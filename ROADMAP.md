# Roadmap

Take the first unchecked item in the current milestone. Tick items when they're done and tested. Milestone definitions are in SPEC.md section 11. The current milestones are MW (melody writing) and OS (the open singer); TASKS.md has the day-to-day list.

## M0: Walking skeleton (done 2026-10-16)

- [x] Project docs: README, SPEC, AGENTS, ROADMAP, DECISIONS
- [x] Packaging: pyproject.toml with the `copyist` command
- [x] Song file loader: YAML + ABC melody + chord symbols → music21 score
- [x] Lyric parsing and alignment (hyphens, `_` melisma, `*` skip, ties and rests skipped, multiple verses)
- [x] Validators: `bars`, `lyrics-fit`, `range`, `chord-tones`, `prosody`, `key`
- [x] Validation report (Markdown) with bar and beat for every finding
- [x] Engraving: lead sheet MusicXML → SVG (Verovio) → PDF (PyMuPDF), title and credits on page 1
- [x] MIDI export
- [x] Demo audio: MIDI → WAV with TinySoundFont and GeneralUser GS (auto-download to .cache/); since replaced by sampled instruments (milestone S), with the SoundFont as the fallback
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
- [x] A second test song in 4/4: *When the Saints Go Marching In* (and *Silent Night* in 6/8); a verse/chorus song still to come

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
- [x] First LoRA: *I Left the Lights On*, 41 songs, trigger `lightson`: trained on the Mac 2026-10-17, 800 steps; held-out loss lowest at steps 300–500
- [ ] Pick a checkpoint by ear (steps 300 and 500 first) and with `follow`
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

## D: Desktop app (docs/desktop-app.md)

A free, open-source Tauri app: the page as its window, the engine and yue2.cpp as sidecars, models downloaded on first run, everything on the person's own computer.

- [x] Engine as a sidecar: `--root` library folder, `--port 0 --machine`, health and version endpoint, model manager (pinned, verified, resumable downloads with progress and the licence shown first), `copyist models`
- [x] Tauri shell: the window loads the engine's page; the engine starts and stops with the app (app/; compiles; first Mac run pending)
- [ ] Mac packaging: PyInstaller engine, yue2.cpp with Metal, signing and notarization (Apple Developer account)
- [ ] First run: hardware check, model download, a demo song
- [ ] Best of several takes, ranked by the melody and lyric checks; re-render one section
- [ ] Windows and Linux builds; updates

## S: Sound set and default voices (docs/sound-set.md, docs/default-voices.md)

- [x] Build `sfizz_render`; render a song with the Salamander piano, Growlybass and an AVL drum kit
- [x] A bass with a clear licence: Karoryfer Growlybass and Meatbass (CC0)
- [x] Electric guitars with clear licences: Karoryfer Black and Green Guitars, Emilyguitar (CC0)
- [ ] An acoustic steel-string guitar with a clear licence
- [x] Expressive performance layer (`copyist/perform.py`), on by default
- [x] Instruments as a pinned download in packs (`copyist/instruments.py`: git object ids per file, resumable, `copyist models download band`, a Download button on the page); `render.py` plays one part at a time on sfizz and keeps stems; `mixdown.py` balances by loudness, adds one room and masters gently; credits in the report and on the page; the SoundFont as the fallback
- [x] A melody voice for previews: the VSCO 2 CE clarinet, with Copyist's own measured SFZ
- [ ] `scripts/setup-sfizz.sh` on the Mac, then the band on Amazing Grace from the page
- [ ] `sfizz_render` bundled as a desktop sidecar (milestone D)
- [ ] Music box and celesta (for *I Left the Lights On*): find free libraries, add a pack, and a music-box arrangement style
- [ ] Orchestra and pit pack (VSCO 2 CE: strings, harp, brass, woodwinds, timpani, glockenspiel), with a pit-orchestra template for Broadway
- [ ] Keys pack (Rhodes, organs, harpsichords, vibraphone), folk and country pack (harmonicas, fiddle, guitars), percussion pack (VCSL)
- [ ] Synths generated by sfizz (pads, leads, synth bass), no download
- [ ] Find the rest with clear licences: acoustic steel and nylon guitars, banjo, mandolin, ukulele, pedal steel, accordion, snare brushes, a choir
- [ ] A melody voice per style (flute, oboe, violin, sax, synth lead), chosen by the song's style
- [ ] Voice presets: style lines and seeds that stay one singer across songs
- [ ] Synthetic voice LoRAs: many takes per preset, grouped by speaker embedding, trained with scripts/yue-lora
- [ ] Mastering step for takes: loudness to streaming level, gentle limiter (reuse `mixdown.loudness` and `mixdown.limit`)

