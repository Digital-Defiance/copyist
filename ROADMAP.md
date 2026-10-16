# Roadmap

Take the first unchecked item in the current milestone. Tick items when they're done and tested. Milestone definitions are in SPEC.md section 10.

## M0: Walking skeleton (done 2026-10-16)

- [x] Project docs: README, SPEC, AGENTS, ROADMAP, DECISIONS
- [x] Packaging: pyproject.toml with the `copyist` command
- [x] Song file loader: YAML + ABC melody + chord symbols → music21 score
- [x] Lyric parsing and alignment (hyphens, `_` melisma, `*` skip, ties and rests skipped, multiple verses)
- [x] Validators: `bars`, `lyrics-fit`, `range`, `chord-tones`, `prosody`, `key`
- [x] Validation report (Markdown) with bar and beat for every finding
- [x] Engraving: lead sheet MusicXML → SVG (Verovio) → PDF (PyMuPDF), title and credits on page 1
- [x] MIDI export
- [x] Demo audio: MIDI → WAV with TinySoundFont and GeneralUser GS (auto-download to .cache/)
- [x] Test song: Amazing Grace (public domain), all verses
- [x] Tests for loader, lyrics, every validator (pass and fail cases)
- [x] Look at the lead sheet against the SPEC section 9 checklist and fix what's wrong

## M1: Band arrangement (current)

- [x] Arrangement patterns as data (`arrange.STYLES`); move them to `styles/*.yaml` files with instruments, ranges, clefs and transpositions (SPEC 8.2)
- [x] `band` template: voice, piano, bass, with `waltz`, `ballad` and `straight` patterns
- [x] Full score PDF and one PDF per part, parts transposed
- [ ] Range and playability check per instrument
- [ ] Melisma extender lines under held syllables (MusicXML `<extend>`; music21's Lyric doesn't write it)
- [ ] Verses as repeats in the audio (the demo WAV currently plays the tune once)
- [ ] Rehearsal marks and section names from the song file
- [ ] Concert-pitch vs transposed full score option
- [x] Multi-track MIDI and demo WAV for the arrangement
- [ ] Drum kit part (percussion staff) for `straight` and `ballad`
- [ ] A second test song in 4/4 with a different form (verse/chorus)

## MT: Transcription from recordings (SPEC section 12)

- [ ] Stem separation with Demucs; cache stems per song
- [ ] Beat, tempo map, key and chord detection
- [ ] Vocal melody: pitch contour → notes on the beat grid; lyrics aligned with Whisper word timings and the person's own lyric text
- [ ] Bass line and drum groove extraction
- [ ] Draft song file + arrangement parts from the measurements
- [ ] Analysis-by-synthesis fitting loop: render, compare per stem, keep edits that improve closeness + simplicity
- [ ] A/B listening page: original vs fitted render, mark bars that sound wrong
- [ ] Accuracy report per stem against a few hand-checked songs

## M2: Song planning and following directions

- [ ] Brief schema `copyist-brief/0` (SPEC 8.1) with loader and validation
- [ ] Style profiles in `styles/` (SPEC 8.2): start with `hymn`, `pop-ballad`, `outlaw-country`, `western-swing`, `broadway-uptempo`
- [ ] Direction checks in the report (SPEC 8.4): instruments included/excluded, tempo, meter, range, form

- [ ] Song plan schema (form, key, meter, tempo, chord chart, syllabified lyrics with stress)
- [ ] LLM drafting from a brief and lyrics; prompts versioned in `prompts/`
- [ ] Syllabification and stress marking (CMU dict, with manual overrides)

## M3: Melody proposals

- [ ] Melody proposal interface: plan + section → ABC
- [ ] Audition by ear only: render candidates, keep / change / try again; Copyist can also pick on its own (no singing, playing or notation required)
- [ ] Validate-and-retry loop
- [ ] Side-by-side audition: several proposals per section, rendered
- [ ] Evaluate open symbolic models (MuPT, Amadeus) against an LLM baseline

## M4 and later

See SPEC.md section 10.
