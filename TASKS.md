# Copyist tasks

If you're picking up this work, start here. Tick a box when its task is done and verified, and add new tasks where they fit.
Background: [SPEC.md](SPEC.md) says what to build, [ROADMAP.md](ROADMAP.md) lays out the milestones, [DECISIONS.md](DECISIONS.md) records why, and [AGENTS.md](AGENTS.md) has the rules.

Last updated: 2026-10-18.

## Ground rules

- The person directing this can't sing, hum, play an instrument or read music. Every step has to work by listening and choosing, never by performing or reading notation.
- The target is Suno-level sound. The SoundFont preview is a draft, not the product.
- Singer voices live in `voices/`, which git ignores. Never commit or publish them.
- Before calling anything done, look at every PDF page and listen to every render (or run the pitch and lyric checks on it).

## Done

- [x] Score pipeline: a song file becomes a lead sheet, band score and parts (PDF and MusicXML), plus MIDI, a preview WAV and a validation report (`copyist build`, `copyist check`)
- [x] Validators: bars, lyrics fit, range, chord tones, prosody, key
- [x] Band arrangement for voice, piano, bass and drums, which follows `instruments:` in the song file
- [x] Held syllables: extender lines and melisma slurs
- [x] Drums on a percussion staff, with grooves and fills
- [x] Singing through SoulX-Singer (`copyist sing`), with a pitch check (±50 cents) and a lyric check (Whisper)
- [x] Voice prompts made from a recording (`copyist voice`; code in `copyist/voiceprompt.py`)
- [x] Sampled band (`copyist build`): each part on a sampled instrument through sfizz, mixed and mastered, with stems (docs/sound-set.md)
- [x] YuE2 export (`copyist/yue.py`): the score becomes YuE2's ABC dialect plus a request with style, lyrics, abc and seed. mlx-Yue's `abc_tools inspect` accepts it, and its notes match ours exactly

## 1. Push

- [x] `git push`: everything through the expressive performance is pushed (2026-10-17)
- [ ] `git push`: six commits are waiting (the sampled band, styles, the 12/8 default, the takes gallery, the MIT licence, and the handoff plans for melody writing and the open singer)

## 1b. Open source

- [x] MIT licence (LICENSE), CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue templates, tests on GitHub Actions (Linux and macOS, Python 3.11 and 3.12), `copyist --version`
- [ ] Push, then check the first GitHub Actions run passes
- [ ] A short demo (video or page) for the README
- [ ] Label a few good first issues: tango, polka, bluegrass and salsa styles; an instrument library search

## 2. Production-quality sound (YuE2)

The goal: Suno-level audio that follows our score.

- [x] Install a YuE2 runtime on the Mac. yue2.cpp is built in `.cache/yue2.cpp` (Metal on by itself; run with `--device MTL0`). Weights in `.cache/yue/`: `YuE2-3B-Q6_K.gguf` and `YuE2-Vae-F32.gguf`. Terms are in DECISIONS.md. `scripts/setup-yue.sh` repeats the install
- [x] Render Amazing Grace, verse 1, 4-bar intro. `copyist produce` wrote `out/amazing-grace/production/production.wav` (47.1 s, seed 831001) and the same request is `.cache/yue/ag-v1-request.json`. On an M4 Max this took 45 s. Flags match `yue-synth --help`: `--model`, `--vae`, `--request`, `--out`, `--device`
- [x] Check that the render follows the melody: `copyist follow` on the separated vocal. It sang 32 of 32 notes, an octave low, 0.4–0.9 s early
- [x] Fix the octave: YuE2 sings an octave below the ABC, so `yue.py` now writes the vocal an octave up (`SUNG_OCTAVE_BELOW`; `produce --octave`). Tested on CPU: 30 of 32, 29 of them in the written octave
- [ ] Re-render Amazing Grace on the Mac with the octave fix (`copyist produce songs/amazing-grace.yaml`, about 45 s), then separate and `copyist follow` it. Listen
- [ ] `copyist produce --check`: after rendering, separate the vocal (Demucs) and run `follow` automatically
- [ ] Find out why YuE2 shortens the intro (0.9–1.9 s early). Try `[Intro]` lyrics with an instrumental tag, or a Vocal intro written as rests in the Ins voice
- [ ] Render all four verses and check each with `follow --verses 4`
- [x] `copyist produce` wraps `yue.request` and `yue.run_yue2cpp`. Paths come from `COPYIST_YUE_SYNTH`, `COPYIST_YUE_MODEL` and `COPYIST_YUE_VAE`; the device from `COPYIST_YUE_DEVICE` or `--device`
- [x] `docs/production.md`
- [x] Tests for `yue.py`: the header, allowed durations only, bar count, the pickup, and the intro chords

