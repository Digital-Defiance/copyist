# The open singer (plan B): spec

**Goal:** a singer anyone may use commercially, open under licences no stricter than Apache-2.0, that performs Copyist's score: the written melody and chords, the lyrics, and the style. It's the fully open counterpart to YuE2, whose weights are CC BY-NC 4.0 (individual creators may sell their songs; companies may not use it). This is milestone OS in ROADMAP.md, chosen by the owner on 17 October 2026.

Status: planned, and the source code below has been read. Nothing is trained yet. TASKS.md section 3h lists the steps in order.

## Why build it

The open song models of 2026 don't take a melody:
- HeartMuLa-oss-3B (Apache-2.0, January and February 2026) writes its own melody from lyrics and tags;
- ACE-Step 1.5 (MIT) does the same.

The two models that do follow a melody (MuLaCover, MiniMax Music 3) have non-commercial weights. For Copyist, a singer that ignores the score breaks the product: the sheet music must be what's sung.

## The recipe: MuLaCover's method, our own weights

MuLaCover (HeartMuLa team, September 2026) proves the method on this exact model family. Its source code is Apache-2.0 (github.com/HeartMuLa/MuLaCover); only its weights are non-commercial. We reuse the code and train our own conditioning weights on data with clean rights.

**The base: HeartMuLa-oss-3B, frozen.** Weights from HeartMuLa/heartlib, "HeartMuLa-oss-3B-happy-new-year", the recommended checkpoint.
- A Llama-3.2-style backbone: 28 layers, width 3072, 24 heads, 8 KV heads, vocabulary 128,256.
- A 300M local decoder over 8 audio codebooks of 8,197 entries.
- HeartCodec turns tokens into 48 kHz audio.
- The prompt is `<tag>…</tag>` tags, a reference-audio slot, then lowercased lyrics.

**The new part, MuLaCover's symbolic conditioning** (`src/mulacover/modeling.py`, `symbolic.py`):
- **The condition** is a lead sheet on a sixteenth-note grid, in beat space, not seconds; the tempo stays free and the model learns the alignment. Per sixteenth:
  - melody onset and sustain (128 × 2);
  - drum pianoroll (128);
  - chord chroma (12).

  Inputs are `(onset, pitch, length)` rows in sixteenths. `SymbolicCondition.from_midi` reads melody, chord and drum MIDI files. The maximum length is 5,000 sixteenths.
- **`SymbolicAdaptor`:**
  - linear layers squeeze each stream to 24 dimensions;
  - they're fused to 512;
  - a 2-layer, 8-head transformer runs over them;
  - the result is projected to 3072.
- **`CrossAttentionLayer`** sits on each of the backbone's last 8 layers (`peft_layer_num = 8`):
  - its own adaptor, accumulated across layers;
  - gated cross-attention from the audio stream to the condition, with rotary positions on both;
  - a tanh gate that starts at zero, so training begins from the untouched base model.
- **Partial conditioning:** `context_mask` lets the melody or the chords be left out.
- **MuLaCover's `StyleMLP`** (Qwen tag embeddings) is optional. Start with HeartMuLa's own tag conditioning and add it only if styles need help.

**Training:**
- Teacher-forced next-token cross-entropy on the HeartCodec tokens of real songs, the same loss HeartMuLa trains with, given:
  - their tags and lyrics;
  - the lead sheet transcribed from their audio.
- The base is frozen. Train the adaptors and the cross-attention, roughly 300M parameters. Optionally add a small LoRA on the last 8 layers if following stays weak.
- Drop the condition 10% of the time so classifier-free guidance works.
- MuLaCover's training code isn't published, so this loop is ours to write. `scripts/yue-lora/train.py` is the model to follow: mps, CUDA or CPU, resumable, evals on held-out data, memory-saving attention.

## Data: every source with clean rights

| Source | Rights | Role |
|---|---|---|
| Songs HeartMuLa-oss-3B generates | Apache-2.0 model, so outputs are unrestricted | The bulk: thousands of songs across Copyist's style words (copyist/styles/*.yaml `production`) and varied lyrics |
| Lyrics for those songs | Public-domain poems and hymns; original lyrics written for the project | Lyrics |
| Creative Commons recordings with vocals (FMA and Jamendo tracks marked CC BY or CC0) | Per-track licence, checked and recorded | Real performances, mixed in once the pipeline works |
| US public-domain recordings (published in 1925 or earlier) | Public domain | Optional; old recording quality |

