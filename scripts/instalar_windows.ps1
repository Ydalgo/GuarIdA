param(
    [switch]$SinHerramientas
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Raiz = Split-Path -Parent $PSScriptRoot
$DirRuntime = Join-Path $Raiz "runtime\python"
$DirDatos = Join-Path $Raiz "datos"
$PyExe = Join-Path $DirRuntime "python.exe"
$ArchivoPortable = Join-Path $Raiz ".portable"

$PythonVersion = "3.12.7"
$PythonZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  GuarIdA - Instalacion desde cero (Win)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $DirDatos | Out-Null
if (-not (Test-Path $ArchivoPortable)) {
    "portable=1" | Out-File -FilePath $ArchivoPortable -Encoding ascii
}

if (-not (Test-Path $PyExe)) {
    Write-Host "[1/4] Descargando Python embebido $PythonVersion..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $DirRuntime | Out-Null
    $ZipPath = Join-Path $env:TEMP "guarida-python-embed.zip"
    Invoke-WebRequest -Uri $PythonZipUrl -OutFile $ZipPath -UseBasicParsing
    Expand-Archive -Path $ZipPath -DestinationPath $DirRuntime -Force
    Remove-Item $ZipPath -Force

    $PthFile = Get-ChildItem -Path $DirRuntime -Filter "python*._pth" | Select-Object -First 1
    if ($PthFile) {
        $Contenido = Get-Content $PthFile.FullName
        $Contenido = $Contenido -replace "^#\s*import site", "import site"
        if ($Contenido -notcontains "..\..") {
            $Contenido += "..\.."
        }
        $Contenido | Set-Content -Path $PthFile.FullName -Encoding ascii
    }
} else {
    Write-Host "[1/4] Python embebido ya presente en runtime\python." -ForegroundColor Green
}

& $PyExe -m pip --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[2/4] Instalando pip en Python embebido..." -ForegroundColor Yellow
    $GetPipPath = Join-Path $env:TEMP "get-pip.py"
    Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath -UseBasicParsing
    & $PyExe $GetPipPath --no-warn-script-location
    Remove-Item $GetPipPath -Force
} else {
    Write-Host "[2/4] pip ya disponible." -ForegroundColor Green
}

Write-Host "[3/4] Instalando dependencias Python..." -ForegroundColor Yellow
& $PyExe -m pip install --upgrade --no-warn-script-location `
    "cryptography>=41.0.0" `
    "psutil>=5.9.0" `
    "fastapi==0.115.4" `
    "uvicorn==0.32.0"

if (-not $SinHerramientas) {
    Write-Host "[4/4] Descargando herramientas del bunker (llama-server, git, ripgrep)..." -ForegroundColor Yellow
    $CodigoTools = @"
from guarida_manager.downloader.tools import GestorHerramientasBunker

for hid in ("llama-server", "git", "ripgrep"):
    print(f" -> Verificando/descargando {hid}...")
    GestorHerramientasBunker.descargar_y_desplegar(hid)
print("Herramientas listas.")
"@
    & $PyExe -c $CodigoTools
} else {
    Write-Host "[4/4] Omitiendo descarga de herramientas (-SinHerramientas)." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[OK] Instalacion completada. Ejecuta Iniciar_GuarIdA.bat o Iniciar_Web.bat." -ForegroundColor Green
