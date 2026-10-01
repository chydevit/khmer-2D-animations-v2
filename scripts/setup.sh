#!/bin/bash
# One-time setup / health check for the khmer-2d-animation skill (macOS, Apple Silicon or Intel).
set -u
SK="$(cd "$(dirname "$0")/.." && pwd)"
ok() { printf "  [ok] %s\n" "$1"; }
bad() { printf "  [!!] %s\n" "$1"; FAIL=1; }
FAIL=0
echo "khmer-2d-animation setup ($SK)"

command -v ffmpeg >/dev/null && ok "ffmpeg" || bad "ffmpeg missing: brew install ffmpeg"
command -v pango-view >/dev/null && ok "pango-view (Khmer text shaping)" || bad "pango missing: brew install pango"
[ -e /opt/homebrew/lib/libcairo.2.dylib ] || [ -e /usr/local/lib/libcairo.2.dylib ] && ok "cairo" || bad "cairo missing: brew install cairo"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3.10)
[ -n "$PY" ] && ok "python: $PY" || bad "python 3.10-3.12 needed: brew install python@3.12"

if [ ! -x "$SK/.venv/bin/python" ]; then
  echo "  creating render venv..."
  "$PY" -m venv "$SK/.venv" && "$SK/.venv/bin/pip" install -q --upgrade pip
fi
"$SK/.venv/bin/pip" install -q cairocffi numpy scipy soundfile edge-tts pillow 2>&1 | grep -v notice
"$SK/.venv/bin/python" -c "import cairocffi, numpy, scipy, soundfile, edge_tts" && ok "render venv" || bad "render venv broken"

if [ "${SKIP_VOX:-0}" != "1" ]; then
  if [ ! -x "$SK/.venv-vox/bin/python" ]; then
    echo "  creating VoxCPM venv (PyTorch, ~2 GB)..."
    "$PY" -m venv "$SK/.venv-vox" && "$SK/.venv-vox/bin/pip" install -q --upgrade pip
    "$SK/.venv-vox/bin/pip" install -q voxcpm soundfile 2>&1 | grep -v notice
  fi
  "$SK/.venv-vox/bin/python" -c "import voxcpm, torch; print('  torch', torch.__version__, 'mps', torch.backends.mps.is_available())" \
    && ok "VoxCPM venv" || bad "VoxCPM venv broken (use --engine edge meanwhile)"
  echo "  checking VoxCPM2 model (downloads ~5 GB the first time)..."
  "$SK/.venv-vox/bin/python" -c "from huggingface_hub import snapshot_download; print('  model:', snapshot_download('openbmb/VoxCPM2'))" \
    && ok "VoxCPM2 model" || bad "VoxCPM2 model download failed"
fi

fc-list 2>/dev/null | grep -qi "khmer" || ls /System/Library/Fonts/Supplemental/ | grep -qi "Khmer Sangam" && ok "Khmer font (Khmer Sangam MN)" || bad "no Khmer font found"
pango-view --no-display --pixels --font="Khmer Sangam MN Bold 40px" --text "សួស្តី" -o /tmp/kh2d_font_test.png >/dev/null 2>&1 \
  && ok "Khmer text renders" || bad "pango could not render Khmer"
[ $FAIL = 0 ] && echo "ready." || echo "fix the [!!] items above."
