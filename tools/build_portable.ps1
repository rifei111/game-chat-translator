# Build a portable, windowless Lingua Studio folder.
# Usage: powershell -ExecutionPolicy Bypass -File tools\build_portable.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path (Split-Path -Parent $Root) ".venv-studio\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  $Py = "python.exe"
}

Write-Host "[build] root: $Root"
Write-Host "[build] python: $Py"
& $Py -m pip install --disable-pip-version-check -q -r (Join-Path $Root "requirements.txt")
& $Py -m PyInstaller --noconfirm --clean (Join-Path $Root "LinguaStudio.spec")

$Out = Join-Path $Root "dist\LinguaStudio"
if (-not (Test-Path $Out)) { throw "PyInstaller did not produce $Out" }
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $Out "README.md") -Force

# The app reads/writes data next to the executable; ship an empty data dir.
$Data = Join-Path $Out "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

$Zip = Join-Path $Root "dist\LinguaStudio-portable.zip"
if (Test-Path $Zip) { Remove-Item -LiteralPath $Zip -Force }
Compress-Archive -Path (Join-Path $Out "*") -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "[build] done: $Out"
Write-Host "[build] zip : $Zip"
