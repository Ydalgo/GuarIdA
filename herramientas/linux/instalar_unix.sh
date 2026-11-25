#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR_RUNTIME="$RAIZ/runtime/python"
DIR_DATOS="$RAIZ/datos"
PY_EMB="$DIR_RUNTIME/bin/python3"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux)  PBS_OS="unknown-linux-gnu" ;;
    Darwin) PBS_OS="apple-darwin" ;;
    *)
        echo "[ERROR] Sistema operativo no soportado automaticamente: $OS"
        exit 1
        ;;
esac

case "$ARCH" in
    x86_64|amd64)  PBS_ARCH="x86_64" ;;
    aarch64|arm64) PBS_ARCH="aarch64" ;;
    *)
        echo "[ERROR] Arquitectura no soportada automaticamente: $ARCH"
        exit 1
        ;;
esac

PY_TAG="20241016"
PY_VER="3.12.7"
PBS_FILE="cpython-${PY_VER}+${PY_TAG}-${PBS_ARCH}-${PBS_OS}-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/${PBS_FILE}"

echo "=========================================="
echo "  GuarIdA - Instalacion desde cero (Unix)"
echo "=========================================="

mkdir -p "$DIR_DATOS"
echo "portable=1" > "$RAIZ/.portable"

if [ ! -x "$PY_EMB" ]; then
    echo "[1/3] Descargando Python portable ($PY_VER para $PBS_ARCH-$PBS_OS)..."
    mkdir -p "$RAIZ/runtime"
    TMP_TAR="/tmp/guarida-python-${PY_VER}.tar.gz"
    if command -v curl >/dev/null 2>&1; then
        curl -fL "$PBS_URL" -o "$TMP_TAR"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$TMP_TAR" "$PBS_URL"
    else
        echo "[ERROR] Se requiere curl o wget para descargar Python portable."
        exit 1
    fi
    tar -xzf "$TMP_TAR" -C "$RAIZ/runtime"
    rm -f "$TMP_TAR"
else
    echo "[1/3] Python portable ya presente en runtime/python."
fi

echo "[2/3] Instalando dependencias Python..."
"$PY_EMB" -m pip install --upgrade --no-warn-script-location \
    "cryptography>=41.0.0" \
    "psutil>=5.9.0" \
    "fastapi==0.115.4" \
    "uvicorn==0.32.0"

echo "[3/3] Descargando herramientas del bunker (llama-server, ripgrep)..."
PYTHONPATH="$RAIZ/app" "$PY_EMB" -c '
from guarida_manager.downloader.tools import GestorHerramientasBunker

for hid in ("llama-server", "ripgrep"):
    print(f" -> Verificando/descargando {hid}...")
    GestorHerramientasBunker.descargar_y_desplegar(hid)
print("Herramientas listas.")
'

chmod +x "$RAIZ/herramientas/linux/"*.sh
echo ""
echo "[OK] Instalacion completada. Ejecuta ./iniciar_guarida.sh o ./iniciar_web.sh"
