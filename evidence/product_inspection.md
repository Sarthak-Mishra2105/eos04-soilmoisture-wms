# Delivered EOS-04 product inspection

All 169 downloaded products were inspected during preparation and full data verification.

Each ZIP contains a 600×600, two-band float32 GeoTIFF plus metadata and a preview image. Raster CRS is EPSG:4326 and pixels are 0.005 degrees. The supplied metadata labels it `L4-Soil-Moisture-500m`, `ParameterValue=Volumetric Soil Moisture`.

Band 1 contains continuous moisture values and -9999 fill. Band 2 contains -9999/-1/0/1; no band-code definitions were found in the supplied metadata. Band 1 is published, and original band 2 is retained in the downloaded products.

Some band-1 values exceed the 2023 ATBD nominal maximum 0.65. These physically valid values are preserved, not clipped or silently treated as invalid.

See [data_verification.md](data_verification.md) for the all-product verification results and [data/download_manifest.json](../data/download_manifest.json) for download sizes/checksums.
