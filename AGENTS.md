# Working on Copyist

**Start with [TASKS.md](TASKS.md)**: the checklist of what is done and what comes next.

Instructions for AI coding agents (Claude, Cursor, anything else) and people picking up this project. Read this first, then SPEC.md, then ROADMAP.md.

## Start here (handoff, 19 October 2026)

The work moved fast and may change hands at any moment. Here is where things stand.

**Done and working** (tests pass: `python -m unittest discover -s tests`, 278 tests):
- Song files become a lead sheet, band score and parts, MIDI, and a validation report.
- 23 styles as data files, with a style gallery; styles can cycle a phrase of bars.
- Expressive performance.
- The sampled band through sfizz, with stems and a gentle master. Waltz exact preview is piano-vocal (no clarinet, no drums). Melody voices (fiddle/flute/oboe/sax), guitar staff, celesta.
- YuE2 takes that follow the score, checked by `copyist follow`.
- Voice LoRA training on the Mac.
- The local web page (`copyist serve`).
- The Mac app, shipped as v0.0.1 (Apple Silicon): `brew install --cask digital-defiance/tap/copyist`. The cask lives in Digital-Defiance/homebrew-tap (`/Volumes/Code/homebrew-tap` on the Mac); the signed, notarized DMG is on the GitHub release. Release steps: scripts/package/README.md. Install extras in the UI.
- MIT licence. GitHub Actions workflows exist (tests; an unsigned Mac build that never touches releases), but GitHub CI isn't tracked as a gate for now: the local suite is.
- `copyist write` (YuE2 plan or `--engine rules`), `copyist rewrite` (again / higher / simpler) and `copyist transcribe`. Mac write timed: ~8 s a candidate on MTL0.
- `copyist import` (MusicXML → song file). Round-trip table includes Saints, Silent Night, Amazing Grace, Tyger and Major-General (~128 notes; truth take in `out/major-general/takes/truth/` on the Mac).
- Public site in `site/` → https://copyist.digitaldefiance.org/

