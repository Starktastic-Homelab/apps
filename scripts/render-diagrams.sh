#!/usr/bin/env bash
# Render all docs/diagrams/*.d2 to SVG (source-of-truth) + light/dark PNG (README display).
# Browser-free: rasterize via rsvg-convert. D2 runs from a local `d2` binary when present,
# otherwise from the pinned Docker image. Both are pinned to the same version and produce
# byte-identical SVG, so either path is interchangeable (CI is the authoritative renderer).
# The dark PNG uses the dark theme as the PRIMARY theme (--theme 200) so its colours are the
# SVG defaults; rsvg-convert ignores CSS prefers-color-scheme, so --dark-theme would not work.
# Usage: scripts/render-diagrams.sh [--check]
#   --check : after rendering, fail if git working tree shows changes to rendered artifacts.
set -euo pipefail

D2_IMAGE="terrastruct/d2:v0.7.1"
DIAGRAM_DIR="docs/diagrams"
LAYOUT="elk"
PAD="40"

# Prefer a local d2 binary. Falling back to Docker keeps contributors install-free, but a
# local binary avoids Docker's userns file-ownership pitfalls on some workstations.
if command -v d2 >/dev/null 2>&1; then
  d2_run() { d2 "$@"; }
else
  d2_run() { docker run --rm -v "$PWD:/work" -w /work "$D2_IMAGE" "$@"; }
fi

shopt -s nullglob
sources=("${DIAGRAM_DIR}"/*.d2)
if [ ${#sources[@]} -eq 0 ]; then
  echo "No .d2 sources found in ${DIAGRAM_DIR}"; exit 0
fi

render_one() {
  local src="$1" base svg png pngdark
  base="${src%.d2}"
  svg="${base}.svg"; png="${base}.png"; pngdark="${base}-dark.png"

  d2_run --layout "$LAYOUT" --pad "$PAD" --theme 0 "$src" "$svg"
  d2_run --layout "$LAYOUT" --pad "$PAD" --theme 200 "$src" "${base}-dark.svg"

  rsvg-convert "$svg" -o "$png"
  rsvg-convert "${base}-dark.svg" -o "$pngdark"
  rm -f "${base}-dark.svg"   # dark SVG is transient; only dark PNG is committed
  echo "rendered: $svg, $png, $pngdark"
}

for src in "${sources[@]}"; do render_one "$src"; done

if [ "${1:-}" = "--check" ]; then
  # Fail if rendering produced any change — including brand-new (untracked) artifacts,
  # which `git diff` alone would miss.
  if [ -n "$(git status --porcelain -- "${DIAGRAM_DIR}")" ]; then
    echo "ERROR: rendered diagrams are out of date with their .d2 sources:"
    git --no-pager status --short -- "${DIAGRAM_DIR}"
    exit 1
  fi
fi
