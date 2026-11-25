param(
    [string]$Version = "0.2.0"
)

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DirDist = Join-Path $Raiz "dist"
$DirStaging = Join-Path $DirDist "GuarIdA-Portable-win64"
$RutaMsi = Join-Path $DirDist "GuarIdA-Offline-Setup-x64-v$Version.msi"
$RutaWxs = Join-Path $PSScriptRoot "guarida.wxs"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  GuarIdA - Creador de .MSI Offline" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Verificar WiX Toolset v4/v5
$WixCmd = Get-Command wix -ErrorAction SilentlyContinue
if (-not $WixCmd) {
    Write-Host "[ERROR] No se encontro WiX Toolset ('wix' CLI)." -ForegroundColor Red
    Write-Host "        Instalalo con: dotnet tool install --global wix" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $DirStaging)) {
    Write-Host "[*] Carpeta staging portable no encontrada. Generandola primero..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "crear_portable_win64.ps1") -Version $Version
}

Write-Host "[1/2] Compilando instalador MSI offline con WiX..." -ForegroundColor Yellow
& wix build $RutaWxs `
    -arch x64 `
    -d "SourceDir=$DirStaging" `
    -d "ProductVersion=$Version" `
    -o $RutaMsi

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Fallo la compilacion del MSI." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Instalador MSI offline generado en:" -ForegroundColor Green
Write-Host "     $RutaMsi" -ForegroundColor White
