#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$RAIZ/herramientas/linux/instalar_unix.sh" "$@"
