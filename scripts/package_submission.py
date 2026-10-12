"""Create code/evidence and prepared-data bundles without secrets or GeoServer internals."""
import subprocess
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'submission';out.mkdir(exist_ok=True)
    # Include tracked and new non-ignored project files; never traverse credential/runtime directories.
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    with zipfile.ZipFile(out/'eos04-soilmoisture-wms-code.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(set(names)):
            if name and (ROOT/name).is_file(): z.write(ROOT/name,name)
    with zipfile.ZipFile(out/'eos04-soilmoisture-wms-prepared-data.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT/'data/mosaic').glob('sm_*.tif')): z.write(p,p.relative_to(ROOT))
        for name in ['data/mosaic/granules.json','data/stac_items.json']:
            z.write(ROOT/name,name)
    for p in out.glob('*.zip'): print(f'{p.name}: {p.stat().st_size/1e6:.2f} MB')

if __name__=='__main__': main()