## ST: Styles (docs/styles.md, SPEC 8.2)

Copyist arranges in as many styles as can be written as correct scores: everyone's music, not one songwriter's.

- [x] Styles as data: `copyist/styles/*.yaml` (`copyist-style/0`), checked on load; the arranger and drum kit read them; the three original styles ported note for note
- [x] Pattern vocabulary: chords, jazz shells, arpeggios, chord tones and approach notes, a walking bass, climbing bass lines (boogie, octaves), more drums (ride, open and pedal hi-hat, toms, tambourine, clap), triplets, `none` for bass or drums
- [x] Swing and shuffle feel in the performance (and in `--plain`), "Swing" or "Shuffle" on the score
- [x] 23 styles in 3/4, 4/4 and 6/8 across nine families; YuE2's style words come from the style
- [x] `copyist gallery` (every style for the song's meter, each at a fitting tempo), `copyist use-style`, `copyist styles`; the page's Styles section with a player per style and "Use this style"
- [x] `copyist gallery --takes`: a finished YuE2 take in every style, with the style's words and tempo (and a trained voice)
- [ ] A band preview that doesn't sound like a 1990s arranger keyboard: phrase-level variation, builds across verses, comping around the melody, a better melody voice, a real mix
- [x] Test songs in 4/4 and 6/8: *When the Saints Go Marching In*, *Silent Night* (public domain)
- [ ] More parts in the arranger: organ, guitar (strummed and picked, chord shapes), strings, brass and reeds, a lead line, choir; the ensemble chosen by the style
- [ ] Wave 1, finished with real parts: music box (for *I Left the Lights On*), gospel and hymn with organ, country with acoustic guitar and fiddle, folk with fingerpicked guitar, pop and rock with guitars
- [ ] Wave 2: salsa, cumbia, bolero, tango, Western swing, bluegrass, Motown, funk, Celtic reel and air, polka, calypso, 12/8 doo-wop
- [ ] Wave 3: big band, orchestral and cinematic, string quartet, SATB choir, electronic (house, synthwave, lo-fi, ambient)
- [ ] A melody voice per style for previews (flute, sax, violin, synth lead)
- [ ] Harmony, melody habits and form conventions in each profile (for melody proposals, M3)
- [ ] The prosody check reads compound meters (6/8) by dotted-quarter beats

## MW: Melody writing (docs/melody-writing.md)

Lyrics and a style in; several finished songs out to choose between by ear, each with a correct score.

- [x] Spike: YuE2's planner (`yue-plan`) writes melody, chords and sections from lyrics and a style
- [x] Syllables and stress; the planner's ABC into Copyist song files; lyrics fitted to the notes
- [x] `copyist write` with ranked candidates, band previews and optional takes; `--keep`
- [x] The page's "Write a song"
- [ ] The owner writes a song with it on the Mac and keeps one
- [ ] Section-level rewriting ("again", "higher", "simpler")
- [ ] A rule-based writer of Copyist's own (MIT), for use without YuE2

## OS: The open singer (docs/open-singer.md)

A singer anyone may use commercially that follows the score: HeartMuLa-oss-3B plus MuLaCover-style lead-sheet conditioning, trained by Copyist on data with clean rights.

- [x] Research and plan
- [ ] B0 Feasibility on the Mac; the adaptor bolted on with zero effect at the start
- [ ] B1 Data: generated songs, transcribed lead sheets, quality gate, tokens
- [ ] B2 Training: the real lead sheet clearly beats a shuffled one on held-out songs
- [ ] B3 Following: 90% of notes on the three test songs
- [ ] B4 In Copyist: `produce --singer open`, the page, the download

## M4 and later

See SPEC.md section 11.
