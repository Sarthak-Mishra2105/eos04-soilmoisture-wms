# Data verification

All **169 source products** were downloaded, checksum verified and prepared.
They cover **29 acquisition days**, 2025-06-03 to 2025-10-24.
Downloaded ZIP packages: **90.69 MB**; prepared COGs: **58.78 MB**.

Every prepared band-1 pixel equals the delivered band-1 pixel on the native 0.005-degree EPSG:4326 grid.
The only normalization is explicit nodata (-9999) for non-finite or physically invalid values.
All outputs have one float32 band, explicit nodata and COG layout. Acquisition dates and unique filenames were checked.

The delivered second band contains [-9999.0, -1.0, 0.0, 1.0]; its code semantics are not documented in the supplied product metadata. It is retained in source packages and is not used to mask band 1.
4,113 delivered moisture pixels exceed the ATBD illustrative maximum of 0.65 but remain within [0,1]; these values are preserved and the colour ramp saturates at 0.65.

| Acquisition date (UTC) | Products |
|---|---:|
| 2025-06-03 | 5 |
| 2025-06-10 | 5 |
| 2025-06-11 | 9 |
| 2025-06-19 | 5 |
| 2025-06-20 | 6 |
| 2025-06-27 | 5 |
| 2025-06-28 | 6 |
| 2025-07-06 | 5 |
| 2025-07-07 | 5 |
| 2025-07-14 | 5 |
| 2025-07-15 | 7 |
| 2025-07-23 | 5 |
| 2025-07-24 | 9 |
| 2025-08-09 | 7 |
| 2025-08-26 | 7 |
| 2025-08-27 | 5 |
| 2025-09-03 | 5 |
| 2025-09-04 | 10 |
| 2025-09-12 | 5 |
| 2025-09-13 | 5 |
| 2025-09-20 | 5 |
| 2025-09-21 | 5 |
| 2025-09-29 | 7 |
| 2025-09-30 | 6 |
| 2025-10-07 | 5 |
| 2025-10-08 | 5 |
| 2025-10-16 | 5 |
| 2025-10-17 | 5 |
| 2025-10-24 | 5 |

Detailed per-product checksums and verification: [data_verification.json](data_verification.json).
