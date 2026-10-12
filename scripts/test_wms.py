"""OGC WMS 1.3.0 compliance and behaviour checks for the soil-moisture service.

Runs real HTTP requests against the endpoint and writes evidence/compliance_report.md.

    python scripts/test_wms.py                                   # localhost
    python scripts/test_wms.py --wms https://<public-host>/geoserver/bhoonidhi/wms

Checks (WMS 1.3.0, OGC 06-042):
  * GetCapabilities: schema-valid XML, version negotiation, required service/layer metadata,
    TIME <Dimension>, CRS list, EX_GeographicBoundingBox, styles + LegendURL
  * GetMap: PNG/JPEG output in EPSG:4326 (lat/lon axis order), CRS:84 and EPSG:3857,
    TIME selection (each advertised date, default, strict match and range), transparency
  * GetFeatureInfo: text/plain, text/html, application/json, GML; value equals the source raster
  * GetLegendGraphic
  * Exception reports with the right codes: LayerNotDefined, StyleNotDefined, InvalidCRS,
    InvalidFormat, InvalidPoint, InvalidDimensionValue, MissingParameterValue, VERSION handling
"""

import argparse
import datetime as dt
import io
import json
import random
import sys
from pathlib import Path

import numpy as np
import requests
from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NS = {"wms": "http://www.opengis.net/wms", "xlink": "http://www.w3.org/1999/xlink",
      "ogc": "http://www.opengis.net/ogc"}
LAYER = "eos04_soil_moisture"
import os  # noqa: E402
MOSAIC_DIR = Path(os.environ.get("MOSAIC_DIR", ROOT / "data" / "mosaic"))

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return cond


class WMS:
    def __init__(self, url):
        self.url = url
        self.s = requests.Session()

    def get(self, **params):
        p = {"service": "WMS", "version": "1.3.0"}
        p.update({k: v for k, v in params.items() if v is not None})
        return self.s.get(self.url, params=p, timeout=120)


def exception_code(r):
    try:
        x = etree.fromstring(r.content)
    except etree.XMLSyntaxError:
        return None
    el = x.find(".//ogc:ServiceException", NS)
    if el is None:
        el = x.find(".//ServiceException")
    return el.get("code") if el is not None else None