**Never used:**
- copyrighted recordings;
- YuE2, MuLaCover or MiniMax outputs (non-commercial terms);
- Suno or Mozart outputs (their terms forbid training competitors);
- the owner's own songs and voices. Those train only her private LoRAs and never go into a public model.

Keep a manifest of every training item with its source and licence (SPEC section 10).

**Transcription, audio to lead sheet**, using Copyist's own tools where possible:
1. Vocal: Demucs separation (`copyist/stems.py`), then pYIN (`copyist/pitch.py`'s tracker), then notes.
2. Beats: librosa's beat tracker gives the beat grid and the sixteenths.
3. Chords: the Music X Lab large-vocabulary chord model (MIT, adapted inside MuLaCover's code).
4. Drums: optional at first.

YourMT3, which MuLaCover uses for melody, has a GPL-3.0 upstream licence and checkpoints of unclear terms. Use it only after checking the licence, and only as a tool to make labels; don't ship it.

**Quality gate:** keep a song only if its transcribed melody, played back with Copyist's band, passes `copyist follow` against the original vocal at 90% or more. A label that doesn't match its audio teaches the model to ignore the condition.

**Amount:** start with 1,000 songs, about 33 hours of audio. MuLaCover's paper isn't out, so the right amount is a measurement: train, check following, add data.

## Compute

| Step | The owner's Mac (M4 Max, 64 GB) | A rented GPU (A100 or H100) |
|---|---|---|
| Generate 1,000 two-minute songs | HeartMuLa's speed on mps is unmeasured; guess 2 to 4 times real time, so 70 to 130 hours | About real time: about 33 hours, about $50–100 |
| Transcribe | Demucs on mps was fast (141 songs in an afternoon); pYIN on CPU | Same |
| Train the adaptor, 5,000 steps | About 10–15 s a step (the YuE2 LoRA ran 15 s a step at a similar size): about 17 hours | About 1–2 s a step: about 2 hours |

So the plan works on the Mac alone over a week or two, or in about a day with a few hundred dollars of GPU time. The owner decides which; nothing in the code should assume either.

## Using it in Copyist

- `copyist produce --singer open`:
  - writes the song's exact melody, chords and drums (from the arrangement MIDI) as `SymbolicCondition` rows;
  - writes the tags (the style's `production` words) and the lyrics;
  - generates and decodes;
  - checks the take with `copyist follow`, as YuE2 takes are checked.
- On the page, a "Singer: YuE2 / Open" choice beside the voice, with each singer's licence shown.
- The weights download like the other models (`copyist/models.py`): pinned, checked, resumable, with the Apache-2.0 notice.

## Phases, each with its test for "done"

| Phase | Work | Done when |
|---|---|---|
| B0 Feasibility | Run HeartMuLa-oss-3B on the Mac (mps) and in the container (CPU, short clip). Measure speed and memory. Read `music_generation.py` for the exact prompt layout and frame rate. Run MuLaCover's adaptor code on random weights against the HeartMuLa backbone: shapes line up, output matches the base when the gate is zero. | A 30 s HeartMuLa song generated on the Mac; the adaptor bolted on with zero effect at init (test) |
| B1 Data pipeline | `scripts/open-singer/generate.py` (tags × lyrics → songs and a manifest), `transcribe.py` (song → lead sheet rows and a quality score), `tokenize.py` (song → HeartCodec tokens) | 50 songs end to end, each with tokens and a lead sheet; the quality gate rejects bad transcriptions (tested on a deliberately shifted label) |
| B2 Training | `scripts/open-singer/train.py`: frozen base, adaptors trained, evals on held-out songs (loss with the real condition against a shuffled one; the gap is the model listening) | Loss with the true condition clearly below loss with a shuffled condition, held out |
| B3 Following | Generate from Copyist scores (Amazing Grace, the Saints, Silent Night) in several styles; `copyist follow` | 90% or more of the notes followed on all three, in the written octave or one octave off |
| B4 Product | `copyist produce --singer open`, the page choice, the model download, docs | The owner makes a take with the open singer from the page |

## Risks

- **Following may stay weak with only 1,000 songs.** Mitigations:
  - more data;
  - a LoRA on the last layers;
  - more conditioned layers;
  - a stronger condition dropout schedule.
- **Generated training songs carry HeartMuLa's habits, good and bad.** Mix in Creative Commons recordings once the pipeline works.
- **Transcription errors become training errors.** The quality gate is the defence; keep it strict.
- **The 7B HeartMuLa may arrive.** The adaptor design carries over (MuLaCover's code takes a flavor).
