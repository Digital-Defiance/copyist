# Copyist, the desktop app

The Tauri 2 shell around Copyist ([docs/desktop-app.md](../docs/desktop-app.md)). **This is the product people install** (Homebrew cask → `Copyist.app`). The window loads the engine's page; the engine runs as a sidecar.

## People installing Copyist

```
brew install --cask digital-defiance/tap/copyist
open -a Copyist
```

Apple Silicon, macOS 13 or later; the cask is in [Digital-Defiance/homebrew-tap](https://github.com/Digital-Defiance/homebrew-tap). See the main [README](../README.md) and [docs/desktop-app.md](../docs/desktop-app.md).

## Run it from a checkout (development)

Once on the machine:

```
xcode-select --install                                           # Apple's command-line tools
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # Rust
```

From the repository root (with `.venv` and `pip install -e .` already done):

```
scripts/package/run-app.sh
# or: cd app && npm install && npm run dev
```

The engine uses this checkout (`COPYIST_REPO`), your `songs/` and `.cache/`. The first build compiles Tauri (a few minutes).

## Package a release

Signing uses **Developer ID Application: Digital Defiance (J6887N729S)** (already in the keychain) and notarization an App Store Connect API key in the environment. See [scripts/package/README.md](../scripts/package/README.md).

```
scripts/package/freeze-engine.sh          # → dist/copyist-engine-<triple>
scripts/package/bundle-mac.sh --sign      # signed, notarized, stapled app and DMG
```

The release DMG is built on the Mac and attached with `gh release create`; CI (`.github/workflows/release-mac.yml`) only builds unsigned artifacts. After each release, update the SHA-256 in the tap's `Casks/copyist.rb` (Digital-Defiance/homebrew-tap).

## Layout

```
shell/             start page ("Starting…", or why the engine stopped)
src-tauri/
  src/main.rs      window, sidecar, links, quitting; sets COPYIST_DESKTOP=1
  tauri.conf.json  name, identifier (org.digitaldefiance.copyist), icons, externalBin
  binaries/        copyist-engine-<triple> (the tracked dev script; bundle-mac.sh swaps in the frozen engine during a build)
  icons/
```
