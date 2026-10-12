# Rebuild and publish to an already-running GeoServer on localhost:8080.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:GEOSERVER_URL = 'http://localhost:8080/geoserver'
$steps = @('prep_rasters.py','verify_data.py','configure_geoserver.py','test_wms.py')
foreach ($step in $steps) {
    Write-Host "Running $step"
    python (Join-Path 'scripts' $step)
    if ($LASTEXITCODE -ne 0) { throw "$step failed. Fix the reported issue before continuing." }
}
Write-Host 'Service and validation complete: http://localhost:8080/geoserver/www/eos04-demo/index.html'