## 3. Singer voices

- [ ] Pick a voice by ear. All four made voices sang Amazing Grace bars 0–4 at 10 of 10 on pitch; they're back to back in `out/amazing-grace/sung/voice-comparison.wav` (hope, june-snow, june-snow-broadway, silver-tongues), and each is in `out/amazing-grace/sung/<voice>/`. Whisper heard every word except in june-snow ("May he's in grace")
- [x] Broadway June Snow: the first 45 s were separated with the mel-band-roformer karaoke model (Hugging Face `Soul-AILab/SoulX-Singer-Preprocess`, about 7× slower than real time on a 2-core CPU; `out/separated/june-snow-broadway-vocal.wav`), and made into the `june-snow-broadway` voice
- [x] Vocals separated with Demucs for 141 songs (the 41 Lights On mixes and 100 experimental songs), on the Mac 2026-10-16: `out/separated/htdemucs/<song>/vocals.wav`, sources in `out/separated/sources/`. Demucs lives in `.cache/demucs` (`-d mps --two-stems vocals`). Voices stay in `voices/` and are never committed or shipped (see DECISIONS.md)
- [x] Make a voice from a separated vocal: `copyist voice separated.wav --name <name> --lyrics <lyrics file>`
- [x] Tests for `voiceprompt.py` (`tests/test_voiceprompt.py`). They found a bug: a blip inside a held note split it in two; fixed
- [ ] Choose a default voice and record the choice in DECISIONS.md

## 3b. Jennifer's voice in YuE2 (the Suno-grade path)

The SoundFont band plus a SoulX vocal will never sound like Suno: they're checking tools now. YuE2 renders the band and the singer together. Two ways to give it a particular voice:

- [x] Continuation test (yue2.cpp `source_tokens`): the first 18 s of Broadway June Snow (tokenized with `yue-tokenize`, the realaudio tokenizer v4 Q8 and MERT-v2 Q8), then Amazing Grace with an 8-bar intro, the realaudio NAR adapter v9, and CPU with 8 steps. Result: the right octave, but only 14 of 32 notes followed the melody (it was 30–32 without the opening). The opening is in G like ours, but around 103 BPM against our 80, so the model drifts toward June Snow. Not good enough to rely on
- [ ] Continuation, second try: a source section at the song's own tempo, or a song file written at the source's tempo. Listen for whether the voice carries
- [x] LoRA tooling: `copyist lora-songs` (prompt sheets → song list), `scripts/yue-lora/prepare.py` (tokens + dataset), `scripts/yue-lora/train.py` (the trainer: mps/CUDA/CPU, resumable), `scripts/setup-yue-train.sh`, `scripts/yue-lora/run.sh`, `produce --lora`, and docs/voice-lora.md. Tested here on a tiny model and with a real-sized adapter in yue2.cpp
- [x] The musical's song list: `.cache/lora/lights-on/songs.jsonl`, 41 songs from `lights-on/AI Prompts` (demo style + tagged lyrics) paired with `lights-on-audio`, trigger word `lightson`
- [x] Trained on the Mac, 2026-10-17, about 11:00 to 14:09 Pacific: 800 steps, about 15 s a step, with `scripts/setup-yue-train.sh` then `scripts/yue-lora/run.sh .cache/lora/lights-on/songs.jsonl ~/Documents/lights-on-audio lights-on`. Held-out loss (two songs it never saw): 4.77 at the start, 3.83 at step 300, 3.85 at 500, then rising to 4.01 at 800 while the training songs kept falling (2.91): past about 500 it memorizes the songs rather than learning the voice. The minted guard set held steady (3.61 → 3.56), so general singing didn't degrade. Checkpoints every 100 steps in `.cache/lora/lights-on/lora/`
- [ ] Listen: `produce --lora` with steps 300 and 500 first (then 400 and 600) and the Jennifer style line, check each with `follow`, and pick one
- [ ] If the score fights the voice: train with each song's own score too (SheetSage2 transcription, `cot=full` prefixes)
- [ ] Use the realaudio NAR adapter (`nar_lora_joint_v9.bf16.safetensors`) in `copyist produce` (`--adapters`), and compare it by ear with a plain render

