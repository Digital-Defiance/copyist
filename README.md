# Copyist

**The song, the score, the sound.**

[Website](https://copyist.digitaldefiance.org/) · [GitHub](https://github.com/Digital-Defiance/copyist)

Copyist writes songs the way a working composer, copyist and band would: it starts from the notes, not from audio. Every song comes out as real, correct music: a lead sheet, a full score, a part for every player, MIDI and MusicXML, and a recording made from those same notes. Because the score is the source of truth, the sheet music always matches what you hear.

Tools like Suno and Mozart AI generate audio first. Their notes don't exist as data, so any sheet music has to be guessed back out of the recording. Copyist works the other way around.

## Install the app (recommended)

On a Mac with Apple Silicon (macOS 13 or later):

```
brew install --cask digital-defiance/tap/copyist
open -a Copyist
```

The cask lives in [Digital Defiance's tap](https://github.com/Digital-Defiance/homebrew-tap) and installs the signed, notarized DMG from the [GitHub release](https://github.com/Digital-Defiance/copyist/releases/latest); you can also download that DMG and drag Copyist to Applications. Intel Macs: run from this repository (below) for now.

That opens the desktop app. **Write a song** from lyrics immediately (Copyist's own writer needs no download). Under **Install extras**, download only what you want: the sampled band for exact previews, the YuE2 singer for finished takes, or SheetSage2 for optional transcription (licences shown first). Songs live in `~/Music/Copyist/`. Details: [docs/desktop-app.md](docs/desktop-app.md).

### Run the app from this repository

For contributors, and on Intel Macs and Linux:

```
git clone --recurse-submodules https://github.com/Digital-Defiance/copyist.git
cd copyist
# if you cloned without submodules: git submodule update --init open-transcriber
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install --no-deps tinysoundfont
scripts/package/run-app.sh          # needs Rust once (see app/README.md)
```

Or open the same UI in a browser without Tauri:

```
copyist serve                       # http://127.0.0.1:8765/
```

## Make some music

In the app (or after `copyist serve`):

1. **Write a song** — paste lyrics, pick a style and writer, listen to each band preview, keep one.
2. **Install extras** — optional band / singer / voice tools.
3. **Try another melody**, **edit by ear** (click a note to hear it, nudge it, pick another chord) or **edit the lyrics** on a kept song; **transcribe** a recording you own.
4. **Sound** — make a YuE2 take when the singer is installed.

From the terminal (same engine):

```
copyist write lyrics.txt --title Hope --style folk --engine rules
copyist write --title Hope --keep 1 --build
copyist build songs/amazing-grace.yaml
```

## Status

Early. Twenty-three styles; sampled band through sfizz; `copyist write` / `rewrite` / `refit` / `transcribe` / `produce` / `follow`; local page and Tauri shell; public site. See [ROADMAP.md](ROADMAP.md) and [TASKS.md](TASKS.md).

## Licence and contributing

Copyist is free and open source under the [MIT licence](LICENSE), stewarded by [Digital Defiance](https://github.com/Digital-Defiance). Contributions welcome — styles, instruments, and packaging especially: [CONTRIBUTING.md](CONTRIBUTING.md).

Downloaded pieces have their own terms (YuE2 CC BY-NC 4.0 with creator sell-through; optional SheetSage2 non-commercial; instruments CC0 / CC BY as credited in each song's report).

## Read next

- [docs/desktop-app.md](docs/desktop-app.md) — Homebrew, packaging, first run
- [docs/web.md](docs/web.md) — the page inside the app
- [docs/hardware.md](docs/hardware.md) — using the CPU, GPU and Neural Engine together; Linux and Windows
- [docs/melody-writing.md](docs/melody-writing.md) — write / rewrite / refit
- [SPEC.md](SPEC.md) · [ROADMAP.md](ROADMAP.md) · [AGENTS.md](AGENTS.md) · [DECISIONS.md](DECISIONS.md)
