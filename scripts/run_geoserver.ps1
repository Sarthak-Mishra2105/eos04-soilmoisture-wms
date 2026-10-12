# Use the GeoServer Windows service already installed on this machine.
param([string]$ServiceName = 'GeoServer')
$ErrorActionPreference = 'Stop'
$service = Get-Service -Name $ServiceName
if ($service.Status -ne 'Running') {
    try { Start-Service -Name $ServiceName }
    catch { throw 'Start the GeoServer service from Windows Services, or run this script in an administrator PowerShell window.' }
}
Write-Host 'Installed GeoServer service is running.'
Write-Host 'Admin UI: http://localhost:8080/geoserver/web/'
Write-Host 'Assignment demo: http://localhost:8080/geoserver/www/eos04-demo/index.html'
