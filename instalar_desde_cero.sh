#!/usr/bin/env bash
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$RAIZ/scripts/instalar_unix.sh" "$@"