**Next, in this order:**
1. **Transcribing recordings:** TASKS.md section 7 — open-transcriber + `--engine neural` (BP/`clean_notes`): note table mean ~0.88 vs open 0.83, Saints/AG gaps closed (0.85 tied, 0.89 vs 0.88); Major-General 0.83 vs open 0.84 (121 of 128 notes). Full `roundtrip.py --engine neural` mean 0.87 vs 0.83, losing only Silent Night (0.78 vs 0.80): next is its 6/8 rhythm snapping. SheetSage2, as a yardstick only, scores 0.97 notes / 0.88 chords on the same five takes (2026-10-19): that's the gap to close. Fix the key-change bug in the ABC readers (TASKS §7) before the big songs. Owner songs only after a table win.
   - Two big public-domain songs for the round-trip set (TASKS.md §7), chosen to add what the five lack: a minor key, a key change, syncopation, richer harmony, 12/8 or a brisk 6/8, a wide range, held notes, a repeated chorus. Open-ended research runs kept failing with the API error "Improperly formed request", so pick the songs directly and give each song its own small steps.
   - T1: train the neural transcriber, soon after the non-training passes run out. Plan written 2026-10-19 (summary in TASKS.md §7; full local report in `.agents/tasks/t1-training-plan-2026-10-19/`). Owner decided 2026-10-19: build on Basic Pitch + SoulX, Mac only, MIT weights, run SheetSage once on all seven test songs as a yardstick, and YuE2 renders of sampler scores may be training material (second round, gated, melody only, a separate tagged slice). YuE2 was trained on SheetSage2's transcriptions, so YuE2 takes can't be what judges "better than SheetSage2": real recordings must. The T1a data foundation landed (held-out guard, score sampler; open-transcriber 2f90e7f). New goal from the owner: the open transcriber must be the best available and beat SheetSage2 objectively, for songs, musicals and orchestral music. The design audit is done (local report `.agents/tasks/open-transcriber-audit-2026-10-19/report.md`; summary in TASKS §7). T1 is re-scoped to an encoder bake-off plus multi-task heads and structured decoding. The judge becomes real, licence-clean recordings (SheetSage2's own tests and a frozen public-domain set, COTB-v1), not YuE2 takes. Stage 0a, the first honest scoreboard against SheetSage2 on real recordings, is under way (worktree `.worktrees/stage0-scoreboard`). The owner approved two things: a ready-made "ear", which the bake-off picks, and the `copyist-song/1` upgrade. Note that music21 10.5 drops inline `[K:]`. GPU time comes in windows she agrees to, since the Mac is her laptop (see "The owner's machine"). The budget is $0: free downloads only, nothing bought. It must fit on the Mac's disk: about 300 GB at most while training and testing, then about 15 GB long term (stage 6). Non-commercial test songs are for testing only: never trained on, shipped or shared, and only their scores and credits are published. `songs/` and the round-trip cases are held out: never train on them.
2. **Less-cheesy exact previews (rest of 3f):** crank/comb music box when a CC0 set can be hosted (celesta is in).
3. **The open singer (plan B):** TASKS.md section 3h, spec in [docs/open-singer.md](docs/open-singer.md). Start with phase B0 (feasibility).
4. **The Mac app's next release:** TASKS.md §3d — an Intel build, then CI signing.

**The owner's machine:**
- An M4 Max Mac with 64 GB, the repository at `/Volumes/Code/copyist`, a `.venv` there.
- yue2.cpp built with Metal in `.cache/yue2.cpp/build/` (`yue-synth`, `yue-plan`, `yue-transcribe`, `yue-tokenize`).
- YuE2 weights in `.cache/yue/`.
- Instruments install with `scripts/setup-sfizz.sh --instruments` (band), `copyist models download keys` / `bells` / `folk` / `electric` / `winds` (organ, harp, tonewheel, celesta, music-box glock, guitars, fiddle, flute, oboe, sax).
- Run YuE2 with `--device MTL0`.
- GPU work (takes, planning, training) runs there. The Mac is the owner's laptop, so GPU time comes in windows she agrees to (owner, 2026-10-19).
  - **Before any GPU job longer than about 15 minutes,** ask her, through the orchestrator if you're a workflow step. Say what the job is, roughly how many hours it needs, and the earliest it could start. For that window she keeps the Mac plugged in with the lid open.
  - **Agents start and watch the jobs; she doesn't.** One GPU job at a time.
  - **Every long job must:** resume from checkpoints, pause while the Mac is on battery (`pmset -g batt`) and resume on AC, and keep the Mac awake with `caffeinate -i` while it runs. She also uses Amphetamine to keep it awake.
- An agent in a cloud container can't use the Mac's GPU. Write the scripts, say how long they take, and leave the run to an agent on the Mac, not to the owner.

**Never commit:** `voices/`, `.cache/` (weights, LoRAs, instruments), `out/`, or anything from the owner's musical *I Left the Lights On* (`lights-on*` folders). The `lightson` LoRA is private and never ships.

**SheetSage never touches the owner's songs** (owner, 2026-10-19). That covers *I Left the Lights On*, her second musical and anything else of hers. Never run SheetSage on them, not even as a yardstick, and never keep or use SheetSage output for them. Her lead sheets come only from Copyist's own engines. SheetSage stays a yardstick on public test sets only.

**The owner's goal** (2026-10-19). Everything else serves these two parts:
1. **Lights On.** Her musical exists only as audio demos, with no sheet music: a black box. Transcribe the demos into lead sheets. Reproduce them with YuE2 from those lead sheets, as close to the demos as can be measured: transcribe, render, measure, refine. Then make lead sheets and orchestra arrangements from them. This waits for Copyist's own engine, because she won't have it done with SheetSage. Build and test the loop on public-domain music in the meantime.
2. **Her second musical,** written from scratch with Copyist.

## The project in one paragraph

Copyist makes songs score-first: a song file (YAML with an ABC melody, chord symbols and lyrics) becomes a canonical music21 score, which is validated, arranged, engraved to PDF and MusicXML, exported to MIDI and rendered to audio. The score is always the source of truth; audio is derived from it, never the other way around. Tagline: *the song, the score, the sound.*

## How to pick up work

1. Read TASKS.md and ROADMAP.md. Take the first unchecked item in the section the owner (Jessica) last asked for (see "Start here"), or the first unchecked item in the current milestone.
2. If the item is unclear, write your interpretation into the item before starting.
3. Do the work in a small, reviewable change. Add or update tests.
4. Run the checks below. Open and look at any PDF you changed; a score that builds but looks wrong is not done.
5. Tick the item in ROADMAP.md, add a line to DECISIONS.md if you made a design choice, and commit.

## Commands

```
pip install -e .                          # install (Python 3.10+)
pip install --no-deps tinysoundfont       # audio (its PyAudio dependency is only for live playback)
copyist build songs/amazing-grace.yaml    # build every output into out/amazing-grace/
copyist build songs/amazing-grace.yaml --images   # also PNGs of every PDF page, for checking by eye
copyist check songs/amazing-grace.yaml    # run validators only
copyist sing songs/amazing-grace.yaml --bars 0-4   # sung vocal (needs SoulX-Singer; docs/singing.md)
copyist produce songs/amazing-grace.yaml           # YuE2 production from the score (docs/production.md)
copyist follow songs/amazing-grace.yaml VOCAL.wav # does a recording sing the melody? (timing and octave allowed)
copyist import score.musicxml -o songs/foo.yaml    # MusicXML lead sheet → song file
copyist serve                                      # the web front end (docs/web.md)
copyist gallery songs/when-the-saints.yaml         # the song in every style that fits it (docs/styles.md)
python -m unittest discover -s tests      # tests
```

For the band's sound, `scripts/setup-sfizz.sh --instruments` builds the sampled-instrument player and downloads the band (about 1.1 GB). Without them, the first build downloads the GeneralUser GS SoundFont (about 32 MB) into `.cache/` and plays that instead.

## Layout

```
copyist/          the package
  song.py         load and parse song files into a music21 score (melody, chords, lyrics)
  lyrics.py       syllable parsing and alignment
  validate.py     validators (SPEC section 5)
  arrange.py      arrangement templates (SPEC section 7), playing the song's style
  styles/         one YAML file per style, and the loader (docs/styles.md)
  gallery.py      a song played in every style that fits it
  drums.py        drum grooves, fills and crashes; notation and MIDI from one list of hits
  engrave.py      MusicXML, SVG and PDF output via Verovio and PyMuPDF
  musicxml_in.py  MusicXML → song file (`copyist import`)
  perform.py      expressive performance: the arrangement MIDI played, not just written
  render.py       the band: each part on its sampled instrument (sfizz), SoundFont fallback; a sung vocal over the band
  mixdown.py      loudness (BS.1770), the shared room, the gentle master, WAV in and out
  instruments.py  the sampled instruments: catalog, packs, verified downloads (docs/sound-set.md)
  sound/          the instrument manifest (git object ids) and Copyist's own clarinet SFZ
  models.py       the YuE2 models: catalog and verified downloads
  paths.py        where the data folder, models and programs are
  sing.py         voice part → SoulX-Singer input; runs the model (docs/singing.md)
  pitch.py        sung pitch vs the score, note by note
  hear.py         Whisper transcription of a vocal vs the lyrics
  yue.py          the score as YuE2's ABC, and the call to yue-synth (docs/production.md)
  stems.py        separating a recording's vocal with Demucs
  lora.py         training data for a YuE2 voice LoRA (docs/voice-lora.md)
  voiceprompt.py  a SoulX voice from a recording
  web/            `copyist serve`: server.py and the page in static/ (docs/web.md)
  cli.py          the `copyist` command
songs/            song files (public domain or original only)
tests/            unittest tests
docs/             production.md, voice-lora.md, web.md, singing.md, sound-set.md, styles.md, desktop-app.md,
                  default-voices.md
site/             the public GitHub Pages site (static HTML: advert, features, install)
scripts/          setup-yue.sh, setup-yue-train.sh, setup-sfizz.sh, setup-demucs.sh, setup-soulx.sh;
                  yue-lora/ (prepare, train, run.sh); instruments/ (manifest.py, clarinet.py)
app/              the desktop app (Tauri), which runs the engine as a sidecar (docs/desktop-app.md)
open-transcriber/ git submodule: neural lead-sheet AMT (docs/open-transcriber.md); `git submodule update --init`
out/              build output (ignored)
.cache/           downloaded assets (ignored)
```

## Rules

- **The score is the source of truth.** Never derive notes from audio except in the verification step.
- **Deterministic builds.** The same song file must produce the same outputs. No randomness without a seed recorded in the output.
- **Every validator has tests,** including one input that should fail.
- **No copyrighted music in the repo.** Test songs must be public domain or written for the project. Check dates: published before 1929 in the US.
- **Don't change the song format** without bumping its version in SPEC.md section 4 and providing a converter.
- **Keep docs current.** If you change behavior described in SPEC.md, update SPEC.md in the same commit.
- **Small commits,** with messages that say what changed and why.
- **Look at the output.** Render the PDF pages to images and check them: lyrics under the right notes, chord symbols above the staff, nothing colliding, parts in the right clef and transposition.

## Style

- Python 3.10+, standard library plus the dependencies in pyproject.toml. Type hints on public functions.
- Plain names; short functions; docstrings that say what and why.
- User-facing messages in plain English, with bar and beat numbers for anything musical.

## Owner

Jessica Mulein (Digital Defiance). She writes lyrics and directs the work through AI tools in short bursts. She can't sing, play an instrument or read music, so melodies and sounds are chosen by listening. Nothing may wait on her listening, hands-on work or time (2026-10-19): make every check automatic, run the jobs yourself, and ask her only for decisions. Leave the repo in a state where the next person can continue without context: tests passing, roadmap current, no half-finished changes left uncommitted.
