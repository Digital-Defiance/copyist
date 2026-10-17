# Copyist tasks

If you're picking up this work, start here. Tick a box when its task is done and verified, and add new tasks where they fit.
Background: [SPEC.md](SPEC.md) says what to build, [ROADMAP.md](ROADMAP.md) lays out the milestones, [DECISIONS.md](DECISIONS.md) records why, and [AGENTS.md](AGENTS.md) has the rules.

Last updated: 2026-10-16.

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

- [x] `git push -u origin main`. Push again after each commit

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

- [ ] Compare the three voice prompts by ear, each singing Amazing Grace bars 0–4:
  `copyist sing songs/amazing-grace.yaml --bars 0-4 --voice voices/<name>.wav --out out-<name>`
- [ ] Separate a solo vocal from a full mix that has no stems. Demucs 4.1.0 is installed in `.cache/demucs` (`-d mps --two-stems vocals`). Amazing Grace's production vocal is separated. Still to separate: the Lights On mixes and the experimental songs that have no `Lead Vocals` stem. Voices stay in `voices/` and are never committed or shipped (see DECISIONS.md)
- [ ] Make a voice from the separated vocal: `copyist voice separated.wav --name <name> --lyrics <lyrics file>`, then sing with it
- [ ] Add tests for `voiceprompt.py`: `smooth_contour` octave folding, `split_notes` on a synthetic contour, `clean_hint`
- [ ] Choose a default voice and record the choice in DECISIONS.md

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
