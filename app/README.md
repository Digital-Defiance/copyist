# Copyist, the desktop app

The Tauri 2 shell around Copyist ([docs/desktop-app.md](../docs/desktop-app.md)). **This is the product people install** (Homebrew cask → `Copyist.app`). The window loads the engine's page; the engine runs as a sidecar.

## People installing Copyist

```
brew tap digital-defiance/copyist https://github.com/Digital-Defiance/copyist
brew install --cask copyist
open -a Copyist
```

See the main [README](../README.md) and [docs/desktop-app.md](../docs/desktop-app.md).

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

Signing uses **Developer ID Application: Digital Defiance (J6887N729S)** (already in the keychain). See [scripts/package/README.md](../scripts/package/README.md) for the app-specific password.

```
source ~/.config/copyist/notarize.env     # APPLE_ID, APPLE_PASSWORD, TEAM_ID, …
scripts/package/freeze-engine.sh
scripts/package/bundle-mac.sh --sign      # notarized DMG
```

CI builds DMGs on `v*` tags (`.github/workflows/release-mac.yml`). Update SHA-256 in `Casks/copyist.rb` after each release.

## Layout

```
shell/             start page ("Starting…", or why the engine stopped)
src-tauri/
  src/main.rs      window, sidecar, links, quitting; sets COPYIST_DESKTOP=1
  tauri.conf.json  name, identifier (org.digitaldefiance.copyist), icons, externalBin
  binaries/        copyist-engine-<triple> (dev script or frozen binary)
  icons/
```
