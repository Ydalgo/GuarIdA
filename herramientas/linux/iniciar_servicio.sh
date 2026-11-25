#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_EMB="$RAIZ/runtime/python/bin/python3"

if [ ! -x "$PY_EMB" ]; then
    echo "[GuarIdA] No se encontro Python embebido en runtime/python."
    echo "[GuarIdA] Ejecutando instalacion automatica desde cero..."
    bash "$RAIZ/herramientas/linux/instalar_desde_cero.sh"
fi

echo "[GuarIdA] Iniciando como servicio en red local (0.0.0.0:8080)..."
export PYTHONPATH="$RAIZ/app:${PYTHONPATH:-}"
exec "$PY_EMB" "$RAIZ/app/main.py" --web --host 0.0.0.0 --port 8080 --no-browser "$@"