## 3c. Web front end (docs/web.md)

- [x] `copyist serve`: a local page for songs, lyrics and checks, the score as pages, takes with players, making a take, checking the melody, and voice-training progress. Tested here (server tests, and screenshots in light, dark and phone widths)
- [ ] Use it on the Mac for a real take with a trained voice
- [ ] Compare two takes side by side; mark a favorite take
- [ ] Write a new song from the page (needs melody proposals, M2)
- [ ] Hosting for other people (accounts, a GPU queue): later

## 3d. Desktop app (docs/desktop-app.md, ROADMAP milestone D)

- [x] Decided: a free, open-source Tauri app running everything locally (fits YuE2's non-commercial licence: each user downloads the weights and may sell their own songs)
- [x] Step 1, the engine as a sidecar: `--root`, `--port 0 --machine`, `/api/health`, `/api/models`, the model manager (`copyist/models.py`, `copyist/paths.py`), the install panel on the page, `copyist models`. 90 tests pass
- [x] Apple Developer account: she has one
- [x] Step 2, the Tauri shell: written (`app/`, app/README.md) and compiling on Linux
- [ ] First run on the Mac: `npm run dev` built `copyist-app` on 2026-10-17. Confirm the window opens, the engine starts, and the page loads
- [ ] Step 3, packaging: PyInstaller for the engine, yue2.cpp with Metal, `externalBin`, signing and notarization

## 3e. Sound set and default voices (ROADMAP milestone S)

- [x] Research: instrument libraries and licences (docs/sound-set.md); voice sources and licences (docs/default-voices.md). No hiring: voices come from presets, synthetic LoRAs and open data
- [x] Prototype: `sfizz_render` with the Salamander piano, Growlybass (CC0) and an AVL kit on Amazing Grace; under 2 s a part (docs/sound-set.md)
- [x] Listen: old SoundFont band against the sampled band (sent 2026-10-17)
- [x] Guitars: Karoryfer Black and Green Guitars and Emilyguitar (CC0); bonus jRhodes3d electric piano (docs/sound-set.md). Still missing: an acoustic steel-string guitar
- [x] Expressive performance (`copyist/perform.py`, on by default, `--plain` off): phrase dynamics, metric accents, melody contour, timing within about 26 ms, rolled piano chords, pedal, phrase breaths, final ritardando. 8 tests
- [ ] Listen: sampled band, plain against performed
- [x] Wire it in: the band pack downloads pinned and checked (`copyist/instruments.py`, `copyist models download band`, the page's Download button); `render.py` plays one part at a time on sfizz with stems; `mixdown.py` balances by loudness (BS.1770), adds one room and masters to -16 LUFS under -1 dBFS; credits in the report and on the page; SoundFont fallback. 117 tests pass. Amazing Grace: every melody and bass note within half a semitone, parts aligned within about 15 ms
- [x] Melody voice: the VSCO 2 CE clarinet with Copyist's own SFZ (`scripts/instruments/clarinet.py`: VSCO's octave naming, mislabelled F#5 files, silent starts trimmed, tuning, loudness evened, loops for held notes)
- [ ] On the Mac: `scripts/setup-sfizz.sh --instruments`, then build Amazing Grace and listen
- [ ] `sfizz_render` as a desktop sidecar (with the engine packaging, 3d step 3)
- [ ] Music box and celesta for the musical: find free libraries (VCSL glockenspiel, chimes and kalimbas are the stand-ins), a pack, and a music-box style in the arranger
- [ ] Orchestra and pit pack from VSCO 2 CE, and a pit-orchestra template for Broadway songs
- [ ] Keys, folk and country, and percussion packs (docs/sound-set.md lists what's found); synths generated by sfizz
- [ ] Research the gaps: acoustic steel and nylon guitars, banjo, mandolin, ukulele, pedal steel, accordion, snare brushes, choir
- [ ] A guitar part in the arrangements (strummed and picked patterns per style)

## 3f. Styles (ROADMAP milestone ST, docs/styles.md)

- [x] Styles as data files, the arranger reading them, 23 styles, swing feel, the gallery, `use-style`, the page's Styles section. Tests arrange every style on a song in each of its meters; the original three styles produce the same MIDI as before, byte for byte
- [x] Listen to the band-preview gallery (published as a page, 2026-10-17). Verdict: "pretty cheesy, pretty 1990s". The one-bar patterns, the bare clarinet melody and the plain mix sound like an arranger keyboard
- [x] `copyist gallery --takes`: a finished YuE2 take in every style (singer and the style's own band), and a page button for it
- [ ] On the Mac: `copyist gallery songs/when-the-saints.yaml --takes` (about 13 minutes), then listen and pick the styles that work
- [x] Exact-preview first cut (2026-10-18): phrase cycles in style files; waltz is piano-vocal with a 4-bar LH/bass phrase and no drums; RH rests (no double-strikes); piano melody skips voice legato (no hammer clicks); quieter accompaniment mix. Owner listened: no glitches. Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Softened ballad, hymn, lullaby (piano-vocal) and broadway-ballad (phrase-cycled arps, clarinet kept). Solo-piano keeps RH but opens melody pitches. Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Softened straight, pop, rock, country (two-bar phrases) and folk (piano-vocal + `keep_rh`). Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [ ] Better exact previews (rest): builds across verses, melody voice per style beyond piano/clarinet, real stereo mix, remaining styles (gospel, reggae, disco, …). Default for `write` and the style gallery stays this layer; YuE2 takes stay on demand (`--takes`). Optional SoulX sung guide later. Decision: DECISIONS.md 2026-10-18 (previews and score editing); SPEC §15
- [ ] Organ part (with the pipe organ from VCSL/VSCO and a tonewheel organ generated by sfizz), then gospel and hymn with organ
- [ ] Guitar part (strum and fingerpick patterns, chord shapes), once an acoustic guitar library is found
- [ ] Music box style and instruments (the musical)
- [ ] The prosody check misreads 6/8 (it treats quarter notes as beats); fix it for compound meters

## 3g. Melody writing (ROADMAP milestone MW, spec: docs/melody-writing.md)

The owner's goal is "really good melodies and solid themes", for people who can't write music. Take these in order; each has its test for "done".

- [x] Spike: `yue-plan` writes a full score (melody, chords, sections) from lyrics and a style, with no audio. Tested on "Hope is the thing with feathers": 3/4 in D, and 4/4 in B-flat with a different style line; 2 min 42 s on a 2-core CPU. Format notes in the spec
- [x] `copyist/syllables.py`: English syllables and stress (CMU dictionary through `pronouncing`, plus spelling rules: `-est`/`-ing` keep their syllable, stop+liquid onsets go with the next vowel, `tch` stays together). A 40-word table test passes
- [x] `copyist/abcplan.py`: reads yue-plan's dialect (sections, Vocal and Ins voices, `Zn`, ties, chords on rests; refuses tuplets), trims to the sung bars, writes 2/4 plans as 4/4 (`pair_bars`, putting chord changes on the downbeats), `place_in_range` (down YuE2's octave, best octave for the voice, a semitone transposition with a new key when more than 10% is still outside), `respell` (every accidental explicit, because music21 doesn't carry accidentals through a bar while YuE2's plans do), rescales units, drops repeated chord symbols
- [x] `copyist/fit.py`: dynamic-programming fit of syllables to notes with the spec's cost table, plus a rule that a word's stressed syllable mustn't land on a weaker beat than its neighbour; splits notes when there are more syllables
- [x] Song format: optional `sections:` (rehearsal marks on the lead sheet and score; `[Chorus]` in YuE2 requests) and `written_with:`
- [x] `copyist write LYRICS --title --style --words --voice --candidates --seed [--takes] [--no-preview] [--words-by --music-by]`: planner requests, plans reused when the request is unchanged, candidate folders with plan, request, song file, report and band preview, `candidates.json` ranked by the spec's scores (fails, fit cost, prosody, range, leaps over a 9th, chord tones, the chorus hook). New lyrics start a fresh list. `--keep SEED [--replace] [--build]` copies one into `songs/` and can write its score
- [x] Tests: `tests/test_write.py` (33 tests: syllable table, hand-written plans in `tests/data/plans/`, exact/melisma/split/line-end fits, 2/4 pairing, sections, the whole command with a fake `yue-plan`, keep) and the page's actions in `tests/test_web.py`
- [x] The page: "Write a song" in the drawer (title, lyrics, style, voice, how many), the candidates as they land with band previews and plain-words scores, "Keep this one" (keeps it and writes its score, then opens the song), "Write 4 more". Driven end to end in a browser with a fake planner
- [x] Checked for real in the container: yue-plan on CPU wrote two candidates for "Hope is the thing with feathers" in the folk style (2 min 21 s each on 2 cores); both passed every check, one warning each
- [ ] **NEXT, on the Mac:** `copyist write` on a few lyrics (public-domain poems first) with 4 candidates each, from the page; time it (expect seconds per melody with Metal); the owner listens and picks. Note what goes wrong
- [ ] Section rewriting ("again", "higher", "simpler") and a rule-based writer of Copyist's own (spec, "Later")
- [ ] Let the page edit a kept song's lyrics and refit them (the fit code is ready)

## 3i. Score editing (SPEC §14)

For transcribed and written songs. Both modes ship; neither is a consolation prize.

- [ ] Spec and page sketch: by-ear controls (nudge pitch/length, chord list, "try this bar again") and by-note controls (select on the score, change pitch/duration/chord/lyrics)
- [ ] Write edits back into the song file; re-validate; refresh the engraving and the exact preview
- [ ] MusicXML round-trip (export already exists; import edits without losing Copyist fields)
- [ ] "Try another version of this bar" uses the melody writer on one section

## 3h. The open singer, plan B (ROADMAP milestone OS, spec: docs/open-singer.md)

A singer anyone may use commercially that follows Copyist's score: HeartMuLa-oss-3B (Apache-2.0) plus MuLaCover's lead-sheet conditioning (Apache-2.0 code), trained by us on data with clean rights.

- [x] Research and plan: open models compared (HeartMuLa, ACE-Step 1.5, MuLaCover, MiniMax Music 3, SongGeneration 2); MuLaCover's conditioning read from its source (a sixteenth-note lead sheet, an adaptor, gated cross-attention on the last 8 layers, zero-init gate)
- [ ] B0: HeartMuLa-oss-3B running on the Mac (mps): a 30 s song, the speed and memory measured. In the container on CPU: a short clip, to check the setup. Write `scripts/setup-open-singer.sh`
- [ ] B0: MuLaCover's adaptor bolted onto the HeartMuLa backbone (`copyist_open/` or `scripts/open-singer/model.py`, importing MuLaCover's Apache code with attribution). Done when a test shows identical outputs to the base model while the gate is zero
- [ ] B1: `scripts/open-singer/generate.py`: songs from HeartMuLa across Copyist's style words and public-domain or original lyrics, with a manifest (source, licence, seed, tags, lyrics)
- [ ] B1: `scripts/open-singer/transcribe.py`: song to lead sheet on a sixteenth grid (Demucs, then pYIN, beats, the Music X Lab chord model), plus the quality gate (`copyist follow` at 90% or more). Done when a deliberately shifted label is rejected
- [ ] B1: `scripts/open-singer/tokenize.py`: HeartCodec tokens per song. 50 songs end to end first, then 1,000
- [ ] B2: `scripts/open-singer/train.py`: frozen base, adaptors trained, 10% condition dropout, resumable, mps/CUDA/CPU, evals of loss with the real against a shuffled lead sheet on held-out songs. Done when the real condition's loss is clearly lower
- [ ] B3: Copyist scores (Amazing Grace, the Saints, Silent Night) in several styles; `copyist follow` at 90% or more on all three
- [ ] B4: `copyist produce --singer open`, the page's singer choice, the weights as a pinned download, docs. Done when the owner makes a take with it from the page
- [ ] Decide with the owner: the Mac only (a week or two) or rented GPU time (about a day, a few hundred dollars) for B1 and B2

## 4. Singing that sounds performed

- [ ] Lyric timing check: align the sung WAV to the lyrics (Whisper word timestamps or a CTC aligner) and flag words that land too far from their notes in the score
- [ ] Riffs and variations: let the singer decorate (SoulX's F0-curve mode, or YuE2's freedom) while a check confirms the structural notes still match the score (downbeats, phrase ends)
- [ ] Sing all the verses, not just bars 0–4
- [ ] Retry any segment that fails the pitch or lyric check, using a new seed
- [ ] Run SoulX on the Mac (`--device mps`) and time it

## 5. Score polish (M1 leftovers)

- [ ] Range and playability check for each instrument
- [ ] Verses as repeats in the audio
- [ ] Rehearsal marks
- [ ] Concert-pitch option
- [ ] Drum key
- [ ] Simile marks

## 6. Following directions (M2, SPEC §8)

- [ ] Brief format `copyist-brief/0`
- [x] Style profiles beyond waltz, ballad and straight (23 styles, section 3f)
- [ ] Direction checks in the report: style, instruments, tempo, mood
- [ ] Melody proposals: Copyist offers several melodies, renders each, and the person picks by ear

## 7. Transcribing recordings (MT, SPEC §12)

Spec: docs/transcribing.md. The owner asked for this on 18 October 2026; her musical is built from songs that exist only as recordings.

- [x] Measured SheetSage2 (`yue-transcribe`): the most accurate (0.94–0.98 note F1), but its weights are CC BY-NC 4.0 with no permission for creators to sell, so it's an optional engine and the open one is the default
- [x] The open engine (`copyist/transcribe.py`): Demucs stems (`stems.split_vocals`), beats on band and voice with a steady tempo, meter by testing groupings of eighths (beat first, then bar: 3/4, 4/4, 6/8, 12/8), key, chords (chroma above the bass, Viterbi, the bass naming roots on downbeats), pYIN notes tidied (`clean_notes`: bleed, outliers, scoops, slides that wander, splits, syllable attacks kept, the lyric count), rhythm snapped to the plainest pattern per beat, pitches settled by context, syllable-start hints for the lyric fit
- [x] `copyist transcribe RECORDING --title [--lyrics] [--engine open|sheetsage] [--voice] [--vocals --accompaniment]` and `--keep [--replace] [--build]`; out/<slug>/transcribe/ with source, stems, draft.abc, song file, report with doubts, band playback, transcription.json
- [x] The page: "Transcribe a recording" (upload, title, lyrics, engine with SheetSage's licence spelled out), the result with the original and the band side by side, doubts, notes, "Keep it". Driven end to end in a browser
- [x] Tests: `tests/test_transcribe.py` (a tune synthesised in the test: notes including a repeated one, rhythm, chords, key, meter; cleaning rules; rhythm snapping; a SheetSage-style draft with a pickup bar through a fake runner) and the page's upload and actions in `tests/test_web.py`
- [x] Evaluation: `scripts/transcribe/evaluate.py SONG.yaml DRAFT.abc [--octave-free]`; the numbers are in docs/transcribing.md
- [ ] **NEXT:** more sung truth: YuE2 takes of the Saints and Silent Night (being rendered in the cloud container at the time of writing; render them on the Mac with `copyist produce` if they're missing), then improve the open engine where they show it's weakest (chords on real mixes, sung ornaments)
- [ ] On the Mac: the owner transcribes a few of her own songs from the page and listens; note what goes wrong. Never commit them
- [ ] Repeats vote (SPEC 12.2a step 3): the same section sung again settles doubtful notes
- [ ] Per-doubt A/B by ear (SPEC 12.2a step 7), writing the choice back into the song file
- [ ] Bass line, drum groove and band parts (SPEC 12.1); analysis by synthesis (SPEC 12.2 step 4)
