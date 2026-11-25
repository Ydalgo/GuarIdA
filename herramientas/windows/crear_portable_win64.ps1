param(
    [string]$Version = "0.2.0"
)

$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DirDist = Join-Path $Raiz "dist"
$NombrePaquete = "GuarIdA-Portable-win64"
$DirStaging = Join-Path $DirDist $NombrePaquete
$RutaZip = Join-Path $DirDist "$NombrePaquete-v$Version.zip"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  GuarIdA - Generador Portable Win64" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Asegurar que runtime y binarios existen antes de empaquetar
if (-not (Test-Path (Join-Path $Raiz "runtime\python\python.exe"))) {
    Write-Host "[*] Runtime no detectado. Ejecutando instalacion base..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "instalar_windows.ps1")
}

if (Test-Path $DirStaging) { Remove-Item $DirStaging -Recurse -Force }
if (Test-Path $RutaZip) { Remove-Item $RutaZip -Force }
New-Item -ItemType Directory -Force -Path $DirStaging | Out-Null

Write-Host "[1/3] Copiando codigo y lanzadores..." -ForegroundColor Yellow
$ArchivosRaiz = @(
    "Iniciar_GuarIdA.bat",
    "Iniciar_Web.bat",
    "Iniciar_Servicio.bat",
    "README.md",
    "LICENSE"
)
foreach ($Archivo in $ArchivosRaiz) {
    $Origen = Join-Path $Raiz $Archivo
    if (Test-Path $Origen) {
        Copy-Item $Origen -Destination $DirStaging -Force
    }
}
New-Item -ItemType Directory -Force -Path (Join-Path $DirStaging "configuracion") | Out-Null
if (Test-Path (Join-Path $Raiz "configuracion\pyproject.toml")) {
    Copy-Item (Join-Path $Raiz "configuracion\pyproject.toml") -Destination (Join-Path $DirStaging "configuracion\pyproject.toml") -Force
}
"portable=1" | Out-File -FilePath (Join-Path $DirStaging ".portable") -Encoding ascii

# Copiar paquete app sin __pycache__
robocopy (Join-Path $Raiz "app") (Join-Path $DirStaging "app") /E /XD __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null

Write-Host "[2/3] Copiando runtime Python embebido y herramientas binarias..." -ForegroundColor Yellow
robocopy (Join-Path $Raiz "runtime") (Join-Path $DirStaging "runtime") /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null

$DirBinOrigen = Join-Path $Raiz "datos\bin"
$DirBinDestino = Join-Path $DirStaging "datos\bin"
New-Item -ItemType Directory -Force -Path (Join-Path $DirStaging "datos\models") | Out-Null
if (Test-Path $DirBinOrigen) {
    robocopy $DirBinOrigen $DirBinDestino /E /NFL /NDL /NJH /NJS | Out-Null
}

Write-Host "[3/3] Comprimiendo $RutaZip..." -ForegroundColor Yellow
Compress-Archive -Path $DirStaging -DestinationPath $RutaZip -CompressionLevel Optimal

Write-Host ""
Write-Host "[OK] Paquete portable generado en:" -ForegroundColor Green
Write-Host "     $RutaZip" -ForegroundColor White
