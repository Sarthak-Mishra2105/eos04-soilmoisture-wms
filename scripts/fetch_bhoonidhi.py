"""Search/download EOS-04 soil moisture with automatic token refresh and verified files.
Credentials are prompted for locally and never written to disk.
Use --saved-items --max 169 to download the saved catalogue selection.
"""
import argparse
import datetime as dt
import getpass
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

API = 'https://bhoonidhi-api.nrsc.gov.in'
COLLECTION = 'EOS-04_SAR-MRS_SM'
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
MANIFEST = ROOT / 'data' / 'download_manifest.json'
PROGRESS = ROOT / 'data' / 'download_progress.json'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    tmp.replace(path)

class Bhoonidhi:
    def __init__(self):
        self.session = requests.Session()
        self.user = os.environ.get('BHOONIDHI_USER') or input('Bhoonidhi userId: ')
        password = os.environ.get('BHOONIDHI_PASSWORD') or getpass.getpass('Bhoonidhi password: ')
        self.tokens = {}
        self.authenticate({'userId':self.user, 'password':password, 'grant_type':'password'})
        del password
    def authenticate(self, body):
        r = self.session.post(f'{API}/auth/token', json=body, timeout=60)
        if r.status_code == 403:
            raise RuntimeError('Maximum active Bhoonidhi sessions; log out of other sessions, then rerun.')
        if r.status_code == 401:
            raise RuntimeError('Login failed or refresh session expired; rerun and sign in.')
        r.raise_for_status()
        self.tokens = r.json()
        self.expires = time.monotonic() + float(self.tokens.get('expires_in',1200)) - 60
    def refresh(self):
        self.authenticate({'userId':self.user, 'refresh_token':self.tokens['refresh_token'], 'grant_type':'refresh_token'})
    def request(self, method, url, **kw):
        url = urljoin(API + '/', url)
        if urlparse(url).netloc != urlparse(API).netloc:
            raise ValueError('Refusing to send authentication to a different host')
        for attempt in range(2):
            if time.monotonic() >= self.expires: self.refresh()
            r = self.session.request(method,url,headers={'Authorization':f"Bearer {self.tokens['access_token']}"},**kw)
            if r.status_code != 401 or attempt: return r
            r.close()
            self.refresh()
    def close(self):
        try:
            if self.tokens.get('refresh_token'):
                self.session.post(f'{API}/auth/logout',timeout=20,headers={'Authorization':f"Bearer {self.tokens['refresh_token']}"})
        except requests.RequestException: pass
        self.session.close()

