"""Turn downloaded EOS-04 SAR-MRS Soil Moisture products into a time-indexed mosaic.

Input : data/raw/*  (product .zip files or GeoTIFFs as delivered by Bhoonidhi)
Output: data/mosaic/sm_YYYYMMDDTHHMMSS_<id>.tif   Cloud Optimized GeoTIFFs, EPSG:4326,
        float32 volumetric soil moisture (m3/m3), nodata = -9999, on a common
        0.005 deg (~500 m) grid so GeoServer's ImageMosaic can stack them.

Acquisitions are grouped by UTC day from the saved STAC metadata (falling back to
product dates). Native pixels are preserved with nearest-neighbour grid preparation.
Original timestamps remain in granules.json. Unique product hashes prevent collisions.

Usage:  python scripts/prep_rasters.py [--res 0.005]
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio import shutil as rio_shutil
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
WORK = ROOT / "data" / "extracted"
OUT = ROOT / "data" / "mosaic"
NODATA = -9999.0
# Physical bounds for volumetric soil moisture. The ATBD gives a valid range of
# 0.02-0.65 m3/m3; anything outside [0, 1] is a fill / flag value.
PHYS_MIN, PHYS_MAX = 0.0, 1.0

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def stac_datetimes():
    p = ROOT / "data" / "stac_items.json"
    if not p.exists():
        return {}
    return {it["id"]: it.get("properties", {}).get("datetime") for it in json.loads(p.read_text())}


def parse_time(name, tags, stac):
    # Group acquisitions by UTC day so adjacent scenes mosaic into one TIME value.
    # The original acquisition timestamps are retained separately in granules.json.
    for item_id, iso in stac.items():
        if item_id in name and iso:
            when = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.datetime.combine(when.date(), dt.time())
    m = re.search(r"(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{4})", name.upper())
    if m:
        return dt.datetime(int(m[3]), MONTHS[m[2]], int(m[1]))
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if m:
        return dt.datetime(int(m[1]), int(m[2]), int(m[3]))
    for k in ("TIFFTAG_DATETIME", "ACQUISITION_DATE", "DATE"):
        if k in tags:
            v = re.sub(r"[:/-]", "", tags[k])[:8]
            return dt.datetime.strptime(v, "%Y%m%d")
    raise ValueError(f"cannot determine acquisition date for {name}")


def find_sm_tifs():
    """Yield (product_name, tif_path) for every soil-moisture GeoTIFF in data/raw."""
    WORK.mkdir(parents=True, exist_ok=True)
    for f in sorted(RAW.iterdir()):
        if f.suffix.lower() == ".zip":
            dest = WORK / f.stem
            if not (dest / ".extraction_complete").exists():
                with zipfile.ZipFile(f) as z:
                    for member in z.infolist():
                        if not (dest / member.filename).resolve().is_relative_to(dest.resolve()):
                            raise ValueError(f"Unsafe archive path: {member.filename}")
                    z.extractall(dest)
                (dest / ".extraction_complete").touch()
            tifs = [t for t in dest.rglob("*") if t.suffix.lower() in (".tif", ".tiff")]
        elif f.suffix.lower() in (".tif", ".tiff"):
            tifs = [f]
        else:
            continue
        # Ignore explicit ancillary quality/angle files rather than publishing them as moisture.
        candidates = [t for t in tifs if not re.search(r"quality|flag|incidence|lia|mask", t.name, re.I)]
        sm = [t for t in candidates if re.search(r"sm|soil|moist", t.name, re.I)] or candidates
        if len(sm) != 1:
            raise ValueError(f"{f.name}: expected one soil-moisture raster, found {len(sm)}; inspect this product.")
        for t in sm:
            yield f.stem, t


def to_cog(src_path, dst_path, res):
    with rasterio.open(src_path) as src:
        data = src.read(1).astype("float32")
        if src.count not in (1, 2) or src.crs is None:
            raise ValueError(f"Expected a georeferenced one/two-band EOS-04 moisture raster: {src_path}")
        if src.count == 2:
            flags = src.read(2)
            observed = np.unique(flags[np.isfinite(flags) & (flags != -9999)])
            if not np.isin(observed, [-1, 0, 1]).all():
                raise ValueError(f"Unexpected second-band values in {src_path}; inspect the band semantics.")
        nodata_mask = src.read_masks(1) == 0
        data = data * src.scales[0] + src.offsets[0]
        bad = ~np.isfinite(data) | (data < PHYS_MIN) | (data > PHYS_MAX)
        bad |= nodata_mask
        data[bad] = NODATA

        dst_crs = "EPSG:4326"
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res)
        # Snap the output origin to a global res-aligned grid so granules line up.
        a = transform
        x0 = np.floor(a.c / res) * res
        y0 = np.ceil(a.f / res) * res
        transform = rasterio.Affine(res, 0, x0, 0, -res, y0)
        width = int(np.ceil((a.c + width * a.a - x0) / res - 1e-8))
        height = int(np.ceil((y0 - (a.f + height * a.e)) / res - 1e-8))
        out = np.full((height, width), NODATA, dtype="float32")
        reproject(data, out, src_transform=src.transform, src_crs=src.crs, src_nodata=NODATA,
                  dst_transform=transform, dst_crs=dst_crs, dst_nodata=NODATA,
                  resampling=Resampling.nearest)

    profile = dict(driver="COG", dtype="float32", count=1, width=width, height=height,
                   crs=dst_crs, transform=transform, nodata=NODATA, compress="DEFLATE",
                   predictor=3, blocksize=512, overview_resampling="average")
    tmp = dst_path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **{**profile, "driver": "GTiff"}) as dst:
        dst.write(out, 1)
        dst.update_tags(units="m3/m3", long_name="Surface soil moisture (volumetric)",
                        source=str(src_path.name), resampling="nearest", time_grouping="UTC acquisition day")
    with rasterio.open(tmp) as t:
        rio_shutil.copy(t, dst_path, **profile)
    tmp.unlink()
    v = out[out != NODATA]
    return v.size, (float(v.min()), float(v.mean()), float(v.max())) if v.size else (None,) * 3


def main():
    global RAW, OUT, WORK
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=float, default=0.005, help="output pixel size in degrees (source grid is 0.005)")
    ap.add_argument("--raw", type=Path, default=RAW, help="folder with downloaded products")
    ap.add_argument("--out", type=Path, default=OUT, help="folder for mosaic granules")
    a = ap.parse_args()
    RAW, OUT, WORK = a.raw, a.out, a.raw.parent / "extracted"

    OUT.mkdir(parents=True, exist_ok=True)
    stac = stac_datetimes()
    summary = []
    for product, tif in find_sm_tifs():
        with rasterio.open(tif) as s:
            tags = s.tags()
            print(f"{tif.name}: {s.width}x{s.height} {s.dtypes[0]} crs={s.crs} nodata={s.nodata}")
        when = parse_time(product + " " + tif.name, tags, stac)
        short = hashlib.sha256((product + "/" + tif.name).encode()).hexdigest()[:16]
        dst = OUT / f"sm_{when:%Y%m%dT%H%M%S}_{short}.tif"
        n, (lo, mean, hi) = to_cog(tif, dst, a.res)
        print(f"  -> {dst.name}  valid px={n}  min/mean/max={lo}/{mean}/{hi}")
        summary.append({"file": dst.name, "time": when.isoformat(), "source": product,
                        "source_file": str(tif.relative_to(ROOT)) if tif.is_relative_to(ROOT) else tif.name,
                        "acquisition_time": stac.get(product),
                        "valid_pixels": n, "min": lo, "mean": mean, "max": hi})
    if not summary:
        raise ValueError("No downloaded GeoTIFFs or ZIP products found in the input directory.")
    if len({g["file"] for g in summary}) != len(summary):
        raise ValueError("Duplicate output granule names; preparation aborted.")
    # Drop only stale generated granules after the new preparation succeeds.
    expected = {g["file"] for g in summary}
    for stale in OUT.glob("sm_*.tif"):
        if stale.name not in expected:
            stale.unlink()
    (OUT / "granules.json").write_text(json.dumps(summary, indent=2))
    print(f"{len(summary)} granules written to {OUT}")


if __name__ == "__main__":
    main()
