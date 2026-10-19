# Packaging Copyist for the Mac

Ship path: freeze the engine → build a signed, notarized, stapled `.dmg` on this Mac → GitHub Release → the cask in Digital Defiance's tap ([Digital-Defiance/homebrew-tap](https://github.com/Digital-Defiance/homebrew-tap), `Casks/copyist.rb`).

Jessica has a Developer ID (Digital Defiance team `J6887N729S` and a personal one). Use the **Digital Defiance** identity for releases.

## One-time Apple setup

1. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/certificates/list), ensure **Developer ID Application** exists for Digital Defiance (it does on this Mac).
2. Notarization credentials in the shell environment, **never committed**. An App Store Connect API key (preferred; this Mac has one):

```bash
export APPLE_SIGNING_IDENTITY="Developer ID Application: Digital Defiance (J6887N729S)"
export APPLE_TEAM_ID=J6887N729S
export APPLE_API_ISSUER="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export APPLE_API_KEY="XXXXXXXXXX"
export APPLE_API_KEY_PATH="$HOME/.appstoreconnect/AuthKey_XXXXXXXXXX.p8"
```

Or an Apple ID with an [app-specific password](https://appleid.apple.com/account/manage) instead of the key: `APPLE_ID` and `APPLE_PASSWORD`. When the key is set, `bundle-mac.sh` uses it and ignores `APPLE_ID`. `notarize.env.example` lists the same variables.

## Build a distributable DMG on this Mac

```bash
# From the repo root, with .venv installed:
scripts/package/freeze-engine.sh          # about 1 minute; writes dist/copyist-engine-<triple> (~200 MB)
# Optional but recommended for a useful app:
#   scripts/setup-sfizz.sh && scripts/setup-yue.sh
scripts/package/bundle-mac.sh --sign      # about 3 minutes, most of it Apple's notary service
```

`bundle-mac.sh --sign`:
- copies the frozen engine over the tracked placeholder in `app/src-tauri/binaries/` for the build and puts the placeholder back when it exits, so `git status` stays empty;
- stages `yue-*` and `sfizz_render` from `.cache/` (gitignored) and lists them for Tauri in a temporary `--config` file, not in `tauri.conf.json`;
- has Tauri sign every binary (Developer ID, hardened runtime, secure timestamp), notarize the app and staple it;
- notarizes and staples the DMG itself, then prints its `spctl` check and SHA-256.

The DMG is `app/src-tauri/target/release/bundle/dmg/Copyist_<version>_aarch64.dmg`. The engine leaves out the neural transcriber (TensorFlow would double its size; DECISIONS.md).

Check:

```bash
codesign --verify --deep --strict --verbose=2 app/src-tauri/target/release/bundle/macos/Copyist.app
spctl -a -vv app/src-tauri/target/release/bundle/macos/Copyist.app     # Notarized Developer ID
spctl -a -vv -t install path/to/Copyist_*.dmg
xcrun stapler validate path/to/Copyist_*.dmg
```

Then mount the DMG, open Copyist from it, and check the window, the page, Install extras, and that quitting stops `copyist-engine`.

## Publish

1. Tag the commit the DMG was built from, and push:

```bash
git tag -a v0.0.1 -m "Copyist 0.0.1"
git push origin main v0.0.1
```

2. Make the release with the notarized DMG (`release-mac.yml` doesn't touch releases):

```bash
gh release create v0.0.1 path/to/Copyist_0.0.1_aarch64.dmg --verify-tag --title "Copyist 0.0.1" --notes "…"
```

3. Download the asset and check its SHA-256 matches.
4. In `/Volumes/Code/homebrew-tap`, update `version` and `sha256` in `Casks/copyist.rb`, commit ("copyist X.Y.Z: notarized DMG sha256"), push, then `brew update && brew fetch --cask digital-defiance/tap/copyist && brew audit --cask --online digital-defiance/tap/copyist`.
5. People install with:

```bash
brew install --cask digital-defiance/tap/copyist
```

## CI

`.github/workflows/release-mac.yml` runs on `v*` tags and by hand. It freezes and bundles unsigned arm64 and Intel DMGs, checks the checkout stays clean, and uploads them as workflow artifacts. It never uploads to the GitHub Release. Signing in CI (an `APPLE_CERTIFICATE` .p12 secret plus the API key) is a later option; until then sign on this Mac.

## Dev without signing

```bash
scripts/package/run-app.sh
```

Smoke-test the frozen sidecar without the window:

```bash
dist/copyist-engine-aarch64-apple-darwin --version
COPYIST_DESKTOP=1 COPYIST_HOME=/tmp/copyist-home \
  dist/copyist-engine-aarch64-apple-darwin \
  serve --root /tmp/copyist-lib --port 0 --machine --demo
# expect a JSON "ready" line with the port; curl http://127.0.0.1:<port>/api/health
```

If the app says the engine stopped: quit and reopen after `freeze-engine.sh`. Known freeze bugs already fixed in that script: relative imports (`engine_entry.py`) and missing `cmudict` package metadata.
