# Production audio

`copyist produce` sends a song's own score to **YuE2** and gets a stereo recording back. The score stays the source of truth: YuE2 is asked to perform the notes Copyist wrote, not to invent a new tune.

```
copyist produce songs/amazing-grace.yaml                 # verse 1, 4-bar intro
copyist produce songs/amazing-grace.yaml --verses 4
copyist produce songs/amazing-grace.yaml --seed 831001 --device MTL0
copyist produce songs/amazing-grace.yaml --takes 4 --take try   # four takes in one run: takes/try-1 ... try-4
```

Output goes to `out/<song>/production/`:

- `production.wav`: the recording, 48 kHz stereo
- `yue-request.json`: exactly what was sent (style, lyrics, the score, both seeds)

## Checking that it sang our tune

A production is only useful if it performs the score. `copyist follow` checks that, note by note. It works best on the separated vocal: a full mix makes the pitch tracker follow the band. Separate with Demucs (in `.cache/demucs`):

```
.cache/demucs/.venv/bin/demucs -d mps --two-stems vocals --other-method none \
  -o out/amazing-grace/production out/amazing-grace/production/production.wav
copyist follow songs/amazing-grace.yaml out/amazing-grace/production/htdemucs/production/vocals.wav
```

YuE2 doesn't keep Copyist's clock exactly: it shortens the intro and drifts a little. So `follow` first finds the recording's overall timing (up to `--search` seconds early or late; default 3), then lets each 4-bar phrase drift up to 0.6 s from it. It counts a note sung in any octave and says which octave; `--written-octave` turns that allowance off. It writes `<recording>-follow.md` beside the recording and exits non-zero if fewer than 80% of notes match (`--pass-share`).

## YuE2 sings an octave below what it's given

Measured on Amazing Grace verse 1, seed 831001:

| Melody in the ABC | What YuE2 sang | Notes matched | Timing |
|---|---|---|---|
| as written (D4–D5) | D3–D4, an octave below | 32 of 32 | 0.9 s early, easing to 0.4 s |
| an octave up (D5–D6) | D4–D5, the written octave | 30 of 32 (29 in the written octave) | about 1.9 s early |

The spectrum confirms the first voice really was down there; it wasn't a tracking error. So `copyist/yue.py` writes the vocal one octave above where it should sound (`SUNG_OCTAVE_BELOW = 1`), and `copyist produce --octave 0` turns that off. The second render was on a 2-core CPU with 8 flow steps instead of 32, so it sounds rougher than a Mac render; the notes come from the earlier stage and aren't affected.

A strict check at the planned time scored 0 of 32 on the first render. That's why `follow` has its allowances.

On an Apple M4 Max, that verse (47 seconds, Metal, `MTL0`) rendered in 45 seconds.

## Setup (once)

The quickest way to get the model files is `copyist models download singer --accept-licence` (it prints the licence first without the flag), or the sound tab of `copyist serve`. They go into Copyist's data folder (`copyist models` says where). The renderer itself still comes from the build below.

The engine is [yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp) (MIT), which runs YuE2's weights. On a Mac the build turns Metal on by itself. `scripts/setup-yue.sh` clones it into `.cache/yue2.cpp`, builds it, and downloads the weights into `.cache/yue/` (it uses `huggingface_hub` from the Copyist environment):

- `YuE2-3B-Q6_K.gguf` (the model)
- `YuE2-Vae-F32.gguf` (the decoder; this one is never quantized, because its weights are the audio)

Then add the lines the script prints to your shell profile:

```
export COPYIST_YUE_SYNTH=".cache/yue2.cpp/build/yue-synth"
export COPYIST_YUE_MODEL=".cache/yue/YuE2-3B-Q6_K.gguf"
export COPYIST_YUE_VAE=".cache/yue/YuE2-Vae-F32.gguf"
export COPYIST_YUE_DEVICE=MTL0
```

Paths can be absolute. `MTL0` is the Mac GPU. Leave the device unset and yue-synth picks one.

## Licence

The YuE2 weights (including these GGUF conversions) are CC BY-NC 4.0, with an extra permission dated 16 September 2026: an individual creator may sell the songs they generate. A company needs a separate licence from the YuE team before it uses the weights commercially. Copyist does not ship the weights. See [DECISIONS.md](../DECISIONS.md).

## What gets sent

The request is YuE2's own ABC, not Copyist's song file. Two voices, `Vocal` and `Ins`; chord symbols in the vocal part; a pickup padded with a rest so every bar is complete; an intro of the tune's opening chords with no melody. Both seeds in the request are the `--seed` value, so the same song file and seed render the same recording. The requested length is the length of that score.
