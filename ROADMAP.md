# Roadmap

Take the first unchecked item in the current milestone. Tick items when they're done and tested. Milestone definitions are in SPEC.md section 11. The current milestone is M5 (better sound); TASKS.md has the day-to-day list.

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

## M1: Band arrangement (paused; these leftovers come back after M5)

- [x] Arrangement patterns as data (`arrange.STYLES`); move them to `styles/*.yaml` files with instruments, ranges, clefs and transpositions (SPEC 8.2)
- [x] `band` template: voice, piano, bass, with `waltz`, `ballad` and `straight` patterns
- [x] Full score PDF and one PDF per part, parts transposed
- [ ] Range and playability check per instrument
- [x] Melisma extender lines under held syllables (MusicXML `<extend>`; music21's Lyric doesn't write it)
- [ ] Verses as repeats in the audio (the demo WAV currently plays the tune once)
- [ ] Rehearsal marks and section names from the song file
- [ ] Concert-pitch vs transposed full score option
- [x] Multi-track MIDI and demo WAV for the arrangement
- [x] Drum kit part (percussion staff) for `waltz`, `ballad` and `straight`, with fills and crashes
- [x] `instruments:` in the song file; left-out instruments get no part (first direction check in the report)
- [ ] Drum key (which line is which piece) on the first page of the drum part
- [ ] Repeated grooves written with repeat (simile) marks instead of every bar in full
- [ ] A second test song in 4/4 with a different form (verse/chorus)

## MT: Transcription from recordings (SPEC section 12)

- [x] Stem separation with Demucs (on the Mac, `-d mps --two-stems vocals`): 141 songs separated into `out/separated/htdemucs/<song>/vocals.wav` on 2026-10-16; `copyist follow --separate` caches the vocal beside each take
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

## M5: Better sound (current)

- [x] Integrate SoulX-Singer: `copyist sing` exports the voice part (per-word phonemes, held notes, phrases), runs the model, checks pitch per note and words with Whisper, mixes with the band (docs/singing.md)
- [ ] Run `copyist sing` on the Mac (M4 Max): confirm `mps` works or fall back to CPU; record the speed (SoulX is a checking tool now; low priority)
- [ ] Record consented reference voices (a few singers, different ranges) and make their metadata with SoulX-Singer's preprocessing
- [ ] Auto-retry phrases that fail the pitch or lyric check (new seed), keep the best take
- [ ] Sing every verse and stitch them with the band playing the tune once per verse
- [ ] Duets and choruses: one voice part per singer, each with its own reference voice
- [x] Evaluate YuE2: `copyist produce` renders a Copyist score with yue2.cpp; the separated vocal sang 32 of 32 notes, an octave low; licence recorded in DECISIONS.md
- [x] Octave fix: the vocal goes to YuE2 an octave up (`SUNG_OCTAVE_BELOW`); tested at 30 of 32 in the written octave
- [x] `copyist follow`: melody check with timing search and any-octave matching, `--separate` to run Demucs first
- [x] `produce --take` keeps every render; `produce --lora` renders with a trained voice
- [x] Voice LoRA tooling: `copyist lora-songs`, `scripts/yue-lora/` (prepare, train on mps/CUDA/CPU, resume), docs/voice-lora.md
- [ ] First LoRA: *I Left the Lights On*, 41 songs, trigger `lightson` (training on the Mac since 2026-10-17); pick a checkpoint by ear and with `follow`
- [ ] Continuation (open with a real recording) at a matching tempo; keep it if the melody holds
- [ ] Train with each song's own score too (SheetSage2 transcription, `cot=full`) if the score fights the voice
- [ ] Evaluate ACE-Step 1.5 as the fully open fallback
- [x] Pitch check: per-note f0 (pYIN) vs score, ±50 cents on the middle of each note (SPEC 6)
- [x] Lyric check: Whisper transcription compared with the sung words

## W: Web front end (SPEC section 13)

- [x] `copyist serve`: songs, lyrics and checks, the score as page images, takes with players, making a take, the melody check, voice-training progress; local only (docs/web.md)
- [ ] A real take from the page on the Mac, with a trained voice
- [ ] Compare two takes side by side; mark a favorite
- [ ] Write a new song from the page (after M2 and M3)

## M4 and later

See SPEC.md section 11.
