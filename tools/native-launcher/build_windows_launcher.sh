#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GO_BIN="${GO_BIN:-go}"
TOOL_BIN="${KFPS_TOOL_BIN:-$HOME/.cache/kfps-tools/bin}"
RSRC_BIN="${RSRC_BIN:-$TOOL_BIN/rsrc}"
RESOURCE_FILE="$ROOT/tools/native-launcher/rsrc_windows_amd64.syso"

cleanup() {
  rm -f "$RESOURCE_FILE"
}
trap cleanup EXIT

cd "$ROOT"

if [[ ! -x "$RSRC_BIN" ]]; then
  mkdir -p "$TOOL_BIN"
  GOBIN="$TOOL_BIN" "$GO_BIN" install github.com/akavel/rsrc@latest
fi

"$RSRC_BIN" -ico assets/kfps-logo.ico -o "$RESOURCE_FILE"

GO111MODULE=off GOOS=windows GOARCH=amd64 CGO_ENABLED=0 "$GO_BIN" build \
  -trimpath \
  -ldflags "-H=windowsgui -s -w" \
  -o "Kloudys Painter Launcher.exe" \
  ./tools/native-launcher

if strings -a "Kloudys Painter Launcher.exe" | grep -E "PyInstaller|_MEIPASS|Failed to remove temporary directory|pyi-runtime-tmpdir" >/dev/null; then
  echo "Built launcher still contains PyInstaller markers; refusing to continue." >&2
  exit 1
fi

echo "Built native KFPS launcher: $ROOT/Kloudys Painter Launcher.exe"
