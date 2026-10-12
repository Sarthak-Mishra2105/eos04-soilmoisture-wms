"""Publish the prepared soil-moisture mosaic as a time-enabled WMS layer via the GeoServer REST API.

Re-running it replaces only this assignment's store and layer in its own workspace.

    python scripts/configure_geoserver.py                 # http://localhost:8080/geoserver, admin/geoserver
    GEOSERVER_URL=... GEOSERVER_USER=... GEOSERVER_PASSWORD=... python scripts/configure_geoserver.py

Result:
    WMS endpoint   {GEOSERVER_URL}/bhoonidhi/wms   (virtual service: only this workspace's layers)
    Layer          bhoonidhi:eos04_soil_moisture  with TIME dimension, SLD style and legend
"""

import os
import shutil
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

import requests

ROOT = Path(__file__).resolve().parents[1]
MOSAIC_DIR = Path(os.environ.get("MOSAIC_DIR", ROOT / "data" / "mosaic"))
GS = os.environ.get("GEOSERVER_URL", "http://localhost:8080/geoserver").rstrip("/")
AUTH = (os.environ.get("GEOSERVER_USER", "admin"), os.environ.get("GEOSERVER_PASSWORD", "geoserver"))

WS = "bhoonidhi"
WS_URI = "https://bhoonidhi.nrsc.gov.in/#EOS-04_SAR-MRS_SM"
STORE = "eos04_sm_mosaic"
LAYER = "eos04_soil_moisture"
STYLE = "soil_moisture"

LAYER_TITLE = "EOS-04 (RISAT-1A) SAR-MRS Surface Soil Moisture, 500 m"
LAYER_ABSTRACT = (
    "Volumetric surface soil moisture (m3/m3) at ~500 m from ISRO's EOS-04 C-band SAR (MRS mode) "
    "combined with SMAP L-band radiometer data (active-passive algorithm, SAC/ISRO ATBD Dec 2023). "
    "Source products: Bhoonidhi STAC collection EOS-04_SAR-MRS_SM (NRSC). Each TIME value is one "
    "acquisition date; the 17-day EOS-04 repeat cycle means a given location is observed about every "
    "17 days. ATBD range 0.02-0.65 m3/m3 (some delivered values exceed 0.65); nodata = -9999. Band 1, EPSG:4326, 0.005 deg grid, nearest-neighbour preparation."
)
# Where a human can learn about this service (shown as Service/OnlineResource in capabilities).
ONLINE_RESOURCE = os.environ.get("SERVICE_HOME", f"{GS}/www/eos04-demo/index.html")
KEYWORDS = ["soil moisture", "EOS-04", "RISAT-1A", "SAR", "C-band", "Bhoonidhi", "ISRO", "NRSC",
            "agriculture", "hydrology", "time series", "WMS"]

S = requests.Session()
S.auth = AUTH


def rest(method, path, ok=(200, 201), **kw):
    r = S.request(method, f"{GS}/rest/{path}", timeout=300, **kw)
    if r.status_code not in ok:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r


def xml(method, path, body, ok=(200, 201)):
    return rest(method, path, ok=ok, data=body.encode("utf-8"), headers={"Content-Type": "application/xml"})


