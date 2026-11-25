#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_EMB="$RAIZ/runtime/python/bin/python3"

if [ ! -x "$PY_EMB" ]; then
    echo "[GuarIdA] No se encontro Python embebido en runtime/python."
    echo "[GuarIdA] Ejecutando instalacion automatica desde cero..."
    bash "$RAIZ/instalar_desde_cero.sh"
fi

exec "$PY_EMB" "$RAIZ/main.py" "$@"