def search(client, a):
    body={'collections':[COLLECTION], 'bbox':a.bbox, 'datetime':f'{a.start}T00:00:00Z/{a.end}T23:59:59Z', 'limit':500}
    if not a.include_offline:
        body.update({'filter':{'args':[{'property':'Online'},'Y'],'op':'eq'},'filter-lang':'cql2-json'})
    items, url, method, seen = {}, f'{API}/data/search', 'POST', set()
    while url:
        key=(url,method,json.dumps(body,sort_keys=True))
        if key in seen: raise RuntimeError('Repeated catalogue pagination link')
        seen.add(key)
        with client.request(method,url,timeout=120,**({'json':body} if method=='POST' else {})) as r:
            r.raise_for_status(); page=r.json()
        for item in page.get('features',[]): items[item['id']]=item
        nxt=next((x for x in page.get('links',[]) if x.get('rel')=='next'),None)
        if not nxt or not page.get('features'): break
        url=urljoin(url,nxt['href']); method=nxt.get('method','GET').upper()
        body=nxt.get('body',body) if method=='POST' else None
    return sorted(items.values(),key=lambda i:(i.get('properties',{}).get('datetime',''),i['id']))

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def download(client,item,manifest):
    item_id=item['id']; previous=manifest.get(item_id)
    if previous:
        path=RAW/previous['file']
        if path.exists() and path.stat().st_size==previous['bytes'] and sha256(path)==previous['sha256']:
            print('  already verified:',path.name,flush=True); return previous
    for attempt in range(6):
        try:
            with client.request('GET',f'{API}/download',params={'id':item_id,'collection':COLLECTION},stream=True,timeout=(30,120)) as r:
                if r.status_code in (408,412,429,500,502,503,504):
                    print(f'  HTTP {r.status_code}; retry {attempt+1}/6',flush=True)
                    r.close(); time.sleep(min(10*(attempt+1),60)); continue
                r.raise_for_status()
                ctype=r.headers.get('Content-Type','').lower()
                if 'json' in ctype or 'text/html' in ctype:
                    raise RuntimeError(f'Download returned {ctype} instead of a product: {r.text[:150]}')
                partial=RAW/(item_id+'.part')
                with partial.open('wb') as f:
                    for chunk in r.iter_content(1024*1024): f.write(chunk)
                expected=r.headers.get('Content-Length')
                if expected and not r.headers.get('Content-Encoding') and partial.stat().st_size!=int(expected):
                    raise requests.ConnectionError('Incomplete transfer (Content-Length mismatch)')
            if zipfile.is_zipfile(partial):
                with zipfile.ZipFile(partial) as z:
                    if z.testzip(): raise requests.ConnectionError('ZIP integrity check failed')
                suffix='.zip'
            else:
                import rasterio
                with rasterio.open(partial) as src: src.read(1)
                suffix='.tif'
            out=RAW/(item_id+suffix); partial.replace(out)
            record={'file':out.name,'bytes':out.stat().st_size,'sha256':sha256(out),
                    'datetime':item.get('properties',{}).get('datetime'),
                    'downloaded_at':dt.datetime.now(dt.timezone.utc).isoformat()}
            print(f"  saved {out.name} ({record['bytes']/1e6:.2f} MB)",flush=True)
            return record
        except requests.RequestException as e:
            if isinstance(e,requests.HTTPError) and e.response.status_code<500: raise
            if attempt==5: raise
            print(f'  {type(e).__name__}; retrying',flush=True)
            time.sleep(min(10*(attempt+1),60))
    raise RuntimeError(f'Download failed after six attempts: {item_id}')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bbox',nargs=4,type=float,default=[74,28,78,32])
    ap.add_argument('--start',default='2025-06-01'); ap.add_argument('--end',default='2025-10-31')
    ap.add_argument('--max',type=int,default=169)
    ap.add_argument('--saved-items',action='store_true'); ap.add_argument('--search-only',action='store_true')
    ap.add_argument('--include-offline',action='store_true'); a=ap.parse_args()
    RAW.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    write_json(PROGRESS,{'status':'awaiting_login'})
    client=None
    try:
        client=Bhoonidhi(); catalogue=ROOT/'data'/'stac_items.json'
        items=json.loads(catalogue.read_text()) if a.saved_items else search(client,a)
        if not a.saved_items: write_json(catalogue,items)
        items=sorted(items,key=lambda i:(i.get('properties',{}).get('datetime',''),i['id']))
        print(f'{len(items)} products in selection.',flush=True)
        if a.search_only:
            for item in items: print(item.get('properties',{}).get('datetime'),item['id'])
            return
        selected=items[:a.max]
        for n,item in enumerate(selected,1):
            write_json(PROGRESS,{'status':'downloading','completed':n-1,'total':len(selected),'current_product':item['id']})
            print(f"[{n}/{len(selected)}] {item['id']}",flush=True)
            manifest[item['id']]=download(client,item,manifest); write_json(MANIFEST,manifest)
        write_json(PROGRESS,{'status':'complete','completed':len(selected),'total':len(selected),
                             'bytes':sum(manifest[i['id']]['bytes'] for i in selected)})
        print('Downloads complete.',flush=True)
    except Exception as e:
        write_json(PROGRESS,{'status':'failed','error':str(e)}); raise
    finally:
        if client: client.close()

if __name__=='__main__': main()
