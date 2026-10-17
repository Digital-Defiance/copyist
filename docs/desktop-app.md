# Copyist on the desktop (plan)

**Goal:** a free, open-source app that people install on their own computer. It writes the song, the score and the sound, with singing that matches or beats Suno, and nothing leaves the machine.

## Why local and free

- **The licence allows it.** YuE2's weights are CC BY-NC 4.0, with a permission for individual creators to sell the songs they make. Each user's app downloads the weights for that user, and Copyist itself is free and open source, so nobody uses the weights commercially. Selling the app, or running it as a paid service, would need a licence from the YuE team (DECISIONS.md).
- **Privacy.** No account, no upload, no subscription. Songs, voices and takes stay on the computer. That's Digital Defiance's line anyway.
- **No servers to run.** There's no GPU bill and nothing to keep up at night.

## Shape

A **Tauri 2** app. Its window is the system webview (WebKit on a Mac) showing the page Copyist already has (`copyist/web/static`). Everything else runs as sidecars, which are programs bundled inside the app:

| Sidecar | What it is | Built with |
|---|---|---|
| `copyist-engine` | the Python engine: `copyist serve` as a local API, plus build, produce, follow | PyInstaller, one per platform |
| `yue-synth`, `yue-tokenize` | yue2.cpp | CMake; Metal on Macs, CUDA or Vulkan elsewhere |
| `sfizz_render` | sfizz (BSD-2-Clause), the player for the sampled instruments | CMake, as `scripts/setup-sfizz.sh` does; about 2 s a part |

The engine picks a free port, prints it, and the window loads the page from it. Tauri starts the engine with the app and stops it on quit. The page's guards (127.0.0.1, Host and Origin checks) stay as they are.

**Models** download on first run into the app's data folder, with a progress screen, checksums and resume:

| Model | Size | Needed for |
|---|---|---|
| YuE2-3B Q6_K | 2.9 GB | every take |
| YuE2 VAE | 0.5 GB | every take |
| realaudio tokenizer + MERT | 0.95 GB | voices and continuation |

**Instruments** download the same way, in packs, from each library's own repository at a pinned commit (docs/sound-set.md). The band (1.1 GB: grand piano, two basses, drums, a melody clarinet) is offered on the Sound tab; more packs follow (orchestra and pit, keys, folk and country, percussion, music box and bells).

**Add-ons** download only when someone asks for them: Demucs (melody checks) and the voice trainer (PyTorch, several GB).

**The library** lives in a folder the person chooses (default `~/Music/Copyist`), not in the code: songs, takes, scores and voices. The engine gets it with `--root`.

## How it beats Suno

1. **Correct sheet music for every take.** The lead sheet, the full score and the parts are what the take plays, by construction.
2. **Exact control.** The melody, lyrics and structure are the person's. Re-render one section (yue2.cpp's continuation) instead of rolling a whole new song.
3. **Best of several, automatically.** Render a few seeds, check each against the score (`copyist follow`) and the lyrics (Whisper), and offer the best ones to listen to. Suno leaves the sorting to you.
4. **Your own voices.** Voice LoRAs trained on the person's own computer (docs/voice-lora.md).
5. **Private and owned.** Nothing uploaded, no terms that claim your output.

Where it may fall short, so measure: speed on smaller machines, the hardware it needs, and whether YuE2 really holds up against Suno for these songs (the YuE team's blind test roughly tied Suno v5, best of 8; we haven't checked).

**Hardware, estimated and to be measured:** Apple Silicon with 16 GB or more; an NVIDIA card with 8 GB or more. CPU-only is too slow (about 13 minutes for a 46-second take on 2 cores).

## Steps (ROADMAP milestone D)

1. **Engine as a sidecar (done, 17 October 2026).** What the app shell uses:
   - Start it with `copyist serve --root LIBRARY --port 0 --machine --demo`. The first line on stdout is JSON, `{"copyist": "ready", "url": …, "port": …, "version": …, "root": …}`; load `url` in the window. `--demo` gives an empty library the Amazing Grace demo.
   - Set `COPYIST_HOME` to the app's data folder (models go in `models/` there) and `COPYIST_BIN` to the folder holding the bundled `yue-synth` and `yue-tokenize`. `copyist/paths.py` says where everything is looked for.
   - `GET /api/health` returns the version, the library and which model groups are installed; `GET /api/models` returns the licence text and each group's files and state.
   - Downloads (`copyist/models.py`) are pinned to a repository revision with each file's size and SHA-256, resume from a `.part` file, and are thrown away if the checksum is wrong. The page asks the person to accept the licence, then shows progress. On the command line, `copyist models` and `copyist models download singer --accept-licence` do the same.
2. **Tauri shell (written and compiling, 17 October 2026; app/README.md).** A start page, the engine started as a sidecar and its page loaded when it's ready, links out opening in the browser, one instance only, the engine stopped on quit. The page gets no Tauri access. It compiles on Linux; the first Mac run is `npm install && npm run dev` in `app/`.
3. **Packaging for the Mac.** Freeze the engine with PyInstaller; build yue2.cpp for Apple Silicon with Metal and `sfizz_render` (`scripts/setup-sfizz.sh` builds it); bundle, sign and notarize. This needs an Apple Developer account ($99 a year, ideally Digital Defiance's).
4. **First run.** Hardware check, model download, and a demo song rendered as the first thing you hear.
5. **Best of several** (step 3 of "How it beats Suno") and **re-rendering one section.**
6. **Writing a song in the app,** after milestones M2 and M3 (song plans and melody proposals).
7. **Windows and Linux** builds (CUDA, Vulkan), and updates through Tauri's updater. No telemetry.

## Open questions

- The licence for Copyist's own code (SPEC section 14); Apache-2.0 suits an app that bundles Apache and MIT parts.
- Whether to ship a voice: only one recorded with a singer's consent, never `lightson` (SPEC section 6).
