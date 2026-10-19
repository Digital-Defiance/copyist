# Open lead-sheet transcriber (a better SheetSage we can ship)

**Goal (owner, 2026-10-19):** the best open transcriber available. It must beat SheetSage2 objectively — on SheetSage2's own benchmarks and metric, and on full lead-sheet measures — for songs, musicals and beyond, with MIT code and MIT weights and no CC BY-NC anything, trained on the owner's M4 Max only. A design audit is under way before anything is trained (local report: `.agents/tasks/open-transcriber-audit-2026-10-19/`). First milestone, unchanged: beat Copyist's open engine on `scripts/transcribe/roundtrip.py`.

**Code:** first-party repo [Digital-Defiance/open-transcriber](https://github.com/Digital-Defiance/open-transcriber) (MIT), vendored here as the git submodule `open-transcriber/`.

```bash
git submodule update --init open-transcriber
```

Status, 19 October 2026: submodule in place; **adaptive BP + `clean_notes`** (see `open-transcriber/docs/t0-results.md`) mean note F1 ~0.87 vs open 0.83; `copyist transcribe --engine neural` wired (default still `open`). Magenta MT3 skipped for singing; Omnizart chords run natively on Apple Silicon since the arm64 nnls-chroma build. SheetSage2 remains optional and non-commercial. The 2026-10-19 design audit re-scopes T1 and moves the judge to real recordings (TASKS §7).

## Why

SheetSage2 is the strongest system we've measured. On our five YuE2 takes its mean note F1 is 0.97 (range 0.94–1.00), against neural 0.87 and open 0.83, and its chord accuracy is 0.88 (2026-10-19, docs/transcribing.md). That's with our lenient metric (onsets within a quarter of a beat, octave-free, best shift and tempo searched), on takes from its own lab's generator. Its own model card uses a strict one (pitch class, 50 ms onsets, no offsets) and reports 82.5% vocal note F1 on RWC-Pop and 67.1% on Rock Corpus, so it is far from perfect on real recordings. Its weights are CC BY-NC 4.0 with no creator-sell permission. Shipping it as the product default is a licence dead end. Closing the gap with more chroma heuristics helps (Silent Night chords 0.40→0.69 with tonal priors; Saints notes 0.85), but a trained model is the honest long-term path for Broadway-dense singing and band voicings that disagree with lead-sheet labels.

## What we will not do

- Fine-tune or redistribute SheetSage / MuScriptor weights (NC).
- Train on Lights On audio, Suno outputs, or any recording we can't prove rights for.
- Replace the open engine until the same round-trip table says the new engine wins and no row collapses.

## Licence stack (must stay MIT/Apache)

| Piece | Role | Licence |
|---|---|---|
| Demucs | vocal / band stems | MIT |
| small lead-sheet head on frozen Basic Pitch posteriors + log-mel (ONNX) | sung melody + chords → note events | MIT code, MIT weights |
| Omnizart (optional chord head) | beat / chord / vocal pitch | MIT |
| HeartMuLa / open-singer B1 pipeline | supervised pairs later | Apache (adaptor work) |
| Copyist open engine | fallback + feature baseline | MIT |
| open-transcriber | baselines, train, inference package | MIT |

MT3 was rejected as a base: there is no singing in its training and it works on 2-second windows. The head above instead sits on frozen Basic Pitch features.

Start with **inference of existing Apache/MIT models** on our truth takes (T0). Only train if T0 loses to the open engine on the table.

## Data we can train on

**Held out, always:** every song in `songs/` and every case in `scripts/transcribe/roundtrip.py`, in any key, tempo, meter or rendition, with their lyrics — including the two long songs added later. The dataset builder refuses them by title and by melodic fingerprint (`open_transcriber/data/heldout.py`, tested). None of them is ever a training input; they exist only to be scored against.

**Training data (exact labels):** lead sheets from Copyist's sampler, sung by SoulX-Singer with CC BY voices (VocalSet) over the sfizz band, mixed and separated with Demucs — every note's label is exact because the score is the source. Real CC BY singing (Annotated-VocalSet, Choral Singing Dataset, ESMUC, Cantoría) for fine-tuning and checks.

**Second round:**
- YuE2 renders of sampler lead sheets (owner approved, 2026-10-19). Each phrase is aligned and gated note by note, and the labels are melody only, since YuE2's band doesn't always play the written chords. They're kept as a separate tagged slice of the manifest.
- HeartMuLa songs with gated pseudo-labels.

**Judging:** YuE2 learned from SheetSage2's transcriptions, so YuE2 takes favour SheetSage2, and would favour a model trained on YuE2 too. Only real recordings decide whether we're better than SheetSage2.

**Dev and test kept apart:** the dev set, for tuning, is YuE2 and SoulX takes of 10–12 songs that aren't held out; the test set is the round-trip table, run once per candidate. No threshold or checkpoint is chosen on the test set.

**Never:** owner Broadway masters, private LoRAs, SheetSage outputs as pseudo-labels for a commercial model; the non-commercial datasets above, the Essen encodings, and SoulX's bundled example voice.

## Gate

Same as the open engine:

```
python scripts/transcribe/roundtrip.py
```

A candidate ships as `--engine neural` (name TBD) only when every row is ≥ open engine and Silent Night / Major-General chords move toward SheetSage's band. Owner listen checks come after a table win.

## Phases

### T0 — Feasibility (no training) — mostly done

- [x] Spotify Basic Pitch (Apache-2.0, CoreML) on the five truth takes via `scripts/transcribe/neural_baseline.py`.
- [x] Adaptive path + Copyist `clean_notes`: mean ~0.87; SN/Tyger win; Saints/AG/MG within 0.02.
- [x] Magenta MT3 evaluated and skipped for sung melody; Omnizart chord wrapper (native arm64 nnls-chroma since 2026-10-18).
- [x] `--engine neural` wired; default remains `open` until full-table + round-trip win.
- Verdict: **T1 deferred** — finish the three small gaps first.

### T1 — Supervised lead-sheet head

- Landed 2026-10-19: the held-out guard (`open_transcriber/data/heldout.py`) and a seeded, data-only score sampler (`open_transcriber/data/scores.py`) with a public-domain lyric pool.
- Dataset builder: sampler lead sheets sung by SoulX over the band → exact melody events and chord symbols on the beat grid (labels come from the score, not from audio).
- Train the lead-sheet head (see the licence stack) on that data. Never on the YuE2 truth takes, which are held out. YuE2 renders of sampler scores come in the second data round (owner approved, 2026-10-19).
- Wire `copyist transcribe --engine neural` behind the same tidy path (`clean_notes`, lyric `note_target`, `fold_grid_rearticulations`).
- Done when the trained model is at or above open on every row of the round-trip table (all seven songs) for notes, with no row worse on chords. Silent Night's chords are their own item: melody training doesn't move them.

### T2 — Product slot

- Default stays `open` until neural wins the full table including a sixth PD song.
- Desktop **Install extras** pack for neural weights (Apache/MIT only; size and download time documented).
- SheetSage remains optional NC for researchers who accept the licence.

## Relation to other work

- **TASKS §7:** open engine table work and T0 can proceed in parallel; T1 only if T0 loses.
- **Open singer B1** (`docs/open-singer.md`): the transcription script there is a data factory for score-conditioned singing; its lead sheets can feed T1 once the quality gate exists.
- **Mac app ship (§3d):** not blocked; neural weights are an extras download later.

## Commands

```
git submodule update --init open-transcriber
bash open-transcriber/scripts/setup_baseline.sh   # CoreML Basic Pitch on macOS/py3.12
python scripts/transcribe/neural_baseline.py
python scripts/transcribe/roundtrip.py            # open-engine yardstick (unchanged)
```

### T0 note F1 (Basic Pitch vs open engine)

| Case | Basic Pitch | Open engine |
|---|---|---|
| saints | 0.46 | 0.85 |
| silent-night | 0.58 | 0.80 |
| amazing-grace | 0.37 | 0.88 |
| tyger | 0.64 | 0.78 |
| major-general | 0.82 | 0.84 |
