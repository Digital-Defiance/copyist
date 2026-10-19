# Open lead-sheet transcriber (a better SheetSage we can ship)

**Goal:** a commercially usable lead-sheet AMT that beats Copyist's open engine on `scripts/transcribe/roundtrip.py`, and approaches SheetSage2 on sung YuE2 takes — without CC BY-NC weights.

**Code:** first-party repo [Digital-Defiance/open-transcriber](https://github.com/Digital-Defiance/open-transcriber) (MIT), vendored here as the git submodule `open-transcriber/`.

```bash
git submodule update --init open-transcriber
```

Status, 19 October 2026: submodule in place; **adaptive BP + `clean_notes`** (see `open-transcriber/docs/t0-results.md`) mean note F1 ~0.87 vs open 0.83; `copyist transcribe --engine neural` wired (default still `open`). Magenta MT3 skipped for singing; Omnizart chords blocked on Apple Silicon Vamp. SheetSage2 remains optional and non-commercial.

## Why

SheetSage2 is the accuracy ceiling we measured (≈0.94–0.98 note F1 on takes), but its weights are CC BY-NC 4.0 with no creator-sell permission. Shipping it as the product default is a licence dead end. Closing the gap with more chroma heuristics helps (Silent Night chords 0.40→0.69 with tonal priors; Saints notes 0.85), but a trained model is the honest long-term path for Broadway-dense singing and band voicings that disagree with lead-sheet labels.

## What we will not do

- Fine-tune or redistribute SheetSage / MuScriptor weights (NC).
- Train on Lights On audio, Suno outputs, or any recording we can't prove rights for.
- Replace the open engine until the same round-trip table says the new engine wins and no row collapses.

## Licence stack (must stay MIT/Apache)

| Piece | Role | Licence |
|---|---|---|
| Demucs | vocal / band stems | MIT |
| MT3 (or a small head on a similar encoder) | multi-instrument AMT → MIDI / note events | Apache-2.0 |
| Omnizart (optional chord head) | beat / chord / vocal pitch | MIT |
| HeartMuLa / open-singer B1 pipeline | supervised pairs later | Apache (adaptor work) |
| Copyist open engine | fallback + feature baseline | MIT |
| open-transcriber | baselines, train, inference package | MIT |

Start with **inference of existing Apache/MIT models** on our truth takes (T0). Only train if T0 loses to the open engine on the table.

## Data we can train on

Paired (audio → known lead sheet), all public-domain or original to Copyist:

1. **Band renders** of every `songs/*.yaml` (sfizz / SoundFont) — exact notes and chords.
2. **YuE2 truth takes** already in the round-trip loop (Saints, Silent Night, Amazing Grace, Tyger, Major-General, …) — melody via `follow`; chords vs written (accept that YuE2 harmony may disagree; optionally train a "played harmony" head separately).
3. **Open-singer B1 corpus** (`scripts/open-singer/transcribe.py` gate): songs generated under Apache licences with lead sheets that pass `copyist follow` ≥ 90%.
4. **Synthetic stress:** patter (Major-General-like), waltz vs 6/8, melisma holds (`_`).

Never: owner Broadway masters, private LoRAs, SheetSage outputs as pseudo-labels for a commercial model.

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
- [x] Magenta MT3 evaluated and skipped for sung melody; Omnizart chord wrapper (arm64 chroma blocked).
- [x] `--engine neural` wired; default remains `open` until full-table + round-trip win.
- Verdict: **T1 deferred** — finish the three small gaps first.

### T1 — Supervised lead-sheet head

- Dataset builder in open-transcriber: song YAML + render/take → aligned melody events + chord symbols on the beat grid (reuse Copyist beat tracker for alignment labels).
- Train a small melody+chord model (start from MT3 checkpoint or a custom encoder) on PD renders; fine-tune lightly on YuE2 takes with melody-only loss if chords are noisy.
- Wire `copyist transcribe --engine neural` behind the same tidy path (`clean_notes`, lyric `note_target`, `fold_grid_rearticulations`).
- Done when round-trip note F1 ≥ open on all five and Silent Night chords ≥ 0.75.

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
