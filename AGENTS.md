# Working on Copyist

**Start with [TASKS.md](TASKS.md)**: the checklist of what is done and what comes next.

Instructions for AI coding agents (Claude, Cursor, anything else) and people picking up this project. Read this first, then SPEC.md, then ROADMAP.md.

## Start here (handoff, 17 October 2026)

The work moved fast and may change hands at any moment. Here is where things stand.

**Done and working** (tests pass: `python -m unittest discover -s tests`, 136 tests):
- Song files become a lead sheet, band score and parts, MIDI, and a validation report.
- 23 styles as data files, with a style gallery.
- Expressive performance.
- The sampled band through sfizz, with stems and a gentle master.
- YuE2 takes that follow the score, checked by `copyist follow`.
- Voice LoRA training on the Mac.
- The local web page (`copyist serve`).
- The Tauri desktop shell.
- MIT licence and GitHub Actions.

**Next, in this order:**
1. **Melody writing:** TASKS.md section 3g, spec in [docs/melody-writing.md](docs/melody-writing.md). Lyrics and a style go in; YuE2's planner (`yue-plan`) writes several melodies; Copyist turns each into a correct song file and the person picks by ear. Built so far (17 October 2026, evening): `copyist/syllables.py`, `copyist/abcplan.py`, `copyist/fit.py`, `copyist/write.py` (`song_from_plan`, the plan-to-song-file core), and the `sections:` / `written_with:` song fields. **Next:** `tests/test_write.py`, then the `copyist write` command loop and CLI, then the page. TASKS.md section 3g has the exact list.
2. **The open singer (plan B):** TASKS.md section 3h, spec in [docs/open-singer.md](docs/open-singer.md). Teach HeartMuLa-oss-3B (Apache-2.0) to follow Copyist's score, using MuLaCover's Apache-2.0 conditioning code and our own training. Start with phase B0 (feasibility).
3. The less-cheesy band preview, the organ and guitar parts, and the music box: TASKS.md section 3f.

**The owner's machine:**
- An M4 Max Mac with 64 GB, the repository at `/Volumes/Code/copyist`, a `.venv` there.
- yue2.cpp built with Metal in `.cache/yue2.cpp/build/` (`yue-synth`, `yue-plan`, `yue-transcribe`, `yue-tokenize`).
- YuE2 weights in `.cache/yue/`.
- Instruments install with `scripts/setup-sfizz.sh --instruments`.
- Run YuE2 with `--device MTL0`.
- GPU work (takes, planning, training) runs there, started by the owner in Terminal or from the page.
- An agent in a cloud container can't use the Mac's GPU. Write scripts and commands for her to run, and say how long they take.

**Never commit:** `voices/`, `.cache/` (weights, LoRAs, instruments), `out/`, or anything from the owner's musical *I Left the Lights On* (`lights-on*` folders). The `lightson` LoRA is private and never ships.

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
scripts/          setup-yue.sh, setup-yue-train.sh, setup-sfizz.sh, setup-demucs.sh, setup-soulx.sh;
                  yue-lora/ (prepare, train, run.sh); instruments/ (manifest.py, clarinet.py)
app/              the desktop app (Tauri), which runs the engine as a sidecar (docs/desktop-app.md)
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

Jessica Mulein (Digital Defiance). She writes lyrics and directs the work through AI tools in short bursts. She can't sing, play an instrument or read music, so melodies and sounds are chosen by listening, so leave the repo in a state where the next person can continue without context: tests passing, roadmap current, no half-finished changes left uncommitted.
