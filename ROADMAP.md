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
- [x] Beat, meter (3/4, 4/4, 6/8, 12/8), key and chord detection (`copyist/transcribe.py`, docs/transcribing.md)
- [x] Vocal melody: pitch contour → notes on the beat grid, tidied and settled by musical context; lyrics fitted with the recording's own syllable starts; Whisper hears the words when none are given
- [x] Draft song file from the measurements (`copyist transcribe`), the page's "Transcribe a recording", and SheetSage2 as an optional, non-commercial engine
- [ ] Bass line and drum groove extraction; arrangement parts
- [ ] Analysis-by-synthesis fitting loop: render, compare per stem, keep edits that improve closeness + simplicity
- [ ] A/B listening page: original vs fitted render, mark bars that sound wrong
- [x] Accuracy measured against Copyist's own songs (`scripts/transcribe/evaluate.py`; numbers in docs/transcribing.md)
- [x] YuE2 truth takes of Saints and Silent Night measured; double-tempo 6/8 correction on soft takes
- [x] Beat-chroma smoothing + tonal chord prior on YuE2 takes (Silent Night chords 0.69; Saints 0.89; Major-General 0.79)
- [x] Ornament folding / lyric-guided splits on busy takes (TASKS §7; Major-General 128 notes)
- [x] Open-transcriber submodule ([Digital-Defiance/open-transcriber](https://github.com/Digital-Defiance/open-transcriber))
- [x] T0 Basic Pitch baseline scored (loses to open engine except Major-General ≈)
- [ ] Open neural lead-sheet: T0b tidy path, then T1 if needed (docs/open-transcriber.md)
- [ ] Two big public-domain songs in the round-trip set, covering a minor key, a key change, syncopation, richer harmony, 12/8, a wide range and a repeated chorus (TASKS.md §7)
- [ ] T1: train the neural transcriber. The owner wants this soon, as soon as the non-training passes run out (two attempts in a row that don't move either benchmark table). Plan written 2026-10-19: a small lead-sheet model on Basic Pitch, trained on SoulX-sung Copyist melodies with exact labels. Owner decisions made 2026-10-19 (Mac only, MIT weights; TASKS.md §7); the data foundation (held-out guard, score sampler) landed. New goal: the best open transcriber available, beating SheetSage2 objectively.
- [x] Design audit (2026-10-19; TASKS.md §7):
  - **The judge:** real, licence-clean recordings, not YuE2 takes.
  - **T1, re-scoped:** an encoder bake-off with multi-task heads and structured decoding.
  - **The song format:** `copyist-song/1` (tuplets, key, meter and tempo changes, repeats, a second vocal line).
  - **Budget:** $0.
  - **The owner's time:** nothing waits on it.
- [x] Stage 0a closed under option B (2026-10-20): SheetSage2 not reproducible locally; its published numbers are external bars
- [ ] The reset (TASKS §7): OT2 design record and guard tests, the canonical transcription document and engine interface, the listening-model contest, the reconstruction loop on public-domain songs, then OT2's first heads and decoder; COTB-v1 and the strict notation metrics grow alongside
- [ ] Stage 1, rhythm and notation: global tempo and meter, a tuplet-aware note grid, key changes, and `copyist-song/1` with a converter
- [ ] Stages 2–4: the encoder bake-off and trained heads; real data, a symbolic prior and the repeats vote; then the one-time test. About 2.5–4 months to the test, depending on the GPU windows the owner's laptop can give (200–350 GPU hours)
- [ ] Repeats vote, per-doubt A/B by ear (SPEC 12.2a)
- [ ] The Lights On loop (the owner's goal, part 1; AGENTS.md):
  - **Steps:** transcribe each demo with Copyist's own engine; reproduce it with YuE2; measure how close the take is, automatically; refine; then make lead sheets and arrangements.
  - **When:** it waits for our engine. Never SheetSage. Build and test the loop on public-domain music first.

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
- [x] Public static site on GitHub Pages (`site/`): what Copyist is, features, install; Actions deploy from `main` to copyist.digitaldefiance.org
- [ ] A real take from the page on the Mac, with a trained voice
- [ ] Compare two takes side by side; mark a favorite
- [ ] Write a new song from the page (after M2 and M3)

## D: Desktop app (docs/desktop-app.md)

A free, open-source Tauri app (Homebrew cask → `Copyist.app`): the page as its window, the engine and yue2.cpp as sidecars, optional packs downloaded when the person chooses them, everything on their own computer. Default install path for users.

- [x] Engine as a sidecar: `--root` library folder, `--port 0 --machine`, health and version endpoint, model manager (pinned, verified, resumable downloads with progress and the licence shown first), `copyist models`
- [x] Tauri shell: the window loads the engine's page; the engine starts and stops with the app (app/; the release app checked on the Mac 2026-10-19)
- [x] Default path: Homebrew cask, packaging scripts, release workflow; Install extras in the UI; write without the singer
- [x] Mac packaging finish: v0.0.1 (2026-10-19), a signed, notarized, stapled Apple Silicon DMG on the GitHub release; `brew install --cask digital-defiance/tap/copyist` (cask in Digital-Defiance/homebrew-tap)
- [ ] Intel Mac build
- [ ] First run polish: hardware check; demo already via `--demo`
- [ ] Best of several takes, ranked by the melody and lyric checks; re-render one section
- [ ] Windows and Linux builds; updates

## S: Sound set and default voices (docs/sound-set.md, docs/default-voices.md)

- [x] Build `sfizz_render`; render a song with the Salamander piano, Growlybass and an AVL drum kit
- [x] A bass with a clear licence: Karoryfer Growlybass and Meatbass (CC0)
- [x] Electric guitars with clear licences: Karoryfer Black and Green Guitars, Emilyguitar (CC0)
- [x] An acoustic steel-string guitar with a clear licence (Discord GM Martin HD28, CC0; 2026-10-18)
- [x] Expressive performance layer (`copyist/perform.py`), on by default
- [x] Instruments as a pinned download in packs (`copyist/instruments.py`: git object ids per file, resumable, `copyist models download band`, a Download button on the page); `render.py` plays one part at a time on sfizz and keeps stems; `mixdown.py` balances by loudness, adds one room and masters gently; credits in the report and on the page; the SoundFont as the fallback
- [x] A melody voice for previews: the VSCO 2 CE clarinet, with Copyist's own measured SFZ
- [ ] `scripts/setup-sfizz.sh` on the Mac, then the band on Amazing Grace from the page
- [ ] `sfizz_render` bundled as a desktop sidecar (milestone D)
- [x] Celesta (Neil Bickford CC0) + music-box style (2026-10-18); crank/comb music box still to host
- [ ] Orchestra and pit pack (VSCO 2 CE: strings, harp, brass, woodwinds, timpani, glockenspiel), with a pit-orchestra template for Broadway
- [ ] Keys pack (Rhodes, organs, harpsichords, vibraphone), folk and country pack (harmonicas, fiddle, guitars), percussion pack (VCSL)
- [ ] Synths generated by sfizz (pads, leads, synth bass), no download
- [ ] Find the rest with clear licences: banjo, mandolin, ukulele, pedal steel, accordion, snare brushes, a choir (nylon and steel guitars are in)
- [ ] A melody voice per style (synth lead; flute/oboe/fiddle/sax are in), chosen by the song's style
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
- [x] Exact-preview first cut: phrase cycles in styles; waltz piano-vocal (no drums); quieter accompaniment mix (2026-10-18)
- [x] Softened ballad, hymn, lullaby, broadway-ballad previews (2026-10-18)
- [x] Softened straight, pop, rock, country, folk previews (2026-10-18)
- [x] Phrase cycles on every style (2026-10-18)
- [x] Form build across the song + stereo place in the mix (2026-10-18)
- [x] Richer stereo room (wet keeps pan; ~1.3 s hall) — 2026-10-18
- [x] Exact previews: dedicated guitar staff (folk/country/pop/rock/blues); flute/oboe/sax/fiddle melody voices are in. YuE2 takes stay on demand; see SPEC §15
- [x] Test songs in 4/4 and 6/8: *When the Saints Go Marching In*, *Silent Night* (public domain)
- [x] Pipe organ (VCSL, hymn), concert harp (VSCO, Broadway), tonewheel synth for gospel (2026-10-18)
- [x] Nylon/steel/electric guitars; fiddle on country/Celtic; flute/oboe on Broadway/march; sax on swing/jazz/blues/bossa (2026-10-18)
- [x] Guitar staff (strummed and picked, chord shapes) for folk/country/pop/rock/blues (2026-10-18)
- [ ] More parts in the arranger: strings, brass and reeds, a lead line, choir; the ensemble chosen by the style
- [x] Music-box style + VCSL glock stand-in, then real celesta (2026-10-18); crank music box still to host
- [ ] Wave 1, finished with real parts: crank/comb music box when hosted (celesta and guitar staff in)
- [ ] Wave 2: salsa, cumbia, bolero, tango, Western swing, bluegrass, Motown, funk, Celtic reel and air, polka, calypso, 12/8 doo-wop
- [ ] Wave 3: big band, orchestral and cinematic, string quartet, SATB choir, electronic (house, synthwave, lo-fi, ambient)
- [ ] A melody voice per style for previews (synth lead; flute/oboe/fiddle/sax are in)
- [ ] Harmony, melody habits and form conventions in each profile (for melody proposals, M3)
- [x] The prosody check reads compound meters (6/8) by dotted-quarter beats

## MW: Melody writing (docs/melody-writing.md)

Lyrics and a style in; several finished songs out to choose between by ear, each with a correct score.

- [x] Spike: YuE2's planner (`yue-plan`) writes melody, chords and sections from lyrics and a style
- [x] Syllables and stress; the planner's ABC into Copyist song files; lyrics fitted to the notes
- [x] `copyist write` with ranked candidates, band previews and optional takes; `--keep`
- [x] The page's "Write a song"
- [x] The owner writes a song with it on the Mac and keeps one (Tyger candidate 4 → `songs/the-tyger.yaml`)
- [x] Section-level rewriting ("again", "higher", "simpler") via `copyist rewrite` and the page's "Try another melody"
- [x] A rule-based writer of Copyist's own (MIT), for use without YuE2 (`--engine rules`)

## SE: Score editing (SPEC §14)

Edit transcribed and written songs. By ear and by note, both first-class.

- [ ] By ear: nudge, chord list, try another bar, A/B
- [ ] By note: select on the score, change pitch/duration/chord/lyrics
- [ ] Persist to the song file; re-validate; re-engrave; refresh the exact preview
- [x] MusicXML → song file (`copyist import`: lead sheet / vocal line)
- [ ] MusicXML import of edits (keep Copyist fields)

## OS: The open singer (docs/open-singer.md)

A singer anyone may use commercially that follows the score: HeartMuLa-oss-3B plus MuLaCover-style lead-sheet conditioning, trained by Copyist on data with clean rights.

- [x] Research and plan
- [ ] B0 Feasibility on the Mac; the adaptor bolted on with zero effect at the start
- [ ] B1 Data: generated songs, transcribed lead sheets, quality gate, tokens
- [ ] B2 Training: the real lead sheet clearly beats a shuffled one on held-out songs
- [ ] B3 Following: 90% of notes on the three test songs
- [ ] B4 In Copyist: `produce --singer open`, the page, the download

## HW: Using the whole computer (docs/hardware.md)

CPU, GPU and Neural Engine working at once on the owner's M4 Max; the GPU kept for what only it can do. Still runs on Linux and Windows (CUDA, Vulkan, CPU).

- [x] Plan; band parts side by side; Demucs on CUDA where it can; several takes in one YuE2 run (`produce --takes`, the page's "Takes"); the benchmark script
- [x] H1 Measured (21 October): the flow-matching render is 65% of a take and doesn't batch; 4 takes in one run save a fifth
- [ ] H2 Draft takes at fewer render steps, then finish the chosen one from its codes (measure the steps first)
- [ ] H3 The page's GPU and CPU lanes
- [ ] H4 Demucs on the faster device and offline; band previews in parallel; `copyist doctor`
- [ ] H5 whisper.cpp with Core ML; HTDemucs on Core ML
- [ ] H6 MLX against PyTorch MPS for one training step

## M4 and later

See SPEC.md section 11.
