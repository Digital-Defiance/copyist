#!/usr/bin/env bash
# Build sfizz_render, the player for Copyist's sampled instruments, into .cache/sfizz/.
# Usage: scripts/setup-sfizz.sh [--instruments]
#   --instruments  also download the band instruments (about 1.1 GB), as `copyist models download band` does.
# Needs git and a C++17 compiler (on a Mac: xcode-select --install). CMake and Ninja are fetched
# into a private folder if they aren't installed. The desktop app bundles sfizz_render instead.
set -euo pipefail

SFIZZ_REPO=https://github.com/sfztools/sfizz.git
SFIZZ_REV=f5c6e29f23b8057867c08e88f5f6ac6738baa30b      # develop, 2026; BSD-2-Clause

root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/.cache/sfizz-src"
dest="$root/.cache/sfizz"
tools="$root/.cache/build-tools"

if [ ! -x "$dest/sfizz_render" ]; then
  if [ ! -d "$src/.git" ]; then
    git clone --filter=blob:none --no-checkout "$SFIZZ_REPO" "$src"
  fi
  git -C "$src" fetch --filter=blob:none origin "$SFIZZ_REV" 2>/dev/null || true
  git -C "$src" checkout -q "$SFIZZ_REV"
  git -C "$src" submodule update --init --recursive --depth 1

  cmake=$(command -v cmake || true)
  ninja=$(command -v ninja || true)
  if [ -z "$cmake" ] || [ -z "$ninja" ]; then
    if [ ! -x "$tools/bin/cmake" ] || [ ! -x "$tools/bin/ninja" ]; then
      python3 -m venv "$tools"
      "$tools/bin/pip" install --quiet cmake ninja
    fi
    cmake="$tools/bin/cmake"
    ninja="$tools/bin/ninja"
  fi

  extra=()
  if [ "$(uname)" = "Darwin" ]; then
    extra+=(-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0)
  fi
  "$cmake" -S "$src" -B "$src/build" -G Ninja -DCMAKE_MAKE_PROGRAM="$ninja" \
    -DCMAKE_BUILD_TYPE=Release -DSFIZZ_RENDER=ON -DSFIZZ_JACK=OFF -DSFIZZ_SHARED=OFF \
    -DSFIZZ_USE_SNDFILE=OFF -DSFIZZ_TESTS=OFF -DSFIZZ_DEMOS=OFF -DSFIZZ_DEVTOOLS=OFF \
    -DSFIZZ_BENCHMARKS=OFF -DENABLE_LTO=OFF ${extra[@]+"${extra[@]}"}
  "$cmake" --build "$src/build" --target sfizz_render
  mkdir -p "$dest"
  cp "$(find "$src/build" -type f -name sfizz_render -perm -u+x | head -1)" "$dest/sfizz_render"
fi
"$dest/sfizz_render" --help > /dev/null
echo "sfizz_render is ready: $dest/sfizz_render"

if [ "${1:-}" = "--instruments" ]; then
  py="${PYTHON:-python3}"
  if [ -x "$root/.venv/bin/python" ]; then
    py="$root/.venv/bin/python"
  fi
  ( cd "$root" && "$py" -m copyist models download band )
fi
