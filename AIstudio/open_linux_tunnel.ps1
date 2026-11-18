<#
.SYNOPSIS
Opens a local SSH port-forward tunnel from Windows/macOS to a Linux AIstudio host.
Defaults to LocalPort 8766 so it does not collide with local AIstudio on port 8765.
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$LinuxHost,
  [int]$LocalPort = 8766,
  [int]$RemotePort = 8765,
  [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$url = "http://127.0.0.1:$LocalPort"
Write-Host "Opening SSH tunnel: $url -> ${LinuxHost}:127.0.0.1:$RemotePort" -ForegroundColor Cyan
if ($OpenBrowser) {
  Start-Process $url
}

& ssh `
  -N `
  -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=15 `
  -o ServerAliveCountMax=3 `
  -L "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}" `
  $LinuxHost
