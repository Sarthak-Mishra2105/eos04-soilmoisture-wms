# WMS 1.3.0 compliance report

Endpoint: `http://localhost:8080/geoserver/bhoonidhi/wms`  
Run at: 2026-10-07T18:04:42+00:00 (UTC) by `scripts/test_wms.py`  
Result: **51/51 checks passed**

These are project integration checks against WMS 1.3.0, including XSD validation. They are not an official OGC CITE certification.

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | GetCapabilities returns HTTP 200 | PASS | HTTP 200 |
| 2 | GetCapabilities content type is text/xml | PASS | text/xml;charset=utf-8 |
| 3 | Root element is wms:WMS_Capabilities version 1.3.0 | PASS | {http://www.opengis.net/wms}WMS_Capabilities v1.3.0 |
| 4 | Capabilities document validates against WMS 1.3.0 XSD | PASS |  |
| 5 | Version negotiation: no VERSION -> highest supported (1.3.0) | PASS | got 1.3.0 |
| 6 | Version negotiation: VERSION=1.1.1 -> 1.1.1 document | PASS |  |
| 7 | Service/Name is WMS | PASS |  |
| 8 | Service has Title and Abstract | PASS |  |
| 9 | Capability/Request advertises GetCapabilities | PASS |  |
| 10 | Capability/Request advertises GetMap | PASS |  |
| 11 | Capability/Request advertises GetFeatureInfo | PASS |  |
| 12 | GetMap advertises image/png and image/jpeg | PASS |  |
| 13 | GetFeatureInfo advertises text/plain, text/html, application/json | PASS |  |
| 14 | Exception formats include XML | PASS | XML, INIMAGE, BLANK, JSON |
| 15 | Layer eos04_soil_moisture is advertised | PASS |  |
| 16 | Layer is queryable (queryable="1") | PASS |  |
| 17 | Layer has Title and Abstract | PASS |  |
| 18 | CRS list includes EPSG:4326, CRS:84 and EPSG:3857 | PASS | CRS:84, EPSG:32643, EPSG:32644, EPSG:3857, EPSG:4269, EPSG:4326 |
| 19 | Layer has EX_GeographicBoundingBox | PASS | [72.0, 26.0, 80.0, 34.0] |
| 20 | Layer has a Style with LegendURL | PASS | soil_moisture |
| 21 | Layer has a TIME <Dimension> | PASS |  |
| 22 | TIME dimension units=ISO8601 | PASS |  |
| 23 | TIME dimension has a default (latest) | PASS | default=2025-10-24T00:00:00Z, values=29 |
| 24 | TIME dimension lists >= 2 acquisition dates | PASS | 2025-06-03, 2025-06-10, 2025-06-11, 2025-06-19, 2025-06-20, 2025-06-27, 2025-06-28, 2025-07-06, 2025-07-07, 2025-07-14, 2025-07-15, 2025-07-23, 2025-07-24, 2025-08-09, 2025-08-26,  |
| 25 | GetMap EPSG:4326 (lat/lon axis order) returns image/png | PASS | image/png |
| 26 | GetMap PNG has data pixels and transparent nodata | PASS | 16.5% opaque |
| 27 | GetMap CRS:84 (lon/lat) gives the same image as EPSG:4326 (lat/lon) | PASS |  |
| 28 | GetMap EPSG:3857 returns 600x400 PNG | PASS |  |
| 29 | GetMap image/jpeg | PASS |  |
| 30 | GetMap succeeds for every advertised TIME value | PASS | 29/29 |
| 31 | Different TIME values render different maps | PASS |  |
| 32 | GetMap without TIME uses the default (latest) date | PASS |  |
| 33 | TIME between two acquisitions -> InvalidDimensionValue | PASS | time=2025-06-06, code=InvalidDimensionValue |
| 34 | TIME as start/end range returns a map (all acquisitions in the period) | PASS | time=2025-06-03/2025-10-24T23:59:59Z |
| 35 | GetFeatureInfo application/json value == source raster pixel | PASS | (29.5675,75.8025) 2025-08-26: service=0.41141 raster=0.41141 |
| 36 | GetFeatureInfo JSON exposes band as 'soil_moisture' | PASS | {'soil_moisture': 0.41141393780708313} |
| 37 | GetFeatureInfo text/plain | PASS | text/plain;charset=utf-8 |
| 38 | GetFeatureInfo text/html | PASS | text/html;charset=utf-8 |
| 39 | GetFeatureInfo application/vnd.ogc.gml | PASS | application/vnd.ogc.gml |
| 40 | GetFeatureInfo I/J outside image -> InvalidPoint | PASS | InvalidPoint |
| 41 | GetFeatureInfo unsupported INFO_FORMAT -> InvalidFormat | PASS | InvalidFormat |
| 42 | GetLegendGraphic returns image/png | PASS |  |
| 43 | GetMap unknown layer -> LayerNotDefined | PASS | code=LayerNotDefined, HTTP 200, text/xml;charset=utf-8 |
| 44 | GetMap unknown style -> StyleNotDefined | PASS | code=StyleNotDefined, HTTP 200, text/xml;charset=utf-8 |
| 45 | GetMap unsupported CRS -> InvalidCRS | PASS | code=InvalidCRS, HTTP 200, text/xml;charset=utf-8 |
| 46 | GetMap unsupported FORMAT -> InvalidFormat | PASS | code=InvalidFormat, HTTP 200, text/xml;charset=utf-8 |
| 47 | GetMap TIME far from any acquisition -> InvalidDimensionValue | PASS | code=InvalidDimensionValue, HTTP 200, text/xml;charset=utf-8 |
| 48 | GetMap missing LAYERS -> LayerNotDefined/MissingParameterValue | PASS | code=LayerNotDefined, HTTP 200, text/xml;charset=utf-8 |
| 49 | EXCEPTIONS=INIMAGE returns an image | PASS |  |
| 50 | EXCEPTIONS=BLANK returns an image | PASS |  |
| 51 | Unknown REQUEST -> OperationNotSupported | PASS | OperationNotSupported |
