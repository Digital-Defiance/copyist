# Copyist on the desktop

**Goal:** install Copyist like a normal Mac app, open it, and start composing. Optional downloads (band, singer) happen inside the app when you ask for them. Nothing leaves the machine.

Tagline path: **Homebrew → Copyist.app → write a song → download extras as needed.**

## Install (the default path)

When a release is published:

```
brew tap digital-defiance/copyist https://github.com/Digital-Defiance/copyist
brew install --cask copyist
open -a Copyist
```

That installs `Copyist.app` from the GitHub Release DMG (`Casks/copyist.rb`). Songs live in `~/Music/Copyist/`; models and instruments in `~/Library/Application Support/Copyist/`.

Until the first notarized release is up, use the development app (below) or `copyist serve` from a checkout.

## What you do in the app

1. **Write a song** — paste lyrics, pick a style, use Copyist's own writer (no download) or YuE2 when installed. Keep a candidate by ear.
2. **Install extras** (drawer) — download only what you want:
   - **The sampled band** (~1.1 GB) for exact score previews on real instruments;
   - **The singer** (YuE2, ~3.4 GB, licence shown first) for finished takes;
   - **Voice tools** if you train or continue from a recording;
   - **SheetSage2** (~1 GB with MERT; non-commercial only) for the optional more accurate transcriber — also offered on **Transcribe a recording** when it isn't installed yet.
3. **Transcribe** a recording you own (Copyist's own engine needs no download; SheetSage2 installs from the form or Install extras); **try another melody** / edit lyrics on a kept song.
4. **Sound tab** — make a YuE2 take when the singer is installed; check the melody with Demucs + `follow`.

The window is the same local page as `copyist serve` (`copyist/web/static`), with Host/Origin guards. The engine runs as a sidecar on `127.0.0.1`.

## Why local and free

- **YuE2's licence** is CC BY-NC 4.0 with permission for individual creators to sell their songs. Each user downloads the weights; Copyist itself is MIT. Selling the app as a paid product, or running it as a hosted service, would need a separate YuE licence (DECISIONS.md).
- **Privacy** — no account, no upload, no subscription.
- **No servers** — no GPU bill for Digital Defiance.

## Shape

| Piece | Role |
|---|---|
| Tauri 2 shell (`app/`) | Window, starts/stops the engine, opens external links in the browser, one instance only |
| `copyist-engine` sidecar | Frozen Python (`scripts/package/freeze-engine.sh`): serve, build, write, produce, … |
| `yue-synth` / `yue-plan` / … | Bundled when present (`scripts/package/bundle-mac.sh` stages from `.cache/`) |
| `sfizz_render` | Sampled instruments player, same |

Environment the shell sets: `COPYIST_DESKTOP=1`, `COPYIST_HOME` (app data), `COPYIST_BIN` (sidecar folder), and in release mode `--root ~/Music/Copyist` with `--demo` so an empty library gets Amazing Grace.

## Packaging and release

Jessica has **Developer ID Application** certs in the keychain, including **Digital Defiance (`J6887N729S`)** — that identity is the default for shipping. Full steps and env vars: [scripts/package/README.md](../scripts/package/README.md).

```
# One-time: app-specific password + env (never commit):
#   export APPLE_SIGNING_IDENTITY="Developer ID Application: Digital Defiance (J6887N729S)"
#   export APPLE_TEAM_ID=J6887N729S
#   export APPLE_ID=…  APPLE_PASSWORD=…   # app-specific password

scripts/package/freeze-engine.sh          # PyInstaller → binaries/copyist-engine-<triple>
scripts/setup-sfizz.sh                    # recommended: stage sfizz_render
scripts/setup-yue.sh                      # recommended: stage yue-synth / yue-plan
scripts/package/bundle-mac.sh --sign      # signs, notarizes, staples, writes DMG
```

Hardened runtime + entitlements are in `app/src-tauri/entitlements.plist` (sidecars need `disable-library-validation`). After a good DMG: `spctl -a -vv --type install …`, paste SHA-256 into `Casks/copyist.rb`, tag `v0.0.1`.

CI: `.github/workflows/release-mac.yml` builds DMGs on `v*` tags (unsigned until cert secrets are added; signed builds can also be done on this Mac and attached to the release).

## Development (contributors)

```
# From a checkout with .venv already installed:
scripts/package/run-app.sh
# or: cd app && npm install && npm run dev
```

The sidecar scripts in `app/src-tauri/binaries/` are thin wrappers that run `python -m copyist` against `COPYIST_REPO`. First `npm run dev` compiles Rust (a few minutes).

CLI-only path remains supported: `pip install -e .` and `copyist serve` (README).

## Roadmap (milestone D)

1. ~~Engine as sidecar API~~ (`--machine`, `/api/models`, downloads)
2. ~~Tauri shell~~
3. **Packaging** — freeze-engine + bundle-mac + Homebrew cask (this doc); notarized first release still open
4. **First run** — Install extras page; desktop flag; write works without the singer
5. Best of several takes / re-render one section
6. Windows and Linux builds; Tauri updater

## Open questions

- Whether to ship a default voice (never `lightson`; SPEC §6).
- Submitting the cask to `homebrew/homebrew-cask` vs keeping the tap only.
