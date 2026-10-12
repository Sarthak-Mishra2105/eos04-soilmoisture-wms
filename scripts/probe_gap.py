"""Gap verification: is there any OGC WMS for EOS-04 SAR-MRS Soil Moisture?

Probes Bhoonidhi (portal, API, Vista viewer), Bhuvan and VEDAS for OGC map
endpoints, scans the Bhoonidhi API specification for OGC keywords and checks
whether any published WMS layer looks like soil moisture.

Every raw response is saved under evidence/probes/ and a summary is written to
evidence/gap_report.md so the result can be re-run and re-checked by anyone.

Usage:  python scripts/probe_gap.py
"""

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "probes"
OUT.mkdir(parents=True, exist_ok=True)

TIMEOUT = 90
UA = {"User-Agent": "eos04-sm-wms-gap-probe/1.0 (CyberGIS course assignment)"}

OGC_QUERIES = {
    "WMS": "service=WMS&version=1.3.0&request=GetCapabilities",
    "WMTS": "service=WMTS&version=1.0.0&request=GetCapabilities",
    "WCS": "service=WCS&version=2.0.1&request=GetCapabilities",
}

# Endpoint paths commonly used by GeoServer / MapServer / MapProxy deployments.
PATHS = ["wms", "ows", "geoserver/wms", "geoserver/ows", "geoserver/gwc/service/wmts",
         "cgi-bin/mapserv", "mapproxy/service", "service/wms"]

HOSTS = [
    "https://bhoonidhi.nrsc.gov.in",
    "https://bhoonidhi.nrsc.gov.in/bhoonidhi",
    "https://bhoonidhi.nrsc.gov.in/vista",
    "https://bhoonidhi-api.nrsc.gov.in",
    "https://bhoonidhi-api.nrsc.gov.in/data",
]

SM_PATTERN = re.compile(r"soil[\s_-]*moist|\bssm\b|\bsm[_-]|eos[\s_-]*0?4|risat[\s_-]*1a", re.I)


def slug(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1])[:150]


def fetch(method, url, **kw):
    """Return (status, content_type, body_bytes); never raises."""
    try:
        r = requests.request(method, url, timeout=TIMEOUT, headers=UA, allow_redirects=True, **kw)
        return r.status_code, r.headers.get("Content-Type", ""), r.content, r.url
    except requests.RequestException as e:
        return None, "", f"{type(e).__name__}: {e}".encode(), url


def is_ogc_capabilities(body):
    head = body[:4000].decode("utf-8", "ignore")
    return bool(re.search(r"<(\w+:)?(WMS_Capabilities|WMT_MS_Capabilities|Capabilities|"
                          r"CoverageDescriptions|ServiceExceptionReport|ExceptionReport)\b", head))


def save(name, status, ctype, body, final_url):
    path = OUT / f"{name}.txt"
    header = f"# status: {status}\n# content-type: {ctype}\n# final-url: {final_url}\n\n"
    path.write_bytes(header.encode() + body[:200_000])
    return path.relative_to(ROOT).as_posix()


def probe_ogc_endpoints():
    rows = []
    for host in HOSTS:
        for p in PATHS:
            for svc, q in OGC_QUERIES.items():
                if svc != "WMS" and p not in ("wms", "ows", "geoserver/ows"):
                    continue
                url = f"{host}/{p}?{q}"
                status, ctype, body, final = fetch("GET", url)
                ogc = is_ogc_capabilities(body)
                f = save("ogc_" + slug(url), status, ctype, body, final)
                rows.append({"url": url, "status": status, "content_type": ctype.split(";")[0],
                             "bytes": len(body), "ogc_xml": ogc, "evidence": f})
                print(f"{status} ogc={ogc} {url}", flush=True)
    return rows


def probe_api_docs():
    url = "https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/"
    status, ctype, body, final = fetch("GET", url)
    f = save("api_spec", status, ctype, body, final)
    text = html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>", "",
                                body.decode("utf-8", "ignore"), flags=re.S))
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    counts = {k: len(re.findall(rf"\b{re.escape(k)}\b", text)) for k in
              ["STAC", "OGC", "WMS", "WMTS", "WCS", "WFS", "GetCapabilities", "GetMap", "tile"]}
    sm_listed = "EOS-04_SAR-MRS_SM" in text
    return {"url": url, "status": status, "keyword_counts": counts,
            "EOS-04_SAR-MRS_SM_listed": sm_listed, "evidence": f}


def probe_stac_auth():
    """Even STAC discovery is login-gated: anonymous calls are refused."""
    out = []
    for url in ["https://bhoonidhi-api.nrsc.gov.in/data/collections",
                "https://bhoonidhi-api.nrsc.gov.in/data/collections/EOS-04_SAR-MRS_SM",
                "https://bhoonidhi-api.nrsc.gov.in/data/search?collections=EOS-04_SAR-MRS_SM&limit=1"]:
        status, ctype, body, final = fetch("GET", url)
        f = save("stac_" + slug(url), status, ctype, body, final)
        out.append({"url": url, "status": status, "body_head": body[:160].decode("utf-8", "ignore"),
                    "evidence": f})
        print(f"{status} {url}", flush=True)
    return out


