# Working on Copyist

Instructions for AI coding agents and people picking up this project. Read this first, then SPEC.md, then ROADMAP.md.

## The project in one paragraph

Copyist makes songs score-first: a song file (YAML with an ABC melody, chord symbols and lyrics) becomes a canonical music21 score, which is validated, arranged, engraved to PDF and MusicXML, exported to MIDI and rendered to audio. The score is always the source of truth; audio is derived from it, never the other way around. Tagline: *the song, the score, the sound.*

## How to pick up work

1. Read ROADMAP.md. Take the first unchecked item in the current milestone, unless the owner (Jessica) has said otherwise.
2. If the item is unclear, write your interpretation into the item before starting.
3. Do the work in a small, reviewable change. Add or update tests.
4. Run the checks below. Open and look at any PDF you changed; a score that builds but looks wrong is not done.
5. Tick the item in ROADMAP.md, add a line to DECISIONS.md if you made a design choice, and commit.

## Commands

```
pip install -e .                          # install (Python 3.10+)
copyist build songs/amazing-grace.yaml    # build every output into out/amazing-grace/
copyist check songs/amazing-grace.yaml    # run validators only
python -m unittest discover -s tests      # tests
```

The first build downloads the GeneralUser GS SoundFont (about 32 MB) into `.cache/`.

## Layout

```
copyist/          the package
  song.py         load and parse song files into a music21 score (melody, chords, lyrics)
  lyrics.py       syllable parsing and alignment
  validate.py     validators (SPEC section 5)
  arrange.py      arrangement templates (SPEC section 7)
  engrave.py      MusicXML, SVG and PDF output via Verovio and PyMuPDF
  render.py       MIDI to WAV via TinySoundFont
  cli.py          the `copyist` command
songs/            song files (public domain or original only)
tests/            unittest tests
docs/             longer design notes
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

Jessica Mulein (Digital Defiance). She writes melodies and lyrics and directs the work through AI tools in short bursts, so leave the repo in a state where the next person can continue without context: tests passing, roadmap current, no half-finished changes left uncommitted.
