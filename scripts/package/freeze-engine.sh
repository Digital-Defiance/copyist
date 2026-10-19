#!/usr/bin/env bash
# Freeze the Copyist engine with PyInstaller for the Tauri sidecar (docs/desktop-app.md).
# Writes app/src-tauri/binaries/copyist-engine-<rust-triple> as a single executable.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

triple="${1:-}"
if [[ -z "$triple" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) triple=aarch64-apple-darwin ;;
    Darwin-x86_64) triple=x86_64-apple-darwin ;;
    Linux-x86_64) triple=x86_64-unknown-linux-gnu ;;
    Linux-aarch64) triple=aarch64-unknown-linux-gnu ;;
    *) echo "Pass a Rust target triple, e.g. aarch64-apple-darwin" >&2; exit 1 ;;
  esac
fi

py="${COPYIST_PYTHON:-$root/.venv/bin/python}"
[[ -x "$py" ]] || py="$(command -v python3)"

# This checkout's .venv is often made with `uv` and has no pip module. Prefer uv;
# otherwise bootstrap pip, then install.
pip_install() {
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$py" "$@"
  else
    if ! "$py" -m pip --version >/dev/null 2>&1; then
      "$py" -m ensurepip --upgrade
    fi
    "$py" -m pip install "$@"
  fi
}

pip_install -e "$root"
pip_install "pyinstaller>=6.3"
# tinysoundfont pulls PyAudio (needs PortAudio); we only need the SoundFont player.
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$py" --no-deps tinysoundfont || true
else
  "$py" -m pip install --no-deps tinysoundfont || true
fi

out="$root/dist/engine"
rm -rf "$out"
mkdir -p "$out" "$root/app/src-tauri/binaries"

echo "Freezing copyist-engine for $triple (onefile; a few minutes)…"
# Use engine_entry.py (absolute imports). Freezing copyist/__main__.py breaks
# relative imports: PyInstaller runs it as a bare __main__ script.
# cmudict (via pronouncing) calls importlib.metadata.version at import — need
# its dist-info in the bundle or the sidecar dies before serve starts.
"$py" -m PyInstaller \
  --noconfirm --clean --onefile --name copyist-engine \
  --distpath "$out" --workpath "$out/build" --specpath "$out" \
  --paths "$root" \
  --collect-all copyist \
  --collect-all music21 \
  --collect-all verovio \
  --collect-all cmudict \
  --collect-all pronouncing \
  --copy-metadata cmudict \
  --copy-metadata pronouncing \
  --hidden-import copyist \
  --hidden-import copyist.cli \
  --console \
  "$root/scripts/package/engine_entry.py"

bin="$out/copyist-engine"
[[ -f "$bin" ]] || bin="$out/copyist-engine.exe"
[[ -f "$bin" ]] || { echo "PyInstaller did not write $out/copyist-engine" >&2; exit 1; }

dest="$root/app/src-tauri/binaries/copyist-engine-$triple"
cp "$bin" "$dest"
chmod +x "$dest"
echo "Wrote $dest ($(du -h "$dest" | awk '{print $1}'))"
echo "Next: scripts/package/bundle-mac.sh"
