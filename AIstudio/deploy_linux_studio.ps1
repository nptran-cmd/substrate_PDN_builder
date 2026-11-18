<#
.SYNOPSIS
Packages AIstudio + Agent 04 + CadenceBatchRunner into a clean tar.gz (no .mcm/.dmp/venv)
and deploys it via SSH/SCP (or optional GCS bucket) to a target Linux host with Cadence APD.
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$LinuxHost,
  [string]$RemoteDir = "~/agent04_linux_studio",
  [ValidateSet("scp", "gcs")]
  [string]$Transport = "scp",
  [string]$GcsBucket = "",
  [string]$GcsObject = "_bootstrap/agent04_linux_studio.tar.gz"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$StageId = [guid]::NewGuid().ToString("N").Substring(0, 8)
$StageRoot = Join-Path $env:TEMP "a4_studio_linux_$StageId"
$BundleDir = Join-Path $StageRoot "bundle"
$TarPath = Join-Path $StageRoot "agent04_linux_studio.tar.gz"

$ExcludedExt = @(".mcm", ".spd", ".dmp", ".log", ".pyc", ".pyo", ".zip", ".tgz", ".gz")
$ExcludedDirNames = @("__pycache__", ".venv", ".venv_linux", "workspaces", "MCM_template", "stage1_inputs", "MCM_test", "output", "outputs", "logs", ".git")

function Copy-CleanTree {
  param([string]$SourceDir, [string]$DestDir)
  if (-not (Test-Path $SourceDir)) { return }
  New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
  Get-ChildItem -Path $SourceDir -Force | ForEach-Object {
    $item = $_
    if ($item.PSIsContainer) {
      if ($ExcludedDirNames -contains $item.Name) { return }
      Copy-CleanTree -SourceDir $item.FullName -DestDir (Join-Path $DestDir $item.Name)
    } else {
      $ext = $item.Extension.ToLowerInvariant()
      if ($ExcludedExt -contains $ext -or $item.Name -like "*_dump.txt") { return }
      $targetFile = Join-Path $DestDir $item.Name
      if ($ext -eq ".sh") {
        $text = [System.IO.File]::ReadAllText($item.FullName, [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::WriteAllText($targetFile, $text.Replace("`r`n", "`n"), [System.Text.UTF8Encoding]::new($false))
      } else {
        Copy-Item -Path $item.FullName -Destination $targetFile -Force
      }
    }
  }
}

try {
  Write-Host "1. Staging clean AIstudio + Agent 04 Linux bundle at $BundleDir..." -ForegroundColor Cyan
  New-Item -ItemType Directory -Path $BundleDir -Force | Out-Null
  Copy-CleanTree -SourceDir (Join-Path $RepoRoot "AIstudio") -DestDir (Join-Path $BundleDir "AIstudio")
  Copy-CleanTree -SourceDir (Join-Path $RepoRoot "agent04_pdn_architect") -DestDir (Join-Path $BundleDir "agent04_pdn_architect")
  Copy-CleanTree -SourceDir (Join-Path $RepoRoot "agent09_via_routing") -DestDir (Join-Path $BundleDir "agent09_via_routing")

  Write-Host "2. Creating compressed archive $TarPath..." -ForegroundColor Cyan
  & tar -czf $TarPath -C $BundleDir .
  if ($LASTEXITCODE -ne 0) { throw "tar failed ($LASTEXITCODE)" }

  if ($Transport -eq "gcs") {
    if (-not $GcsBucket) { throw "Specify -GcsBucket when using -Transport gcs." }
    $GcsUri = "gs://$GcsBucket/$GcsObject"
    & gcloud storage cp $TarPath $GcsUri
    if ($LASTEXITCODE -ne 0) { throw "gcloud storage cp failed ($LASTEXITCODE)" }
    Write-Host "Uploaded to $GcsUri. Extract on $LinuxHost and run ./AIstudio/start_linux_studio.sh --bootstrap" -ForegroundColor Green
  } else {
    & ssh $LinuxHost "mkdir -p $RemoteDir"
    if ($LASTEXITCODE -ne 0) { throw "ssh mkdir failed ($LASTEXITCODE)" }
    & scp $TarPath "${LinuxHost}:${RemoteDir}/agent04_linux_studio.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw "scp failed ($LASTEXITCODE)" }
    & ssh $LinuxHost "cd $RemoteDir && tar -xzf agent04_linux_studio.tar.gz && chmod +x AIstudio/start_linux_studio.sh"
    if ($LASTEXITCODE -ne 0) { throw "remote tar extract failed ($LASTEXITCODE)" }
    Write-Host "Deployed to ${LinuxHost}:${RemoteDir}. Run ./AIstudio/start_linux_studio.sh --bootstrap" -ForegroundColor Green
  }
} finally {
  if (Test-Path $StageRoot) { Remove-Item -Path $StageRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
