"""Verify every prepared granule against downloaded band 1 and write provenance evidence."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
import rasterio
from fetch_bhoonidhi import sha256

ROOT=Path(__file__).resolve().parents[1]

def main():
    granules=json.loads((ROOT/'data/mosaic/granules.json').read_text())
    items=json.loads((ROOT/'data/stac_items.json').read_text())
    manifest=json.loads((ROOT/'data/download_manifest.json').read_text())
    ids={i['id'] for i in items}
    assert {g['source'] for g in granules}==ids, 'Prepared collection must contain every searched product'
    assert len({g['file'] for g in granules})==len(granules), 'Granule names must be unique'
    results=[]; bounds=[]; beyond=0; flag_codes=set()
    for g in granules:
        m=manifest[g['source']]; raw=ROOT/'data/raw'/m['file']
        assert raw.stat().st_size==m['bytes'] and sha256(raw)==m['sha256'], f'Checksum mismatch: {raw.name}'
        with rasterio.open(ROOT/g['source_file']) as src, rasterio.open(ROOT/'data/mosaic'/g['file']) as dst:
            a=src.read(1); b=dst.read(1)
            normalized=np.where(np.isfinite(a)&(a>=0)&(a<=1),a,-9999).astype('float32')
            equal_grid=(src.crs==dst.crs and src.shape==dst.shape and np.allclose(tuple(src.transform),tuple(dst.transform),atol=1e-10))
            identical=equal_grid and np.array_equal(normalized,b)
            assert identical, f'Prepared raster changed native band-1 pixels: {g["file"]}'
            assert dst.nodata==-9999 and dst.count==1, 'Prepared output must declare single-band moisture and nodata'
            assert dst.tags(ns='IMAGE_STRUCTURE').get('LAYOUT')=='COG', 'Output must have COG layout'
            assert g['time'][:10]==g['acquisition_time'][:10], 'TIME must match original acquisition day'
            beyond+=int(((a>0.65)&(a<=1)).sum())
            flag_codes.update(np.unique(src.read(2)).tolist())
            bounds.append(list(dst.bounds))
            results.append({'product':g['source'],'granule':g['file'],'native_pixels_preserved':True,'sha256':m['sha256']})
    counts=Counter(g['time'][:10] for g in granules)
    summary={'collection':'EOS-04_SAR-MRS_SM','products':len(granules),'acquisition_days':len(counts),
             'date_start':min(counts),'date_end':max(counts),'download_bytes':sum(m['bytes'] for m in manifest.values()),
             'prepared_bytes':sum((ROOT/'data/mosaic'/g['file']).stat().st_size for g in granules),
             'bbox':[min(b[0] for b in bounds),min(b[1] for b in bounds),max(b[2] for b in bounds),max(b[3] for b in bounds)],
             'dates':[{'date':d,'products':n} for d,n in sorted(counts.items())],
             'band':1,'source_bands':2,'source_flag_values':sorted(flag_codes),
             'values_above_atbd_max':beyond,'nodata':-9999,'resampling':'nearest; native pixels identical'}
    (ROOT/'evidence/data_verification.json').write_text(json.dumps({'summary':summary,'products':results},indent=2),encoding='utf-8')
    (ROOT/'demo/dataset.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Data verification','',f'All **{len(granules)} source products** were downloaded, checksum verified and prepared.',
           f'They cover **{len(counts)} acquisition days**, {min(counts)} to {max(counts)}.',
           f'Downloaded ZIP packages: **{summary["download_bytes"]/1e6:.2f} MB**; prepared COGs: **{summary["prepared_bytes"]/1e6:.2f} MB**.',
           '', 'Every prepared band-1 pixel equals the delivered band-1 pixel on the native 0.005-degree EPSG:4326 grid.',
           'The only normalization is explicit nodata (-9999) for non-finite or physically invalid values.',
           'All outputs have one float32 band, explicit nodata and COG layout. Acquisition dates and unique filenames were checked.',
           '',f'The delivered second band contains {sorted(flag_codes)}; its code semantics are not documented in the supplied product metadata. It is retained in source packages and is not used to mask band 1.',
           f'{beyond:,} delivered moisture pixels exceed the ATBD illustrative maximum of 0.65 but remain within [0,1]; these values are preserved and the colour ramp saturates at 0.65.',
           '', '| Acquisition date (UTC) | Products |','|---|---:|',*[f'| {d} | {n} |' for d,n in sorted(counts.items())],
           '', 'Detailed per-product checksums and verification: [data_verification.json](data_verification.json).','']
    (ROOT/'evidence/data_verification.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
