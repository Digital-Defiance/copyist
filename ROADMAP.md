# Roadmap

Take the first unchecked item in the current milestone. Tick items when they're done and tested. Milestone definitions are in SPEC.md section 10.

## M0: Walking skeleton (current)

- [x] Project docs: README, SPEC, AGENTS, ROADMAP, DECISIONS
- [ ] Packaging: pyproject.toml with the `copyist` command
- [ ] Song file loader: YAML + ABC melody + chord symbols → music21 score
- [ ] Lyric parsing and alignment (hyphens, `_` melisma, `*` skip, ties and rests skipped, multiple verses)
- [ ] Validators: `bars`, `lyrics-fit`, `range`, `chord-tones`, `prosody`, `key`
- [ ] Validation report (Markdown) with bar and beat for every finding
- [ ] Engraving: lead sheet MusicXML → SVG (Verovio) → PDF (PyMuPDF), title and credits on page 1
- [ ] MIDI export
- [ ] Demo audio: MIDI → WAV with TinySoundFont and GeneralUser GS (auto-download to .cache/)
- [ ] Test song: Amazing Grace (public domain), all verses
- [ ] Tests for loader, lyrics, every validator (pass and fail cases)
- [ ] Look at the lead sheet against the SPEC section 8 checklist and fix what's wrong

## M1: Band arrangement

- [ ] Arrangement template format (instruments, ranges, clefs, transpositions, patterns per style)
- [ ] `band` template: voice, piano, bass, with `waltz`, `ballad` and `straight` patterns
- [ ] Full score PDF and one PDF per part, parts transposed
- [ ] Range and playability check per instrument
- [ ] Multi-track MIDI and demo WAV for the arrangement
- [ ] Drum kit part (percussion staff) for `straight` and `ballad`
- [ ] A second test song in 4/4 with a different form (verse/chorus)

## M2: Song planning

- [ ] Song plan schema (form, key, meter, tempo, chord chart, syllabified lyrics with stress)
- [ ] LLM drafting from a brief and lyrics; prompts versioned in `prompts/`
- [ ] Syllabification and stress marking (CMU dict, with manual overrides)

## M3: Melody proposals

- [ ] Melody proposal interface: plan + section → ABC
- [ ] Validate-and-retry loop
- [ ] Side-by-side audition: several proposals per section, rendered
- [ ] Evaluate open symbolic models (MuPT, Amadeus) against an LLM baseline

## M4 and later

See SPEC.md section 10.