def wait_for_geoserver(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = S.get(f"{GS}/rest/about/version.json", timeout=10)
            if r.ok:
                v = [x for x in r.json()["about"]["resource"] if x["@name"] == "GeoServer"][0]["Version"]
                print(f"GeoServer {v} at {GS}")
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    sys.exit(f"GeoServer not reachable at {GS}")


def ensure_workspace():
    existing = S.get(f"{GS}/rest/workspaces/{WS}.json", timeout=30)
    if existing.status_code == 404:
        xml("POST", "namespaces", f"<namespace><prefix>{WS}</prefix><uri>{escape(WS_URI)}</uri></namespace>")
    else:
        existing.raise_for_status()
        namespace = S.get(f"{GS}/rest/namespaces/{WS}.json", timeout=30)
        namespace.raise_for_status()
        if namespace.json()["namespace"]["uri"] != WS_URI:
            raise RuntimeError(f"Workspace {WS} belongs to another project; choose another workspace name.")
    print(f"workspace {WS}")


def create_mosaic_store():
    granules = list(MOSAIC_DIR.glob("sm_*.tif"))
    if not granules:
        sys.exit("no granules in data/mosaic - run scripts/prep_rasters.py first")
    existing = S.get(f"{GS}/rest/workspaces/{WS}/coveragestores/{STORE}.json", timeout=30)
    if existing.status_code == 200:
        rest("DELETE", f"workspaces/{WS}/coveragestores/{STORE}?recurse=true")
    elif existing.status_code != 404:
        existing.raise_for_status()
    # Fresh index each time: drop any previous shapefile/properties index, add our config.
    for f in MOSAIC_DIR.iterdir():
        if f.suffix.lower() in (".shp", ".shx", ".dbf", ".prj", ".qix", ".fix", ".cpg") or \
                f.name in (f"{LAYER}.properties", "sample_image", "sample_image.dat", f"{LAYER}.xml"):
            f.unlink()
    for name in ("indexer.properties", "timeregex.properties"):
        shutil.copy(ROOT / "geoserver" / "mosaic" / name, MOSAIC_DIR / name)
    idx = (MOSAIC_DIR / "indexer.properties").read_text().replace("Name=soil_moisture", f"Name={LAYER}")
    (MOSAIC_DIR / "indexer.properties").write_text(idx)

    # A plain filesystem path (forward slashes) is what the external.imagemosaic endpoint accepts on Windows;
    # file:/// URIs are rejected with "Failed to locate the input file".
    url = MOSAIC_DIR.resolve().as_posix()
    rest("PUT", f"workspaces/{WS}/coveragestores/{STORE}/external.imagemosaic?configure=all&coverageName={LAYER}",
         data=url, headers={"Content-Type": "text/plain"})
    print(f"ImageMosaic store {STORE} over {len(granules)} granules ({url})")


def configure_coverage():
    kw = "".join(f"<string>{escape(k)}</string>" for k in KEYWORDS)
    body = f"""
<coverage>
  <title>{escape(LAYER_TITLE)}</title>
  <abstract>{escape(LAYER_ABSTRACT)}</abstract>
  <keywords>{kw}</keywords>
  <srs>EPSG:4326</srs>
  <projectionPolicy>FORCE_DECLARED</projectionPolicy>
  <metadataLinks>
    <metadataLink>
      <type>text/html</type>
      <metadataType>Other</metadataType>
      <content>https://bhoonidhi.nrsc.gov.in/bhoonidhi_resources/help/docs/ATBD_EOS04_SSM_Dec2023_v2.pdf</content>
    </metadataLink>
  </metadataLinks>
  <dimensions>
    <coverageDimension>
      <name>soil_moisture</name>
      <description>Volumetric surface soil moisture</description>
      <range><min>0.02</min><max>0.65</max></range>
      <nullValues><double>-9999.0</double></nullValues>
      <unit>m3/m3</unit>
      <dimensionType><name>REAL_32BITS</name></dimensionType>
    </coverageDimension>
  </dimensions>
  <parameters>
    <entry><string>BackgroundValues</string><string>-9999</string></entry>
    <entry><string>MergeBehavior</string><string>FLAT</string></entry>
    <entry><string>SORTING</string><string>time D</string></entry>
  </parameters>
  <metadata>
    <entry key="time">
      <dimensionInfo>
        <enabled>true</enabled>
        <presentation>LIST</presentation>
        <units>ISO8601</units>
        <defaultValue><strategy>MAXIMUM</strategy></defaultValue>
        <nearestMatchEnabled>false</nearestMatchEnabled>
      </dimensionInfo>
    </entry>
  </metadata>
</coverage>"""
    xml("PUT", f"workspaces/{WS}/coveragestores/{STORE}/coverages/{LAYER}", body)
    print(f"coverage {LAYER}: TIME dimension (LIST, default=latest, exact match or range; else InvalidDimensionValue)")


def upload_style():
    sld = (ROOT / "geoserver" / "styles" / f"{STYLE}.sld").read_bytes()
    existing = S.get(f"{GS}/rest/workspaces/{WS}/styles/{STYLE}.json", timeout=30)
    method = "PUT" if existing.status_code == 200 else "POST"
    path = f"workspaces/{WS}/styles/{STYLE}" if method == "PUT" else f"workspaces/{WS}/styles?name={STYLE}"
    rest(method, path, data=sld,
         headers={"Content-Type": "application/vnd.ogc.sld+xml"})
    xml("PUT", f"layers/{WS}:{LAYER}", f"""
<layer>
  <defaultStyle><name>{STYLE}</name><workspace>{WS}</workspace></defaultStyle>
  <queryable>true</queryable>
  <opaque>false</opaque>
  <attribution>
    <title>Data: NRSC/ISRO Bhoonidhi (EOS-04 SAR-MRS SM); algorithm: SAC/ISRO</title>
    <href>https://bhoonidhi.nrsc.gov.in</href>
  </attribution>
</layer>""")
    print(f"style {WS}:{STYLE} set as default")


def configure_wms_service():
    kw = "".join(f"<string>{escape(k)}</string>" for k in KEYWORDS)
    # Workspace-local (virtual) WMS: {GS}/bhoonidhi/wms lists only this workspace's layers.
    xml("PUT", f"services/wms/workspaces/{WS}/settings", f"""
<wms>
  <workspace><name>{WS}</name></workspace>
  <enabled>true</enabled>
  <name>WMS</name>
  <title>Bhoonidhi EOS-04 Soil Moisture WMS</title>
  <abstrct>Time-enabled OGC WMS 1.3.0 for ISRO EOS-04 (RISAT-1A) SAR-MRS 500 m surface soil moisture
products from NRSC Bhoonidhi. Its documented API provides STAC search and whole-product
downloads; no public WMS for this product was found in the documented/probed endpoints.
Supports GetCapabilities, GetMap (with TIME), GetFeatureInfo and GetLegendGraphic.
Built as a CyberGIS course assignment; not an official NRSC/ISRO service.</abstrct>
  <keywords>{kw}</keywords>
  <onlineResource>{escape(ONLINE_RESOURCE)}</onlineResource>
  <fees>NONE</fees>
  <accessConstraints>NONE. Source data: Bhoonidhi open data, NRSC/ISRO.</accessConstraints>
  <versions>
    <org.geotools.util.Version><version>1.1.1</version></org.geotools.util.Version>
    <org.geotools.util.Version><version>1.3.0</version></org.geotools.util.Version>
  </versions>
  <citeCompliant>false</citeCompliant>
  <srs>
    <string>4326</string><string>3857</string><string>4269</string><string>32643</string><string>32644</string>
  </srs>
  <bboxForEachCRS>true</bboxForEachCRS>
  <exceptionOnInvalidDimension>true</exceptionOnInvalidDimension>
  <getFeatureInfoMimeTypeCheckingEnabled>false</getFeatureInfoMimeTypeCheckingEnabled>
  <getMapMimeTypeCheckingEnabled>false</getMapMimeTypeCheckingEnabled>
  <maxRequestMemory>65536</maxRequestMemory>
  <maxRenderingTime>60</maxRenderingTime>
  <maxRenderingErrors>1000</maxRenderingErrors>
</wms>""")
    xml("PUT", f"workspaces/{WS}/settings", f"""
<settings>
<workspace><name>{WS}</name></workspace>
<charset>UTF-8</charset>
<numDecimals>8</numDecimals>
<verbose>false</verbose>
<verboseExceptions>false</verboseExceptions>
<!-- Behind scripts/public_proxy.py, build URLs from the forwarded public host; locally (no headers) use localhost. -->
<proxyBaseUrl>${{X-Forwarded-Proto}}://${{X-Forwarded-Host}}/geoserver</proxyBaseUrl>
<useHeadersProxyURL>true</useHeadersProxyURL>
<contact>
  <contactPerson>Sarthak Mishra</contactPerson>
  <contactOrganization>IIIT Hyderabad - Cyber GIS: Geospatial Web and GeoBI (course assignment)</contactOrganization>
  <contactPosition>Student</contactPosition>
  <addressCity>Hyderabad</addressCity>
  <addressState>Telangana</addressState>
  <addressCountry>India</addressCountry>
  <contactEmail> </contactEmail>
  <onlineResource>{escape(ONLINE_RESOURCE)}</onlineResource>
</contact>
</settings>""")
    print(f"WMS service metadata set; endpoint {GS}/{WS}/wms")


def install_demo():
    """Serve demo/ from GeoServer's www folder so the web client is same-origin (no CORS needed)."""
    for f in (ROOT / "demo").rglob("*"):
        if f.is_file():
            relative = f.relative_to(ROOT / "demo").as_posix()
            rest("PUT", f"resource/www/eos04-demo/{relative}", data=f.read_bytes(),
                 headers={"Content-Type": "application/octet-stream"})
    print(f"demo client at {GS}/www/eos04-demo/index.html")


def main():
    if not list(MOSAIC_DIR.glob("sm_*.tif")):
        sys.exit("No prepared granules: run scripts/prep_rasters.py before configuring GeoServer.")
    wait_for_geoserver()
    ensure_workspace()
    create_mosaic_store()
    configure_coverage()
    upload_style()
    configure_wms_service()
    if (ROOT / "demo" / "index.html").exists():
        install_demo()
    print("\nTry:")
    print(f"  {GS}/{WS}/wms?service=WMS&version=1.3.0&request=GetCapabilities")


if __name__ == "__main__":
    main()
