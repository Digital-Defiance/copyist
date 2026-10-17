# Singing

`copyist sing` turns a song's voice part into a sung vocal with **SoulX-Singer** (Apache-2.0), checks every sung note's pitch against the score, and mixes the vocal with the band.

```
copyist sing songs/amazing-grace.yaml                 # verse 1, whole song
copyist sing songs/amazing-grace.yaml --bars 0-4      # just bars 0 to 4 (quicker)
copyist sing songs/amazing-grace.yaml --verse 2
```

Output goes to `out/<song>/sung/<verse>[-bars…]/`:

- `vocal.wav`: the sung vocal (24 kHz)
- `mix.wav`: the vocal over the band
- `report.md`: the pitch check, listing any note that missed by more than a quarter tone
- `soulx-target.json`: exactly what was sent to the model

## Setup (once)

1. Install Copyist with the singing extras: `pip install -e ".[sing]"`
2. Install SoulX-Singer next to Copyist: `scripts/setup-soulx.sh` (about 6 GB; it downloads the 2.8 GB model and Whisper-base).
3. Add the two `export` lines it prints to your shell profile.

On an Apple Silicon Mac it tries the GPU (`mps`) first and falls back to the CPU for anything the GPU can't do; force one with `--device cpu` or `--device mps`. On a 2-core cloud machine with no GPU, 7 seconds of singing took about 3 minutes; expect a Mac with many cores or a GPU to be much faster.

## Voices

The singer's voice comes from a short **reference recording** (a "prompt") plus its metadata (lyrics, notes and pitch), not from training. Without `--voice`, Copyist uses the English example voice that ships with SoulX-Singer. **Use that for testing only;** its source and licence aren't documented.

Voices stay in the git-ignored `voices/` folder and are never committed or published; a voice Copyist ships must come with the singer's permission (SPEC section 6). To make a voice:

1. Record the singer: 10 to 30 seconds, dry (no reverb), one voice, in their comfortable range, singing something with known lyrics.
2. Run SoulX-Singer's preprocessing on it (`example/preprocess.sh` in the SoulX-Singer folder) to get the matching `.json`, and fix any misaligned notes with its MIDI editor.
3. `copyist sing … --voice singer.wav` (Copyist looks for `singer.json` next to it).

## Don't use AI-generated vocals as voices or training data

Suno's terms (September 2026) forbid using its output "to power, enable or train other artificial intelligence and machine learning models" and to "create, develop or improve any competing products or services". Copyist is a competing product. Treat other generators' terms the same way until checked. Use people who have agreed, and public-domain or openly licensed material.

## How Copyist talks to SoulX-Singer

SoulX-Singer's English input is per word: a word sung over several notes is repeated on each note, marked `2` on its first note and `3` after (extra syllables and held notes alike); silences are `<SP>` marked `1`. Phonemes are CMU ARPAbet with stress, written `en_AH0-M-EY1-Z-IH0-NG`. Words missing from the CMU dictionary go under `pronunciations:` in the song file:

```yaml
pronunciations:
  zorblax: Z AO1 R B L AE0 K S
```

Songs are split into phrases of about 8 seconds at word starts; each phrase is sung separately and placed on one timeline. The model runs in score mode, so it follows the written notes; the pitch check confirms it did.
