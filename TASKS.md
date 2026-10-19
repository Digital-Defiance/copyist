# Copyist tasks

If you're picking up this work, start here. Tick a box when its task is done and verified, and add new tasks where they fit.
Background: [SPEC.md](SPEC.md) says what to build, [ROADMAP.md](ROADMAP.md) lays out the milestones, [DECISIONS.md](DECISIONS.md) records why, and [AGENTS.md](AGENTS.md) has the rules.

Last updated: 2026-10-19.

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
- [x] `git push`: the sampled band, styles, the 12/8 default, the takes gallery, the MIT licence and the handoff plans are on `main`; the 2026-10-19 handoff committed and pushed the rest (nothing waits locally)

## 1b. Open source

- [x] MIT licence (LICENSE), CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue templates, tests on GitHub Actions (Linux and macOS, Python 3.11 and 3.12), `copyist --version`
- [ ] Push, then check the first GitHub Actions run passes. Not tracked for now (owner, 2026-10-19): the gate is the full local suite plus open-transcriber's own tests
- [ ] Dependabot's Cargo security update for `glib` (< 0.20, pulled in by Tauri's Linux GTK stack) fails: no patched version fits Tauri 2's gtk-rs 0.18. Revisit when Tauri moves to gtk-rs ≥ 0.20; the Mac app doesn't link glib
- [x] Public site on GitHub Pages (`site/`): advertises Copyist, explains score-first features, install and setup; deployed by `.github/workflows/pages.yml` to https://copyist.digitaldefiance.org/ (`site/CNAME`). After the next push to `main`: Pages → Source: GitHub Actions, and a DNS CNAME for `copyist` → `digital-defiance.github.io` (plus enforce HTTPS in Pages settings)
- [ ] A short demo (video or audio) linked from the README and the site — still open; the Pages site covers the written pitch
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
- [x] App as the default path: README + Pages lead with Homebrew/`Copyist.app`; **Install extras** page (`#/setup`); write works without the singer (rules/auto); `COPYIST_DESKTOP=1`; packaging scripts (`scripts/package/`), a Homebrew cask (since moved to Digital-Defiance/homebrew-tap), release workflow
- [x] Signing path ready: Digital Defiance Developer ID (`J6887N729S`) on this Mac; `bundle-mac.sh --sign` + entitlements + notarize env documented (`scripts/package/README.md`)
- [x] Shipped v0.0.1 (2026-10-19): `freeze-engine.sh` (66 s) then `bundle-mac.sh --sign` (180 s, both notarizations included) on this Mac with the App Store Connect API key, from commit 0878a5d. Every binary in the app is signed with the Digital Defiance Developer ID, hardened runtime and a timestamp; the app and the DMG are notarized and stapled. The DMG is on the [v0.0.1 release](https://github.com/Digital-Defiance/copyist/releases/tag/v0.0.1); the cask is in Digital-Defiance/homebrew-tap (`brew install --cask digital-defiance/tap/copyist`), and `brew fetch` and `brew audit --online` pass
- [x] First run on the Mac: the release app, opened from the mounted DMG, opened its window; the engine answered `/api/health` within 7–14 s of opening, the page and Install extras (`#/setup`) loaded, and quitting stopped the engine. That check found the frozen engine outliving the app (Tauri killed only PyInstaller's launcher); fixed by running the engine in its own process group. `scripts/package/run-app.sh` (the dev path) wasn't run again
- [ ] An Intel Mac build: v0.0.1 is Apple Silicon only (`depends_on arch: :arm64`). Needs an Intel Mac (or CI signing) to build, notarize and smoke-test an x64 DMG, then an `on_intel` block in the tap's cask
- [ ] Optional later: CI secrets (`APPLE_CERTIFICATE` …) so release-mac.yml signs in GitHub Actions; until then sign on this Mac (the workflow uploads unsigned artifacts only, never to the release)
- [x] Keep packaging from dirtying the checkout: the engine freezes to `dist/`, `bundle-mac.sh` stages it over the placeholder only for the build (a trap restores it) and passes the extra sidecars by `--config`. `git status` was empty after the v0.0.1 freeze and signed build
- [ ] The neural transcriber in the app: left out of the frozen engine for now (TensorFlow doubles it to ~410 MB). Bundle it with its models once `--engine neural` becomes the default (DECISIONS.md 2026-10-19)

## 3e. Sound set and default voices (ROADMAP milestone S)

- [x] Research: instrument libraries and licences (docs/sound-set.md); voice sources and licences (docs/default-voices.md). No hiring: voices come from presets, synthetic LoRAs and open data
- [x] Prototype: `sfizz_render` with the Salamander piano, Growlybass (CC0) and an AVL kit on Amazing Grace; under 2 s a part (docs/sound-set.md)
- [x] Listen: old SoundFont band against the sampled band (sent 2026-10-17)
- [x] Guitars: Karoryfer Black and Green Guitars and Emilyguitar (CC0); Discord GM Martin HD28 steel-string; FreePats nylon; bonus jRhodes3d electric piano (docs/sound-set.md)
- [x] Expressive performance (`copyist/perform.py`, on by default, `--plain` off): phrase dynamics, metric accents, melody contour, timing within about 26 ms, rolled piano chords, pedal, phrase breaths, final ritardando. 8 tests
- [ ] Listen: sampled band, plain against performed
- [x] Wire it in: the band pack downloads pinned and checked (`copyist/instruments.py`, `copyist models download band`, the page's Download button); `render.py` plays one part at a time on sfizz with stems; `mixdown.py` balances by loudness (BS.1770), adds one room and masters to -16 LUFS under -1 dBFS; credits in the report and on the page; SoundFont fallback. 117 tests pass. Amazing Grace: every melody and bass note within half a semitone, parts aligned within about 15 ms
- [x] Melody voice: the VSCO 2 CE clarinet with Copyist's own SFZ (`scripts/instruments/clarinet.py`: VSCO's octave naming, mislabelled F#5 files, silent starts trimmed, tuning, loudness evened, loops for held notes)
- [ ] On the Mac: `scripts/setup-sfizz.sh --instruments`, then build Amazing Grace and listen
- [x] `sfizz_render` as a desktop sidecar: bundled and signed in the v0.0.1 app; the app's engine reports `"sfizz": true`
- [x] Music-box stand-in: VCSL glockenspiel (`bells` pack, ~17 MB), then real celesta. Decision: DECISIONS.md 2026-10-18 (music box / celesta)
- [x] Real celesta (Neil Bickford CC0, ~5 MB subset); music-box style uses it. A crank/comb music box (folkman on Freesound, CC0) still needs a redistributable host. Decision: DECISIONS.md 2026-10-18 (celesta)
- [ ] Orchestra and pit pack from VSCO 2 CE, and a pit-orchestra template for Broadway songs
- [ ] Keys, folk and country, and percussion packs (docs/sound-set.md lists what's found); synths generated by sfizz
- [ ] Research the gaps: banjo, mandolin, ukulele, pedal steel, accordion, snare brushes, choir (nylon and steel guitars are in)
- [x] A guitar part in the arrangements (strummed and picked patterns per style) — 2026-10-18

## 3f. Styles (ROADMAP milestone ST, docs/styles.md)

- [x] Styles as data files, the arranger reading them, 23 styles, swing feel, the gallery, `use-style`, the page's Styles section. Tests arrange every style on a song in each of its meters; the original three styles produce the same MIDI as before, byte for byte
- [x] Listen to the band-preview gallery (published as a page, 2026-10-17). Verdict: "pretty cheesy, pretty 1990s". The one-bar patterns, the bare clarinet melody and the plain mix sound like an arranger keyboard
- [x] `copyist gallery --takes`: a finished YuE2 take in every style (singer and the style's own band), and a page button for it
- [ ] On the Mac: `copyist gallery songs/when-the-saints.yaml --takes` (about 13 minutes), then listen and pick the styles that work
- [x] Exact-preview first cut (2026-10-18): phrase cycles in style files; waltz is piano-vocal with a 4-bar LH/bass phrase and no drums; RH rests (no double-strikes); piano melody skips voice legato (no hammer clicks); quieter accompaniment mix. Owner listened: no glitches. Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Softened ballad, hymn, lullaby (piano-vocal) and broadway-ballad (phrase-cycled arps, clarinet kept). Solo-piano keeps RH but opens melody pitches. Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Softened straight, pop, rock, country (two-bar phrases) and folk (piano-vocal + `keep_rh`). Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Phrase-cycled the remaining styles (gospel, reggae, disco, swing, blues, bossa, power-ballad, broadway-uptempo, march, celtic-jig, jazz-waltz, country-waltz, 6/8 ballad). Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Form build in the performance (band soft → full → settle) and stereo placement in the mix (melody/bass centre, piano left, drums right). Decision: DECISIONS.md 2026-10-18 (less-cheesy exact preview)
- [x] Richer room: slightly longer hall, stereo wet that keeps each part's place (not a mono wash). Decision: DECISIONS.md 2026-10-18 (prosody / room)
- [x] Better exact previews (rest): dedicated guitar staff for folk/country/pop/rock/blues. Default for `write` and the style gallery stays this layer; YuE2 takes stay on demand (`--takes`). Optional SoulX sung guide later. Decision: DECISIONS.md 2026-10-18 (guitar staff); SPEC §15
- [ ] Exact-preview polish still open: real comb music box when hosted; optional SoulX sung guide
- [x] Pipe organ from VCSL (manuals, Quiet + Loud; Copyist's SFZ), `keys` pack, hymn (organ melody + held chords) and gospel (held organ pads). Decision: DECISIONS.md 2026-10-18 (pipe organ and harp)
- [x] Concert harp from VSCO 2 CE; Broadway ballad arpeggios on harp. Decision: DECISIONS.md 2026-10-18 (pipe organ and harp)
- [x] Gospel un-stumbled, then un-kids'-banded, then tonewheel pad under piano (no drums)
- [x] Tonewheel organ from sfizz sine drawbars (`tonewheel` in the keys pack); gospel uses it under the piano tune
- [x] Nylon acoustic guitar (FreePats Spanish classical, CC0); folk fingerpicking plays it. Decision: DECISIONS.md 2026-10-18 (nylon guitar)
- [x] Steel-string acoustic guitar (Discord GM Martin HD28, CC0); country and country-waltz boom-chick play it. Decision: DECISIONS.md 2026-10-18 (steel guitar)
- [x] Electric guitar (Karoryfer Emilyguitar clean, CC0); pop, rock, power-ballad and blues-shuffle play it. Decision: DECISIONS.md 2026-10-18 (electric guitar)
- [x] Fiddle (VSCO solo violin arco vib, CC0); country, country-waltz and Celtic jig melodies. Decision: DECISIONS.md 2026-10-18 (fiddle)
- [x] Flute (VSCO susvib, CC0); Broadway uptempo and march melodies. Decision: DECISIONS.md 2026-10-18 (flute)
- [x] Oboe (VSCO vib, CC0); Broadway ballad melody over harp. Decision: DECISIONS.md 2026-10-18 (oboe)
- [x] Alto sax (Karoryfer Weresax, CC0); swing, jazz waltz, blues-shuffle and bossa melodies. Swing/jazz-waltz drop piano shells under the sax (were discordant). Decision: DECISIONS.md 2026-10-18 (alto sax)
- [x] Guitar part as its own staff (strum patterns, chord shapes), beyond reusing the piano patterns. Decision: DECISIONS.md 2026-10-18 (guitar staff)
- [x] Music box style with real celesta (glock remains as comb stand-in); real crank music box still open
- [x] Prosody and strong-beat checks use Copyist's compound-meter grid (dotted-quarter beats in 6/8 / 12/8), same as the lyric fitter — not music21's beatStrength alone

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
- [x] On the Mac (18 Oct 2026): `copyist write` for Dickinson "Hope" (folk) and Blake "Tyger" (waltz), 4 candidates each, `--device MTL0`. About 30 s for four (plans + band previews). All eight usable. Waltz style line was dropping its trailing `3/4` tag (dedupe ate it); fixed, and ranking now prefers the style's meter
- [x] Owner listened (18 Oct 2026): "sounds fine"; Tyger candidate 4 ("maybe the liveliest") kept as `songs/the-tyger.yaml`. Hope still in `out/hope/write/` if she wants one
- [x] Section rewriting: `copyist rewrite SONG --section --how again|higher|simpler` (swap from write donors, or raise notes and chords together; tests in `tests/test_rewrite.py`)
- [x] Owner kept Tyger higher candidate 3 (+4 → D) after the chord-together fix; page "Try another melody" (again / higher / simpler) on the Song tab
- [x] Rule-based writer: `copyist write --engine rules` (and `auto` fallback without yue-plan); stress, chords, contour, motifs (`copyist/ruleswrite.py`, `tests/test_ruleswrite.py`)
- [x] Page lyric refit: `copyist refit SONG --lyrics` and Song tab "Edit the lyrics" / "Fit lyrics and write the score" (`copyist/refit.py`, `tests/test_refit.py`)

## 3i. Score editing (SPEC §14)

For transcribed and written songs. Both modes ship; neither is a consolation prize.

- [ ] Spec and page sketch: by-ear controls (nudge pitch/length, chord list, "try this bar again") and by-note controls (select on the score, change pitch/duration/chord/lyrics)
- [ ] Write edits back into the song file; re-validate; refresh the engraving and the exact preview
- [x] MusicXML → song file (`copyist import`, `copyist/musicxml_in.py`): lead sheet or vocal line → melody ABC, chords, lyrics, key/meter/tempo. First slice of import; edit round-trip that keeps every Copyist field still open
- [ ] MusicXML edit round-trip (import edits without losing Copyist fields)
- [ ] "Try another version of this bar" uses the melody writer on one section

## 3h. The open singer, plan B (ROADMAP milestone OS, spec: docs/open-singer.md)

A singer anyone may use commercially that follows Copyist's score: HeartMuLa-oss-3B (Apache-2.0) plus MuLaCover's lead-sheet conditioning (Apache-2.0 code), trained by us on data with clean rights.

- [ ] Watch VocalRender (arXiv 2607.27768, pymaster17; Apache-2.0 code + weights) as a possibly cleaner backbone than HeartMuLa + MuLaCover. It's score-native by design: in goes lyrics, MIDI pitches, note values and tempo (interleaved lyric–note tokens, melisma supported), out comes 48 kHz singing, with no separate lead-sheet adaptor needed. Blockers today: released checkpoints are Mandarin-only (training data is all Mandarin singing; the VoxCPM2 base is multilingual, so English is a data/fine-tune problem, not architecture), CUDA-only with ~9.5 GB checkpoints, and its training set names CC BY-NC datasets (M4Singer, GTSinger) under Apache weights. Making it sing English needs English SVS data (our SoulX pipeline or real CC BY voices) plus a rented-GPU fine-tune. Re-evaluate if an English/multilingual checkpoint ships.

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
- [x] Run SoulX on the Mac (`--device mps`) and time it. Measured 2026-10-19 on the M4 Max (local report `.agents/tasks/soulx-timing-2026-10-19/report.md`):
  - **Speed:** about 0.5× real time on the GPU once loaded, plus about 8 s of model load per call. A whole verse takes about 0.8× real time; the CPU takes 2.2–2.8×.
  - **Pitch:** 10 of 10 notes on bars 0–4; 29–31 of 32 on the whole verse.
  - **Fix:** the setup script's torch 2.2.0 crashed on `mps` in SoulX's vocoder. It now pins torch 2.8.0; 2.9+ would break SoulX's `torchaudio.load`.
  - **Install:** in `.cache/SoulX-Singer`, about 3.4 GB, in about a minute. Set `COPYIST_SOULX_DIR` to that folder.
- [ ] Seed SoulX. It has no seed flag and its flow-matching noise is unseeded, so the same score sings differently each run. That breaks AGENTS.md's deterministic-build rule and T1's per-render seeds. A small wrapper that seeds torch before SoulX's CLI would fix it
- [ ] fp16 on `mps`: SoulX halves the model and autocasts only on CUDA, so trying it on the Mac means patching SoulX. Low priority

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

- [x] Measured SheetSage2 (`yue-transcribe`): the most accurate (on the five YuE2 takes, 2026-10-19: note F1 mean 0.97 against neural 0.87 and open 0.83; chords 0.88 against 0.79 and 0.82; lenient metric), but its weights are CC BY-NC 4.0 with no permission for creators to sell, so it's an optional engine and the open one is the default
- [x] The open engine (`copyist/transcribe.py`): Demucs stems (`stems.split_vocals`), beats on band and voice with a steady tempo, meter by testing groupings of eighths (beat first, then bar: 3/4, 4/4, 6/8, 12/8), key, chords (chroma above the bass, Viterbi, the bass naming roots on downbeats), pYIN notes tidied (`clean_notes`: bleed, outliers, scoops, slides that wander, splits, syllable attacks kept, the lyric count), rhythm snapped to the plainest pattern per beat, pitches settled by context, syllable-start hints for the lyric fit
- [x] `copyist transcribe RECORDING --title [--lyrics] [--engine open|sheetsage] [--voice] [--vocals --accompaniment]` and `--keep [--replace] [--build]`; out/<slug>/transcribe/ with source, stems, draft.abc, song file, report with doubts, band playback, transcription.json
- [x] The page: "Transcribe a recording" (upload, title, lyrics, engine with SheetSage's licence spelled out), the result with the original and the band side by side, doubts, notes, "Keep it". Driven end to end in a browser
- [x] SheetSage2 install from the page: `copyist models download sheetsage` (weights + MERT); **Install extras** pack and download-on-transcribe when it isn't installed (licence shown; non-commercial)
- [x] Tests: `tests/test_transcribe.py` (a tune synthesised in the test: notes including a repeated one, rhythm, chords, key, meter; cleaning rules; rhythm snapping; a SheetSage-style draft with a pickup bar through a fake runner) and the page's upload and actions in `tests/test_web.py`
- [x] Evaluation: `scripts/transcribe/evaluate.py SONG.yaml DRAFT.abc [--octave-free]`; the numbers are in docs/transcribing.md
- [x] More sung truth: YuE2 takes of the Saints and Silent Night (`copyist produce … --take truth --device MTL0`); open-engine numbers in docs/transcribing.md
- [x] Soft 6/8 double-tempo lock: when autocorrelation peaks at half the tracked tempo, rebuild the eighth grid and read 6/8 (Silent Night's take was 4/4 @ 108; now 6/8 @ 55)
- [x] Edge-aware beat-chroma smoothing (cosine ≥ 0.55): Saints YuE2 chords 0.70 → 0.83, Amazing Grace 0.75 → 0.78; Silent Night ~0.49 (the take's band often sounds like Em against the written C/G7/F)
- [x] Ornament / re-articulation folding in the open engine (`clean_notes` + post-snap grid merge; tighter lyric count; median outlier drop): Saints YuE2 take notes 0.68 → 0.74 (35 vs 33 true; chords stay 0.83). Equal-weight repeated syllables still kept
- [x] Score a transcription against a recording when there is no written truth: `scripts/transcribe/evaluate.py --sung VOCAL.wav SONG.yaml`. Never commit owner songs
- [x] Round-trip harness: `scripts/transcribe/roundtrip.py` (truth take → open engine → note/chord F1 table). Baselines: Saints 0.74/0.83, Silent Night 0.75/0.40. Improve only when this table moves
- [x] Saints late-downbeat snap: solo eighth reading cost 0.05 → 0.25 (note F1 0.74 → 0.79; Silent Night flat). Still headroom to ~0.88 at looser onset match
- [x] Tyger truth take in the round-trip loop; waltz guard on double-tempo→6/8 (Tyger 0.67/0.62 @ false 6/8 → 0.69/0.73 @ 4/4 ~108; Silent Night stays 6/8)
- [x] Tighter re-articulation (short < 0.25 s, gap < 0.25 s): Tyger note F1 0.69 → 0.76; Saints 0.79; Silent Night 0.75 → 0.74
- [x] Amazing Grace in `roundtrip.py` (0.82 / 0.77); lyric-undershoot → gentle fragment retry: Silent Night 0.74 → 0.76 without dropping Saints/Tyger/AG
- [x] Bigger stress case: *Major-General's Song* (`songs/major-general.yaml`, ~128 notes). Truth take produced; lyric-guided `split_toward_target` + grid-fold floor: note F1 0.44 → 0.79 (117 vs 128). Key still misread as C#m; chords 0.46
- [x] Key from best of acc/mix/vocal/melody chroma (`choose_key`); mix chroma for chords when the band stem disagrees. Major-General → Eb, chords 0.46 → 0.61; Tyger chords 0.81
- [x] Lyric note target includes `_` holds; keep long high notes near the line; gentler split cap. Silent Night 0.76→0.77 (42 vs 46); Amazing Grace 0.82→0.88; Major-General 0.84 / 128 vs 128
- [x] Chord tonal prior (I/IV/V) + dearer mid-bar changes in compound meter + wider smooth: Silent Night chords 0.40→0.69; Saints 0.83→0.89; Amazing Grace 0.78→0.91; Major-General 0.61→0.79 (notes flat)
- [x] Cap consonant onset pull at 0.08 s: Silent Night note F1 0.77→0.80; Tyger 0.76→0.78 (still 42 vs 46 — missing pitches aren't in long same-pitch holds)
- [x] Scoop fold when lyric overshoot ≥ 2: Saints 0.79→0.85 (33 vs 33); AG/Tyger flat (single extras stay)
- [x] Open-transcriber home repo as submodule: [Digital-Defiance/open-transcriber](https://github.com/Digital-Defiance/open-transcriber) → `open-transcriber/`
- [x] T0 Basic Pitch + T0b adaptive / `clean_notes`: mean ~0.87 vs open 0.83; SN +0.05, Tyger +0.19; Saints/AG/MG within 0.02 — `open-transcriber/docs/t0-results.md`
- [x] Magenta MT3 skipped for sung melody (not trained on singing); YourMT3 licence unclear
- [x] Omnizart chord wrapper + setup script; native arm64 `nnls-chroma` Vamp plugin built via `vamp-plugin-sdk` on Apple Silicon
- [x] `copyist transcribe --engine neural` wired (BP melody + open harmony); default stays `open`
- [x] Close note gaps on truth takes: adaptive candidate selection tuned; Saints 0.85 (tied), AG 0.89 (+0.01), SN 0.85 (+0.05), Tyger 0.97 (+0.19), MG 0.83; mean 0.88 vs 0.83
- [x] Full `roundtrip.py --engine neural` lead-sheet draft benchmark: mean 0.87 vs 0.83 (Saints 0.91 vs 0.85, Tyger 0.93 vs 0.78, AG 0.89 vs 0.88, MG 0.84 tied)
- [ ] **NEXT:** Silent Night draft 6/8 compound rhythm snapping (0.78 vs 0.80) to make neural an across-the-board win; T1 domain training on synthetic stems
- [ ] Two big public-domain songs for the round-trip set (owner, 2026-10-19), so the benchmark stops being five short major-key songs that the rules were tuned on. Between them: a minor key or a minor/major switch, a key change, real syncopation, harmony past I/IV/V, a compound meter other than slow 6/8 (12/8 or a brisk 6/8), a range of about a 12th with leaps, held notes and melismas, and a repeated chorus (each take about 150+ sung notes, 2.5+ minutes, two or more verse/chorus cycles). Words and music published before 1929, transcribed from a named, dated edition, every verse screened. Then YuE2 truth takes (`follow` at 90% or more), both engines on all seven songs, and the Silent Night and Major-General gaps judged on all seven
  - Blocked so far: five open-ended research runs stopped with the API error "Improperly formed request". Probes ruled out any single tool, phrase or effort setting. Next try: pick the two songs directly, then give each song its own small steps (a script, not the agent, tabulates the benchmark songs; words are downloaded to files and cited by verse and URL, never quoted in reports)
- [ ] T1: train the neural transcriber. The owner wants this soon, as soon as the non-training passes run out (two attempts in a row that don't move either benchmark table). Plan written 2026-10-19 (local report on the Mac: `.agents/tasks/t1-training-plan-2026-10-19/report.md`):
  - Model: a small lead-sheet model of Copyist's own (5–10M parameters; MIT code, MIT weights (owner, 2026-10-19); run with ONNX, so the app needs no TensorFlow) on frozen Basic Pitch outputs plus a log-mel of the Demucs vocal. Fallback: the GAME architecture (MIT code), trained on our data
  - Data: melodies from a widened rule-based writer (minor keys, 6/8 and 12/8, syncopation, melismas, patter), sung by SoulX-Singer with CC BY 4.0 VocalSet voices over the sfizz band, mixed, then separated with Demucs. Labels are exact by construction and checked note by note. Never `songs/`, the owner's songs, Suno, or SheetSage output
  - Compute: Mac only (owner, 2026-10-19; no rented GPU).
    - **Singing data:** 30 hours of SoulX singing takes about 16 h of GPU, if one long-lived SoulX process sings many phrases, or about 23 h at one call per verse (measured 2026-10-19, TASKS §4). The render pipeline should keep SoulX loaded rather than start it per phrase.
    - **Mixing and Demucs** come on top.
    - **Training:** a run takes about 2–5 hours. The audit's re-scope changes the training budget (see the design audit below).
  - It fixes note-level errors (patter onsets, ornament or real note, stray extras, onset timing), not Silent Night's 6/8 snap, The Tyger's meter, or the chords
  - Mind the yardstick: SheetSage2 is now measured on all five takes (mean 0.97 notes, against neural 0.87). The metric is lenient, and the takes are YuE2 renders from SheetSage2's own lab. Today's numbers are also scored on the same takes the rules were tuned on
  - Build-on check (owner asked, 2026-10-19): Basic Pitch and SoulX remain the right foundation. Basic Pitch isn't used as the transcriber, only as a frozen feature under our own trained head, so its raw accuracy doesn't gate us; it's the only strong, genuinely Apache-2.0, small, ONNX-shippable option. SoulX stays the English-singing data source for v1. Newer options checked and set aside: VocalParse-1.7B (Mandarin audio-LLM, too big, crawled training data); T3MS / phoneme-informed / VOCANO / ROSVOT transcribers (research-grade, weights trained on CC BY-NC singing sets). Watch: VocalRender (arXiv 2607.27768, pymaster17, Apache-2.0 code + weights) is a score-native SVS that would simplify the data pipeline, but its released checkpoints are Mandarin-only (training data, not architecture; base is multilingual VoxCPM2). Re-evaluate for plan B (§3h) if an English or multilingual checkpoint ships
  - [x] Owner decisions (2026-10-19): OK to build on Basic Pitch and SoulX; Mac only (no rented GPU); MIT for the weights; run SheetSage once on all seven test songs as a yardstick (evaluation only); start the T1a data code now (CPU-only, no GPU); YuE2 audio as training material: yes, in the second data round. That means renders of sampler scores only (never held-out tunes), each phrase aligned and checked note by note, melody labels only, kept as a separate tagged slice so a model can be retrained without it. The published terms were checked on 2026-10-19 and nothing in them prohibits this (details in DECISIONS), so it goes ahead. Later: the share-alike drum kit in training audio, volunteer-typed old tune books, which of her songs for the final listen, switching the default
  - [x] The benchmark leak in docs/open-transcriber.md is flagged there: `songs/` and the round-trip cases are held out, evaluation only. The tested fingerprint filter comes with T1's data code
  - [x] T1a foundation (2026-10-19, open-transcriber 2f90e7f): the held-out guard (`open_transcriber/data/heldout.py`: the list is read at runtime from `songs/` and the round-trip cases; transposition- and tempo-invariant melodic fingerprints plus title and lyric matching; tests include a transposed, re-rhythmed Amazing Grace that must be rejected) and a seeded, data-only score sampler (`open_transcriber/data/scores.py`: 24 keys, 2/4 to 12/8, 50–180 BPM, syncopation, ties, pickups, melismas, patter, leaps, chromatic tones; a public-domain lyric pool with sources; a 200-song batch had 0 validator fails and 0 leaks). `docs/open-transcriber.md`'s data section and T1 phase now keep the benchmark out of training. Tests: 278 parent, 34 submodule
  - [x] Design audit (2026-10-19; local report `.agents/tasks/open-transcriber-audit-2026-10-19/report.md`). The owner wants "hands down the best" and to beat SheetSage2 objectively, for songs, musicals, Broadway and orchestral music, on the M4 Max only. Findings:
    - **What SheetSage2 can't do:** triplets, swing or 12/8; tempo changes (one tempo anchor); more than one vocal line; lyrics; chords past sevenths. Key changes are never scored.
    - **Its own tests:** RWC-Pop 82.5 and Rock Corpus 67.1 (pitch class, 50 ms). About half the Rock Corpus songs are in the HookTheory data it trained on, and it scores 6.6 points higher on those (not significant). Its fair Rock Corpus bar is about 64.5.
    - **T1 as planned** (a head on Basic Pitch plus log-mel) almost certainly won't beat it on pop and rock. It could on lyric-given vocals. T1 is re-scoped to multi-task heads on the winner of an encoder bake-off (MusicFM, Dasheng, HeartCodec's encoder, Whisper). It keeps Basic Pitch as a side input and gets structured decoding.
    - **The judge:** real, licence-clean recordings, never YuE2 takes. That's SheetSage2's own two tests, reproduced; neutral sets; and COTB-v1, about 120 public-domain recordings (musicals, choir, band, orchestral, syncopated, old), with performance-aligned truth checked by ear. Scored with strict metrics (octave-exact 50 ms F1, MV2H, notation edit distance, meter, key, underlay), paired bootstrap tests, and a pre-registered decision rule.
    - **Roadmap:** stage 0, the judge (3–4 weeks); stage 1, rhythm and notation decoding (3–4 weeks, overlapping); stage 2, the encoder bake-off and heads (5–7 weeks); stage 3, real data and priors (4–6 weeks); stage 4, the one-time test; stage 5, the product. About 4–5 months of GPU nights on the M4 Max. Full orchestral scores stay a research goal; orchestral lead sheets and short scores are the promise.
  - [ ] Owner decisions on the audit (plain words at the end of its report):
    - testing-only use of non-commercial test sets and systems (RWC, MuScriptor, YourMT3+);
    - buying the Rock Corpus recordings (about $200–400, testing only);
    - real recordings as the judge;
    - about 6–10 hours of listening;
    - open-licence encoders whose training data can't be checked;
    - self-labelled CC0/CC BY music;
    - song format `copyist-song/1` (triplets, key, meter and tempo changes, repeats, a second voice);
    - an external SSD later;
    - claiming "best" only after the one-time test.
  - [ ] Stage 0, the judge (after the owner's decisions and the key-change fix, which touches the same scorer): timed-event outputs from every engine; SheetSage2's scorer replicated and reproduced on RWC-Pop and Rock Corpus with its official implementation (testing only); the strict metric suite and bootstrap; a 40-recording COTB pilot, then 120; baselines run once
  - [ ] The open-transcriber README still says Omnizart chords are blocked on Apple Silicon; they run natively since the arm64 nnls-chroma build (DECISIONS 2026-10-18). Fix it with the next submodule change
  - [ ] SheetSage2 once on all seven test songs as a yardstick (evaluation only; owner OK 2026-10-19). Five done 2026-10-19 on the M4 Max, about 5 s a take. Notes: Saints 0.97, Silent Night 0.96, Amazing Grace 0.94, Tyger 1.00, Major-General 0.98. Chords: 0.87, 0.91, 0.97, 0.91, 0.74. It reads The Tyger's 3/4 right and writes Silent Night as 3/4. Docs: docs/transcribing.md; raw outputs: `out/<slug>/sheetsage-yardstick/`; script: `.agents/tasks/sheetsage-yardstick-2026-10-19/yardstick.py`, which reads roundtrip's CASES. The two big songs get the same single run when they land
  - [ ] Key changes break Copyist's ABC readers (found by the yardstick run, 2026-10-19). `abcplan.parse` keeps only the bars after the last `K:` line, and a mid-bar `[K:…]` stops it with a PlanError; evaluate.py's chord reader (`parse_any`) resets the same way (read, not run). SheetSage2 writes a key change as `K:` in both voices. Fix with tests before the big songs, since one should change key
  - [ ] Widen `evaluate.py`'s ±14 s shift search, or align on the first sung note: SheetSage2 keeps intro bars, and its best shifts on the five takes were already −8.4 to −11.5 s, so a longer intro would mis-score
- [ ] SheetSage ABC through the same fold/tidy path
- [ ] Owner listen check on June Snow / other songs only after a table win. Never commit them
- [ ] Repeats vote (SPEC 12.2a step 3): the same section sung again settles doubtful notes
- [ ] Per-doubt A/B by ear (SPEC 12.2a step 7), writing the choice back into the song file
- [ ] Bass line, drum groove and band parts (SPEC 12.1); analysis by synthesis (SPEC 12.2 step 4)
