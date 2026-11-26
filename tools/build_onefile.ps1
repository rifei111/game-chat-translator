# Build a single-file, windowless Lingua Studio executable.
# Usage: powershell -ExecutionPolicy Bypass -File tools\build_onefile.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path (Split-Path -Parent $Root) ".venv-studio\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  $Py = "python.exe"
}

Write-Host "[onefile] root: $Root"
Write-Host "[onefile] python: $Py"
& $Py -m pip install --disable-pip-version-check -q -r (Join-Path $Root "requirements.txt")
& $Py -m PyInstaller --noconfirm --clean `
  --distpath (Join-Path $Root "dist-onefile") `
  --workpath (Join-Path $Root "build-onefile") `
  (Join-Path $Root "LinguaStudio-onefile.spec")

$Out = Join-Path $Root "dist-onefile\LinguaStudio.exe"
if (-not (Test-Path $Out)) { throw "PyInstaller did not produce $Out" }
$Size = (Get-Item $Out).Length
Write-Host "[onefile] done: $Out"
Write-Host ("[onefile] size: {0:N0} bytes ({1:N1} MiB)" -f $Size, ($Size / 1MB))