def probe_vista():
    """Vista renders products through a private, token-gated JSON RPC, not OGC."""
    url = "https://bhoonidhi.nrsc.gov.in/vista/Vista"
    status, ctype, body, final = fetch("POST", url, json={"action": "GETCONFIG"})
    f = save("vista_getconfig_noauth", status, ctype, body, final)
    js_status, _, js, _ = fetch("GET", "https://bhoonidhi.nrsc.gov.in/vista/js/ajaxCalls.js")
    # keep only the lines showing how the viewer calls its backend (endpoint + token headers)
    excerpt = b"\n".join(l.strip() for l in js.splitlines() if re.search(rb"url:|setRequestHeader|type:", l))
    save("vista_ajaxCalls_js_excerpt", js_status, "", excerpt, "")
    return {"url": url, "method": "POST {action: GETCONFIG}", "status": status,
            "requires_token": b"usertoken" in body or b"token" in js,
            "ogc_xml": is_ogc_capabilities(body), "evidence": f}


def probe_capabilities_for_sm(name, url):
    status, ctype, body, final = fetch("GET", url)
    f = save("caps_" + name, status, ctype, body, final)
    text = body.decode("utf-8", "ignore")
    layers = re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>\s*<Title>([^<]*)</Title>", text)
    hits = [f"{n} | {t}" for n, t in layers if SM_PATTERN.search(f"{n} {t}")]
    print(f"{status} {name}: {len(layers)} layers, {len(hits)} soil-moisture-like", flush=True)
    return {"name": name, "url": url, "status": status, "ogc_xml": is_ogc_capabilities(body),
            "layer_count": len(layers), "soil_moisture_like_layers": hits, "evidence": f}


def main():
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    result = {
        "run_at_utc": started,
        "api_spec": probe_api_docs(),
        "stac_anonymous": probe_stac_auth(),
        "vista": probe_vista(),
        "ogc_endpoints": probe_ogc_endpoints(),
        "other_portals": [
            probe_capabilities_for_sm("bhuvan_vec1", "https://bhuvan-vec1.nrsc.gov.in/bhuvan/wms?"
                                      "service=WMS&version=1.3.0&request=GetCapabilities"),
            probe_capabilities_for_sm("bhuvan_ras2", "https://bhuvan-ras2.nrsc.gov.in/bhuvan/wms?"
                                      "service=WMS&version=1.3.0&request=GetCapabilities"),
            probe_capabilities_for_sm("vedas_geoserver", "https://vedas.sac.gov.in/geoserver/wms?"
                                      "service=WMS&version=1.3.0&request=GetCapabilities"),
        ],
    }
    (ROOT / "evidence" / "gap_probe_results.json").write_text(json.dumps(result, indent=2))
    write_report(result)


def write_report(r):
    ogc_hits = [e for e in r["ogc_endpoints"] if e["ogc_xml"]]
    lines = [
        "# Gap verification report",
        "",
        f"Generated by `scripts/probe_gap.py` at {r['run_at_utc']}. Raw responses are in `evidence/probes/`.",
        "",
        "## 1. Bhoonidhi API specification",
        "",
        f"Source: {r['api_spec']['url']} (HTTP {r['api_spec']['status']})",
        "",
        "| Keyword | Occurrences |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in r["api_spec"]["keyword_counts"].items()],
        "",
        f"`EOS-04_SAR-MRS_SM` listed as a STAC collection: **{r['api_spec']['EOS-04_SAR-MRS_SM_listed']}**",
        "",
        "## 2. Anonymous access to the STAC catalogue",
        "",
        "| URL | HTTP | Body (start) |",
        "|---|---|---|",
        *[f"| {e['url']} | {e['status']} | `{e['body_head'][:80].strip()}` |" for e in r["stac_anonymous"]],
        "",
        "## 3. Vista viewer",
        "",
        f"`{r['vista']['method']}` to {r['vista']['url']} returned HTTP {r['vista']['status']}; "
        f"OGC XML: {r['vista']['ogc_xml']}; token-gated: {r['vista']['requires_token']}.",
        "",
        "## 4. OGC GetCapabilities probes on Bhoonidhi hosts",
        "",
        f"{len(r['ogc_endpoints'])} requests, **{len(ogc_hits)} returned an OGC capabilities/exception document**.",
        "",
        "| URL | HTTP | Content-Type | OGC XML |",
        "|---|---|---|---|",
        *[f"| {e['url']} | {e['status']} | {e['content_type']} | {e['ogc_xml']} |" for e in r["ogc_endpoints"]],
        "",
        "## 5. Other ISRO portals",
        "",
        "| Portal | HTTP | OGC XML | Layers | Soil-moisture-like layers |",
        "|---|---|---|---|---|",
        *[f"| {e['name']} | {e['status']} | {e['ogc_xml']} | {e['layer_count']} | "
          f"{'; '.join(e['soil_moisture_like_layers']) or 'none'} |" for e in r["other_portals"]],
        "",
    ]
    (ROOT / "evidence" / "gap_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote evidence/gap_report.md")


if __name__ == "__main__":
    sys.exit(main())
