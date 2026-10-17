# Copyist tasks

If you're picking up this work, start here. Tick a box when its task is done and verified, and add new tasks where they fit.
Background: [SPEC.md](SPEC.md) says what to build, [ROADMAP.md](ROADMAP.md) lays out the milestones, [DECISIONS.md](DECISIONS.md) records why, and [AGENTS.md](AGENTS.md) has the rules.

Last updated: 2026-10-17.

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
- [x] YuE2 export (`copyist/yue.py`): the score becomes YuE2's ABC dialect plus a request with style, lyrics, abc and seed. mlx-Yue's `abc_tools inspect` accepts it, and its notes match ours exactly

## 1. Push

- [ ] `git push`: 7 commits are waiting (the docs, the web front end, the voice LoRA, follow and the octave fix)

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
- [ ] **Running now** (started 2026-10-17 around 11:00 Pacific; step 320 of 800 at 12:35, about 15 s a step, held-out loss falling 4.77 → 3.87; the first checkpoint, step 300, is saved). It was started with `scripts/setup-yue-train.sh`, then `scripts/yue-lora/run.sh .cache/lora/lights-on/songs.jsonl ~/Documents/lights-on-audio lights-on`. Watch the first steps for s/step and memory. If PyTorch's mps backend fails on an op, it falls back to the CPU for that op (PYTORCH_ENABLE_MPS_FALLBACK); if it's too slow, try `--max-len 6144`
- [ ] Listen: `produce --lora` with steps 300–800 and the Jennifer style line, check each with `follow`, and pick one
- [ ] If the score fights the voice: train with each song's own score too (SheetSage2 transcription, `cot=full` prefixes)
- [ ] Use the realaudio NAR adapter (`nar_lora_joint_v9.bf16.safetensors`) in `copyist produce` (`--adapters`), and compare it by ear with a plain render

## 3c. Web front end (docs/web.md)

- [x] `copyist serve`: a local page for songs, lyrics and checks, the score as pages, takes with players, making a take, checking the melody, and voice-training progress. Tested here (server tests, and screenshots in light, dark and phone widths)
- [ ] Use it on the Mac for a real take with a trained voice
- [ ] Compare two takes side by side; mark a favorite take
- [ ] Write a new song from the page (needs melody proposals, M2)
- [ ] Hosting for other people (accounts, a GPU queue): later

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
- [ ] Style profiles beyond waltz, ballad and straight
- [ ] Direction checks in the report: style, instruments, tempo, mood
- [ ] Melody proposals: Copyist offers several melodies, renders each, and the person picks by ear

## 7. Transcribing recordings (MT, SPEC §12)

- [ ] Stems, then measurement, then a draft score, then refinement by rendering and comparing against the recording