def png(r):
    return Image.open(io.BytesIO(r.content))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wms", default="http://localhost:8080/geoserver/bhoonidhi/wms")
    a = ap.parse_args()
    w = WMS(a.wms)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # ---------------- GetCapabilities ----------------
    r = w.get(request="GetCapabilities")
    check("GetCapabilities returns HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("GetCapabilities content type is text/xml",
          r.headers.get("Content-Type", "").startswith(("text/xml", "application/vnd.ogc.wms_xml")),
          r.headers.get("Content-Type"))
    caps = etree.fromstring(r.content)
    check("Root element is wms:WMS_Capabilities version 1.3.0",
          caps.tag == "{http://www.opengis.net/wms}WMS_Capabilities" and caps.get("version") == "1.3.0",
          f"{caps.tag} v{caps.get('version')}")
    (ROOT / "evidence" / "capabilities_1_3_0.xml").write_bytes(r.content)
    if caps.tag != "{http://www.opengis.net/wms}WMS_Capabilities":
        check("Endpoint returns capabilities rather than a service exception", False, r.text[:300])
        return finish(started, a.wms)

    schema_url = a.wms.split("/geoserver/")[0] + "/geoserver/schemas/wms/1.3.0/capabilities_1_3_0.xsd" \
        if "/geoserver/" in a.wms else "http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"
    try:
        schema = etree.XMLSchema(etree.parse(schema_url))
        ok = schema.validate(caps)
        check("Capabilities document validates against WMS 1.3.0 XSD", ok,
              "" if ok else str(schema.error_log.last_error))
    except Exception as e:  # schema unreachable
        try:
            schema = etree.XMLSchema(etree.parse("http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"))
            ok = schema.validate(caps)
            check("Capabilities document validates against WMS 1.3.0 XSD (schemas.opengis.net)", ok,
                  "" if ok else str(schema.error_log.last_error))
        except Exception as e2:
            check("Capabilities document validates against WMS 1.3.0 XSD", False, f"schema unavailable: {e2}")

    r_nov = w.s.get(a.wms, params={"service": "WMS", "request": "GetCapabilities"}, timeout=120)
    v = etree.fromstring(r_nov.content).get("version")
    check("Version negotiation: no VERSION -> highest supported (1.3.0)", v == "1.3.0", f"got {v}")
    r_111 = w.s.get(a.wms, params={"service": "WMS", "version": "1.1.1", "request": "GetCapabilities"}, timeout=120)
    check("Version negotiation: VERSION=1.1.1 -> 1.1.1 document",
          etree.fromstring(r_111.content).get("version") == "1.1.1")

    svc = caps.find("wms:Service", NS)
    check("Service/Name is WMS", svc.findtext("wms:Name", namespaces=NS) == "WMS")
    check("Service has Title and Abstract", svc.findtext("wms:Title", namespaces=NS) and
          svc.findtext("wms:Abstract", namespaces=NS))
    reqs = caps.find("wms:Capability/wms:Request", NS)
    for op in ("GetCapabilities", "GetMap", "GetFeatureInfo"):
        check(f"Capability/Request advertises {op}", reqs.find(f"wms:{op}", NS) is not None)
    map_formats = [f.text for f in reqs.findall("wms:GetMap/wms:Format", NS)]
    check("GetMap advertises image/png and image/jpeg", {"image/png", "image/jpeg"} <= set(map_formats))
    gfi_formats = [f.text for f in reqs.findall("wms:GetFeatureInfo/wms:Format", NS)]
    check("GetFeatureInfo advertises text/plain, text/html, application/json",
          {"text/plain", "text/html", "application/json"} <= set(gfi_formats))
    exc_formats = [f.text for f in caps.findall("wms:Capability/wms:Exception/wms:Format", NS)]
    check("Exception formats include XML", "XML" in exc_formats, ", ".join(exc_formats))

    layer = None
    for l in caps.iter("{http://www.opengis.net/wms}Layer"):
        n = l.findtext("wms:Name", namespaces=NS)
        if n and n.split(":")[-1] == LAYER:
            layer = l
    if not check(f"Layer {LAYER} is advertised", layer is not None):
        return finish(started, a.wms)
    lname = layer.findtext("wms:Name", namespaces=NS)
    check("Layer is queryable (queryable=\"1\")", layer.get("queryable") == "1")
    check("Layer has Title and Abstract", layer.findtext("wms:Title", namespaces=NS) and
          layer.findtext("wms:Abstract", namespaces=NS))
    crs_all = {c.text for c in caps.iter("{http://www.opengis.net/wms}CRS")}
    check("CRS list includes EPSG:4326, CRS:84 and EPSG:3857",
          {"EPSG:4326", "CRS:84", "EPSG:3857"} <= crs_all, ", ".join(sorted(crs_all)))
    gbb = layer.find("wms:EX_GeographicBoundingBox", NS)
    bbox = [float(gbb.findtext(f"wms:{k}", namespaces=NS)) for k in
            ("westBoundLongitude", "southBoundLatitude", "eastBoundLongitude", "northBoundLatitude")]
    check("Layer has EX_GeographicBoundingBox", gbb is not None, str(bbox))
    style = layer.find("wms:Style", NS)
    check("Layer has a Style with LegendURL", style is not None and style.find("wms:LegendURL", NS) is not None,
          style.findtext("wms:Name", namespaces=NS) if style is not None else "")

    dim = [d for d in layer.findall("wms:Dimension", NS) if d.get("name") == "time"]
    check("Layer has a TIME <Dimension>", dim)
    dim = dim[0]
    times = [t.strip() for t in dim.text.split(",") if t.strip()]
    check("TIME dimension units=ISO8601", dim.get("units") == "ISO8601")
    iso = lambda t: dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    check("TIME dimension has a default (latest)", iso(dim.get("default")) == iso(max(times)),
          f"default={dim.get('default')}, values={len(times)}")
    check("TIME dimension lists >= 2 acquisition dates", len(times) >= 2, ", ".join(t[:10] for t in times))

    # ---------------- GetMap ----------------
    W, S_, E, N = bbox
    cx, cy = (W + E) / 2, (S_ + N) / 2
    half = min(E - W, N - S_) / 2
    # WMS 1.3.0 + EPSG:4326 => axis order is lat,lon
    r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326",
              bbox=f"{S_},{W},{N},{E}", width=512, height=512, format="image/png", transparent="true")
    ok = r.status_code == 200 and r.headers.get("Content-Type") == "image/png"
    check("GetMap EPSG:4326 (lat/lon axis order) returns image/png", ok, r.headers.get("Content-Type"))
    img = png(r).convert("RGBA")
    alpha = np.array(img)[:, :, 3]
    check("GetMap PNG has data pixels and transparent nodata", (alpha > 0).any() and (alpha == 0).any(),
          f"{(alpha > 0).mean():.1%} opaque")
    (ROOT / "evidence" / "getmap_default_time.png").write_bytes(r.content)

    r84 = w.get(request="GetMap", layers=lname, styles="", crs="CRS:84",
                bbox=f"{W},{S_},{E},{N}", width=512, height=512, format="image/png", transparent="true")
    same = r84.status_code == 200 and np.array_equal(np.array(png(r84).convert("RGBA")), np.array(img))
    check("GetMap CRS:84 (lon/lat) gives the same image as EPSG:4326 (lat/lon)", same)

    from pyproj import Transformer  # noqa: E402  (bundled with rasterio installs)
    t3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = t3857.transform(W, S_)
    x1, y1 = t3857.transform(E, N)
    r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:3857", bbox=f"{x0},{y0},{x1},{y1}",
              width=600, height=400, format="image/png", transparent="true")
    check("GetMap EPSG:3857 returns 600x400 PNG", r.status_code == 200 and png(r).size == (600, 400))

    r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
              width=256, height=256, format="image/jpeg")
    check("GetMap image/jpeg", r.status_code == 200 and r.headers.get("Content-Type") == "image/jpeg")

    imgs = {}
    for t in times:
        r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
                  width=256, height=256, format="image/png", transparent="true", time=t)
        imgs[t] = r.content if r.status_code == 200 and r.headers.get("Content-Type") == "image/png" else None
    check("GetMap succeeds for every advertised TIME value", all(imgs.values()),
          f"{sum(v is not None for v in imgs.values())}/{len(times)}")
    check("Different TIME values render different maps", len({v for v in imgs.values() if v}) > 1)
    r_def = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
                  width=256, height=256, format="image/png", transparent="true")
    check("GetMap without TIME uses the default (latest) date", r_def.content == imgs[max(times)])
    t_mid = iso(times[0]) + (iso(times[1]) - iso(times[0])) / 2
    r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
              width=256, height=256, format="image/png", transparent="true",
              time=t_mid.strftime("%Y-%m-%dT%H:%M:%SZ"))
    check("TIME between two acquisitions -> InvalidDimensionValue", exception_code(r) == "InvalidDimensionValue",
          f"time={t_mid:%Y-%m-%d}, code={exception_code(r)}")
    rng = f"{iso(times[0]):%Y-%m-%d}/{iso(times[-1]):%Y-%m-%d}T23:59:59Z"
    r = w.get(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
              width=256, height=256, format="image/png", transparent="true", time=rng)
    check("TIME as start/end range returns a map (all acquisitions in the period)",
          r.status_code == 200 and r.headers.get("Content-Type") == "image/png", f"time={rng}")
    (ROOT / "evidence" / "times.json").write_text(json.dumps(times, indent=2))

    # ---------------- GetFeatureInfo ----------------
    granules = json.loads((MOSAIC_DIR / "granules.json").read_text()) \
        if (MOSAIC_DIR / "granules.json").exists() else []
    gfi_ok = False
    if granules:
        import rasterio
        g = max(granules, key=lambda x: x["valid_pixels"])
        with rasterio.open(MOSAIC_DIR / g["file"]) as src:
            arr = src.read(1)
            rows, cols = np.where(arr != src.nodata)
            k = random.Random(42).randrange(len(rows))
            row, col = int(rows[k]), int(cols[k])
            lon, lat = src.xy(row, col)
            expected = float(arr[row, col])
            res = src.res[0]
        when = g["time"] + ".000Z" if "." not in g["time"] else g["time"]
        # Map window = exactly that one native pixel, drawn 5x5; I=J=2 is then well inside it,
        # independent of whether the server samples map-pixel corners or centres.
        bb = f"{lat - 0.5 * res},{lon - 0.5 * res},{lat + 0.5 * res},{lon + 0.5 * res}"
        common = dict(request="GetFeatureInfo", layers=lname, query_layers=lname, styles="", crs="EPSG:4326",
                      bbox=bb, width=5, height=5, i=2, j=2, time=when)
        r = w.get(info_format="application/json", **common)
        try:
            fc = r.json()
            got = list(fc["features"][0]["properties"].values())[0]
            gfi_ok = abs(got - expected) < 1e-4
            check("GetFeatureInfo application/json value == source raster pixel", gfi_ok,
                  f"({lat:.4f},{lon:.4f}) {g['time'][:10]}: service={got:.5f} raster={expected:.5f}")
            check("GetFeatureInfo JSON exposes band as 'soil_moisture'",
                  "soil_moisture" in fc["features"][0]["properties"], str(fc["features"][0]["properties"]))
        except Exception as e:
            check("GetFeatureInfo application/json value == source raster pixel", False, f"{e}: {r.text[:200]}")
        for fmt in ("text/plain", "text/html", "application/vnd.ogc.gml"):
            r = w.get(info_format=fmt, **common)
            check(f"GetFeatureInfo {fmt}", r.status_code == 200 and r.headers.get("Content-Type", "").startswith(
                fmt.split(";")[0]) and exception_code(r) is None, r.headers.get("Content-Type"))
        r = w.get(info_format="text/plain", **{**common, "i": 50, "j": 50})
        check("GetFeatureInfo I/J outside image -> InvalidPoint", exception_code(r) == "InvalidPoint",
              exception_code(r))
        r = w.get(info_format="application/x-nope", **common)
        check("GetFeatureInfo unsupported INFO_FORMAT -> InvalidFormat", exception_code(r) == "InvalidFormat",
              exception_code(r))

    # ---------------- GetLegendGraphic ----------------
    r = w.get(request="GetLegendGraphic", layer=lname, format="image/png")
    check("GetLegendGraphic returns image/png", r.status_code == 200 and
          r.headers.get("Content-Type") == "image/png")
    (ROOT / "evidence" / "legend.png").write_bytes(r.content)

    # ---------------- Exceptions ----------------
    base = dict(request="GetMap", layers=lname, styles="", crs="EPSG:4326", bbox=f"{S_},{W},{N},{E}",
                width=64, height=64, format="image/png")
    cases = [
        ("unknown layer -> LayerNotDefined", {"layers": "nope"}, "LayerNotDefined"),
        ("unknown style -> StyleNotDefined", {"styles": "nope"}, "StyleNotDefined"),
        ("unsupported CRS -> InvalidCRS", {"crs": "EPSG:99999"}, "InvalidCRS"),
        ("unsupported FORMAT -> InvalidFormat", {"format": "image/nope"}, "InvalidFormat"),
        ("TIME far from any acquisition -> InvalidDimensionValue", {"time": "1990-01-01T00:00:00Z"},
         "InvalidDimensionValue"),
        ("missing LAYERS -> LayerNotDefined/MissingParameterValue", {"layers": None},
         ("LayerNotDefined", "MissingParameterValue")),
    ]
    for name, override, want in cases:
        p = {**base, **override}
        r = w.get(**p)
        code = exception_code(r)
        want = want if isinstance(want, tuple) else (want,)
        check(f"GetMap {name}", code in want and "xml" in r.headers.get("Content-Type", ""),
              f"code={code}, HTTP {r.status_code}, {r.headers.get('Content-Type')}")
    r = w.get(**{**base, "layers": "nope", "exceptions": "INIMAGE"})
    check("EXCEPTIONS=INIMAGE returns an image", r.headers.get("Content-Type", "").startswith("image/"))
    r = w.get(**{**base, "layers": "nope", "exceptions": "BLANK"})
    check("EXCEPTIONS=BLANK returns an image", r.headers.get("Content-Type", "").startswith("image/"))
    r = w.get(request="NoSuchOp")
    check("Unknown REQUEST -> OperationNotSupported", exception_code(r) == "OperationNotSupported",
          exception_code(r))

    finish(started, a.wms)


def finish(started, url):
    passed = sum(ok for _, ok, _ in results)
    lines = [
        "# WMS 1.3.0 compliance report",
        "",
        f"Endpoint: `{url}`  ",
        f"Run at: {started} (UTC) by `scripts/test_wms.py`  ",
        f"Result: **{passed}/{len(results)} checks passed**",
        "",
        "These are project integration checks against WMS 1.3.0, including XSD validation. They are not an official OGC CITE certification.",
        "",
        "| # | Check | Result | Detail |",
        "|---|---|---|---|",
        *[f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {d.replace('|', '/')[:180]} |"
          for i, (n, ok, d) in enumerate(results, 1)],
        "",
    ]
    (ROOT / "evidence" / "compliance_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{passed}/{len(results)} passed -> evidence/compliance_report.md")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
