# Packaging Copyist for the Mac

Ship path: freeze the engine → build signed/notarized `.dmg` → GitHub Release → Homebrew cask.

Jessica has a Developer ID (Digital Defiance team `J6887N729S` and a personal one). Use the **Digital Defiance** identity for releases.

## One-time Apple setup

1. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/certificates/list), ensure **Developer ID Application** exists for Digital Defiance (it does on this Mac).
2. Create an [app-specific password](https://appleid.apple.com/account/manage) for notarization (label it `copyist-notarize`).
3. Put secrets in your shell profile or a local env file that is **never committed** (e.g. `~/.config/copyist/notarize.env`):

```bash
export APPLE_SIGNING_IDENTITY="Developer ID Application: Digital Defiance (J6887N729S)"
export APPLE_TEAM_ID=J6887N729S
export APPLE_ID="you@example.com"          # the Apple ID on the Digital Defiance team
export APPLE_PASSWORD="xxxx-xxxx-xxxx-xxxx" # app-specific password
```

```bash
source ~/.config/copyist/notarize.env
```

App Store Connect API key works instead of `APPLE_ID` / `APPLE_PASSWORD`:

```bash
export APPLE_API_ISSUER="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export APPLE_API_KEY="XXXXXXXXXX"
export APPLE_API_KEY_PATH="$HOME/.appstoreconnect/AuthKey_XXXXXXXXXX.p8"
export APPLE_TEAM_ID=J6887N729S
```

## Build a distributable DMG on this Mac

```bash
# From the repo root, with .venv installed:
scripts/package/freeze-engine.sh                 # several minutes; ~100MB+ binary
# Optional but recommended for a useful app:
#   scripts/setup-sfizz.sh && scripts/setup-yue.sh
scripts/package/bundle-mac.sh --sign
```

Tauri signs the app and sidecars, notarizes with Apple, staples the ticket, and writes a DMG under:

`app/src-tauri/target/release/bundle/dmg/`

Check:

```bash
spctl -a -vv --type install path/to/Copyist_*.dmg
shasum -a 256 path/to/Copyist_*.dmg   # paste into Casks/copyist.rb
```

## Publish

1. Tag and push (or attach the DMG to a release manually):

```bash
git tag v0.0.1
git push origin v0.0.1
```

2. Upload arm64 (and later x64) DMGs to the GitHub Release if CI did not.
3. Update `version` and `sha256` in `Casks/copyist.rb`.
4. Users install with:

```bash
brew tap digital-defiance/copyist https://github.com/Digital-Defiance/copyist
brew install --cask copyist
```

## CI signing (later)

`.github/workflows/release-mac.yml` currently builds unsigned artifacts for smoke tests. To sign in GitHub Actions, add repository secrets:

| Secret | Contents |
|---|---|
| `APPLE_CERTIFICATE` | Base64 of a .p12 exporting the Developer ID Application cert + key |
| `APPLE_CERTIFICATE_PASSWORD` | Password for that .p12 |
| `APPLE_ID` / `APPLE_PASSWORD` / `APPLE_TEAM_ID` | Or the API key trio |

Then flip the workflow to import the cert and run `bundle-mac.sh --sign`. Prefer building signed releases on this Mac until CI secrets are set.

## Dev without signing

```bash
scripts/package/run-app.sh
```

Smoke-test the frozen sidecar without the window:

```bash
app/src-tauri/binaries/copyist-engine-aarch64-apple-darwin --help
COPYIST_DESKTOP=1 COPYIST_HOME=/tmp/copyist-home \
  app/src-tauri/binaries/copyist-engine-aarch64-apple-darwin \
  serve --root /tmp/copyist-lib --port 8769 --machine --demo
# expect a JSON "ready" line; curl http://127.0.0.1:8769/api/health
```

If the app says the engine stopped: quit and reopen after `freeze-engine.sh`. Known freeze bugs already fixed in that script — relative imports (`engine_entry.py`) and missing `cmudict` package metadata.
