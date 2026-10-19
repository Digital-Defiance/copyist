# Transcribing recordings (`copyist transcribe`): spec

**Goal:** someone who has a recording of their song (a Suno or Mozart AI song, a demo, a YuE2 take) and can't read or write music gets a correct lead sheet from it: the melody as sung, the chords, the lyrics under the notes, the key, meter and tempo. From there every Copyist output follows: the score, the parts, the band, new takes. This is milestone MT (SPEC section 12). The owner asked for it on 18 October 2026; her musical is built from songs that exist only as recordings.

Status, 18 October 2026: the first version is built and tested (`copyist transcribe`, `copyist/transcribe.py`, the page's "Transcribe a recording"). YuE2 truth takes measured; soft 6/8 double-tempo corrected; beat-chroma smoothing and a tonal chord prior lift chords (Silent Night 0.40→0.69 on the table). Ornament / re-articulation folding and lyric-guided splits lift notes. **Improve by the round-trip table** (`scripts/transcribe/roundtrip.py`): produce (or reuse a truth take) → open engine → note/chord F1 vs the written score. Owner songs without a written score can be scored with `evaluate.py --sung VOCAL.wav SONG.yaml`. Large PD stress case: `songs/major-general.yaml` (~128 notes). MusicXML lead sheets can become song files with `copyist import`. A commercially usable neural path (not SheetSage weights) is planned in [docs/open-transcriber.md](open-transcriber.md). TASKS.md section 7 lists the steps.

**Rights:** only recordings the person owns or has rights to (SPEC 12.5). Their recordings stay in their own `out/` folder and are never committed.

## Setting up

`pip install -e ".[transcribe]"` (librosa, soundfile, faster-whisper), and Demucs for separating the voice: `scripts/setup-demucs.sh`, as for `copyist follow --separate`. The desktop app will bundle both.

## What the person does

1. **Transcribe a recording** on the page, or `copyist transcribe RECORDING --title "…" [--lyrics lyrics.txt]`.
2. Listen: the page plays the original and Copyist's band playing the transcription, one after the other. It lists the doubtful spots in words ("bar 12, beat 3: between E and F; wrote E").
3. **Keep it**: the song file goes into `songs/` and its score is written. Fix anything still wrong by choosing between alternatives by ear (later: per-doubt A/B, SPEC 12.2a step 7).

Giving the lyrics helps a lot: they fix how many syllables, and so how many notes, the singer sings. Without them, Whisper's hearing of the words is used. If the lyrics are a full libretto (repeats, spoken word) and the transcription has fewer notes, Copyist fits the opening sung lines under the melody, leaves spoken sections off, and says so in the report — the job does not fail.

## Engines: who writes the first draft

| Engine | What | Licence | Measured (below) |
|---|---|---|---|
| `open` (default) | Copyist's own (`copyist/transcribe.py`): beats from the band and the voice, chords from chroma with a Viterbi path, the melody from pYIN on the separated vocal, every doubt settled by the music around it | MIT, with librosa (ISC) and Demucs (MIT) | Band renders: 0.89–0.98 note F1. A YuE2 take: 0.87 |
| `sheetsage` (optional) | SheetSage2 through yue2.cpp's `yue-transcribe` (melody, chords, key, meter from the full mix) | Weights CC BY-NC 4.0, with no added permission: **non-commercial use only** | Band render 0.98. The five YuE2 takes: 0.94–1.00 notes (mean 0.97), 0.74–0.97 chords (mean 0.88) |

SheetSage2 is more accurate today, especially on sung vocals, but its licence forbids commercial use, and unlike YuE2's it has no permission for individual creators to sell their songs. So the open engine is the default. SheetSage2 is an optional download (`copyist models download sheetsage --accept-licence`, or **Install extras** / the transcribe form): SheetSage2-Q8_0.gguf plus MERT beside it (~1 GB), licence shown first. The desktop app bundles `yue-transcribe`; from a checkout run `scripts/setup-yue.sh`. SheetSage2 writes melodies an octave above the singing, YuE2's convention; Copyist moves them down. When it puts the tune on the Ins voice (Vocal left as rests), Copyist takes that line; short mid-song 1/4 or 2/4 bars are joined into the song's meter. When SheetSage2 changes key (a `K:` line in both voices, or `[K:…]` inside a bar), Copyist keeps every bar and reads each note in the key in force; the song keeps the key it starts in, the notes after the change carry their accidentals, and the report says in which bar the key changes.

The open engine's job is to close that gap. The evaluation below is how progress is measured.

## The open engine, step by step

1. **Separate** (`copyist/stems.py`, Demucs): the vocal, and everything else (the accompaniment).
2. **Beats:** librosa's beat tracker on the band's onsets plus the singer's, with a steady tempo. A tight tracker doesn't wander onto the off-beats in a sparse intro (measured on the YuE2 take: a loose one sat a third of a beat late). When the strongest autocorrelation peak is half the tracked tempo (a soft 6/8 take locking onto half of each dotted-quarter), the eighth grid is rebuilt from every other beat trisected, and meter is chosen as 6/8 only.
3. **The melody:** pYIN on the vocal; notes are voiced runs, split where the pitch moves to a new note and holds there, or where a new syllable starts on the same pitch (an onset the loudness climbs out of). Then tidied (`clean_notes`):
   - quiet notes dropped (other instruments bleeding into the vocal stem, mostly in the intro);
   - notes far outside the body of the line dropped (octave errors);
   - fragments too short to be sung folded into the neighbour nearest in pitch;
   - slides folded: a short note a semitone or so from a much longer neighbour whose pitch wanders (a steady passing note stays);
   - same-pitch neighbours joined, unless a new syllable starts the second;
   - re-articulations / ornaments folded: a short same-pitch echo (even with an onset, and across a brief rest) into the longer note — singers and YuE2 often hit "G, G" for one written G; equal-weight repeated syllables stay;
   - stray pitches far from the median of the line dropped (bass bleed into the vocal stem);
   - with the lyrics known, the likeliest leftovers folded until notes are within about 8% of the syllable count (same pitch first); then, if still ≥ 2 over, brief approach-tone scoops fold down to the lyric count;
   - after rhythm snap, short same-pitch echoes on the grid are merged again.

   A note's start moves back to the consonant's onset (at most 0.08 s), just before the pitch settles.
4. **Meter, in two steps, on a grid of eighths** (each tracked beat split in two):
   - the beat: every two eighths (3/4, 4/4) or every three (6/8, 12/8), whichever puts the accents, bass notes and sung onsets on beats and not between them;
   - the bar: which beats start bars, by harmonic change, long sung notes, the bass and accents. 4/4 is favoured a little over 3/4, and 6/8 over 12/8.
5. **Key:** Krumhansl–Kessler profiles on the accompaniment's chroma.
6. **Chords:** chroma above the bass, per beat, smoothed with nearby beats that still match (cosine ≥ 0.55) so passing tones don't rename every chord but real changes stay sharp; the bass chroma is not smoothed. Matched to templates (triads first; sevenths, then maj7, sus4 and dim need clearer evidence), the key favouring diatonic chords plus I/IV/V(7)/vi in major, and the bass naming the root on downbeats (between them it alternates or walks). A Viterbi path changes chord only when it pays: cheaply on a downbeat, dearly mid-bar (dearer still in 6/8). A slash bass is written only where a chord starts.
7. **Rhythm:** each beat's onsets take the plainest pattern that fits them (two eighths, a dotted eighth and a sixteenth, three eighths in 6/8, ...), weighing timing error against reading cost, after the small shift that best fits the singer to the grid.
8. **Pitch by context (SPEC 12.2a):** each note keeps the audio's top candidates. A Viterbi path picks the sequence that's likely both as audio and as music: in the key, a chord tone on strong beats, near the note before. Notes still in doubt are listed.
9. **Syllable starts:** for each note, how surely a syllable starts on it: after a silence almost surely, after a dip in loudness (a consonant) likely, when the voice only glides to a new pitch probably not (a melisma). The lyric fit (`copyist/fit.py`) weighs these against stress and beat.
10. **Write the draft** as planner-dialect ABC, so melody writing's path (`write.song_from_plan`) makes the song file: the octave as sung, a voice preset that fits, the lyrics fitted under the notes, validation.

## Measured

The truth set is Copyist's own public-domain songs, where every note is known: the band rendering of each (melody on the clarinet stem), and YuE2 takes separated with Demucs (`out/<slug>/takes/truth/` for Saints and Silent Night; Amazing Grace under `out/amazing-grace/production/`). `scripts/transcribe/evaluate.py SONG.yaml DRAFT.abc` aligns a transcription to the true score (time shift and tempo ratio) and reports note F1 (onset within a quarter beat, same pitch, `--octave-free` for takes in another octave) and chord accuracy (root and major/minor, by time).

| Recording | Open: notes, chords | SheetSage2: notes, chords |
|---|---|---|
| Amazing Grace, band (3/4) | 0.97, 0.97 | 0.98, 0.98 |
| When the Saints, band (4/4) | 0.98, 0.89 | not run yet |
| Silent Night, band (6/8) | 0.89, 0.89 | not run yet |
| Amazing Grace, YuE2 take, Demucs vocal | 0.88, 0.78 | 0.94, 0.97 |
| When the Saints, YuE2 take (`--take truth`) | 0.85, 0.89 | 0.97, 0.87 |
| Silent Night, YuE2 take (`--take truth`) | 0.80, 0.69 | 0.96, 0.91§ |
| The Tyger, YuE2 take (`--take truth`) | 0.78, 0.81† | 1.00, 0.91 |
| Major-General, YuE2 take (`--take truth`) | 0.84, 0.79‡ | 0.98, 0.74 |

† Written 3/4 @ 80; open engine reads 4/4 ~108 (same bar length: waltz ×4/3 pulse). Was false 6/8 ~54 before the waltz guard. SheetSage2 reads 3/4 @ 81.
‡ Note count recovered by lyric-guided splits (was 0.44 / 43 vs 128). Key was C#m from Demucs accompaniment alone; `choose_key` (mix/melody) → Eb; tonal chord prior → chords 0.79.
§ SheetSage2 writes Silent Night as 3/4 at 1/4=82: the same bar length, but three quarters instead of two dotted quarters. The open engine reads its 6/8 right.

SheetSage2's take rows were measured on 2026-10-19 as a yardstick only (never labels, never tuning; local report in `.agents/tasks/sheetsage-yardstick-2026-10-19/`). Same-session means on the five takes, notes then chords: open 0.83 / 0.82, neural 0.87 / 0.79, SheetSage2 0.97 / 0.88.

These numbers compare engines with each other and nothing more:
- The metric is lenient. SheetSage2's own card scores pitch class with onsets within 50 ms.
- The meter isn't scored.
- SheetSage2 hears only the mix, while the open and neural engines also get the stems and the lyric count.
- The takes are YuE2 renders, and SheetSage2 comes from the same lab.

Meter, key and tempo: right on the band renders and on Amazing Grace's take; Saints' take is 4/4 C ~112; Silent Night's take was heard as 4/4 ~108 until the double-tempo correction, and is now 6/8 ~55 (true is `3/8=56`).

On the M4 Max: Demucs + the open engine is under 10 s a song after the first model load. SheetSage2 takes 4–6 s a take on Metal after loading its ~1 GB of models: a fixed 2 s to encode its 300 s window, then about 5 ms a token.

### Round-trip (how to improve)

```
python scripts/transcribe/roundtrip.py                  # Saints + Silent Night (+ AG when stems exist)
python scripts/transcribe/roundtrip.py --only saints
python scripts/transcribe/roundtrip.py --write out/roundtrip.md
```

Each row is: known public-domain score → YuE2 truth take → open engine → note F1 / chord accuracy vs the score (`evaluate.py`, `--octave-free`). Change one cleaning/rhythm rule, re-run, keep the change only if the table improves (and no row collapses). Owner Broadway songs are a listen check after the table moves — they have no written truth.

Measured diagnosis (open engine, 2026-10-18):
- **Saints 0.85 / 0.89:** scoop fold cleared D-before-E extras (35→33). Looser onset match still ~0.88 ceiling.
- **Tyger 0.78 / 0.81:** still reads 4/4 ~108 not written 3/4 @ 80 (same bar length).
- **Silent Night 0.80 / 0.69** (42 vs 46): chords 0.40→0.69; notes 0.77→0.80 with onset-pull cap. Remaining misses aren't in same-pitch holds (padding to 46 hurt F1).
- **Amazing Grace 0.88 / 0.91:** melisma-aware note target + tonal prior on chords.
- **Major-General 0.84 / 0.79** (128 vs 128): splits + `choose_key` (Eb) + tonal prior.

Known weaknesses, in order of what to fix next:
- Silent Night chords (0.69) and remaining note recall (pitch-track ceiling);
- Open neural lead-sheet T0 (docs/open-transcriber.md) — heuristics near a local wall;
- Saints residual timing (~0.88 at looser onset tol);
- Tyger meter (4/4 vs written 3/4);
- SheetSage drafts don't go through `clean_notes` yet;
- syllable/word timings (Broadway feel).

For a commercially shippable neural engine that can replace SheetSage, see [docs/open-transcriber.md](open-transcriber.md). T0 (Basic Pitch) numbers are there and in `open-transcriber/docs/t0-results.md` — raw BP loses to this open engine on lyrical takes.

Owner songs (no written score): `evaluate.py --sung VOCAL.wav SONG.yaml` and/or `copyist follow`.

## Output

`out/<slug>/transcribe/`:
- `source.<ext>`: a copy of the recording;
- `stems/`: the vocal and the accompaniment;
- `draft.abc`: the engine's score;
- `<slug>.yaml`: the song file;
- `report.md`: the engine's notes, the doubts, the validation;
- `preview.wav`: a piano-led check mix (ballad / waltz / lullaby by meter) so you can hear the tune against the original; not a finished production — use `copyist produce` for a YuE2 take once you keep the song;
- `transcription.json`: what the page reads.

The song file records where it came from: `written_with: {transcriber: copyist-open, recording: name}`.

`copyist transcribe --title T --keep` copies the song file into `songs/` (refusing to overwrite a different song without `--replace`; `--build` writes its score).

## The page

"Transcribe a recording" in the drawer: choose the audio file (it's copied into the library), the title, and optionally the lyrics, and the engine. The result shows:
- both players (original, transcription);
- key, meter, tempo, sections;
- the doubts;
- the checks;
- "Keep this".

## Tests

- Synthetic recordings made in the test (sine-tone melody, chord pads), so the expected notes, chords, key and meter are exact: the engine recovers them.
- `clean_notes`: quiet notes, outliers, fragments, joins, the lyric count.
- Inline meter changes in a draft (a pickup bar), the octave convention per engine.
- The command end to end with stems given (no Demucs in the test), and with a fake `yue-transcribe`.

## Later

- Per-doubt A/B by ear, writing the choice back into the song file (SPEC 12.2a step 7).
- Repeats vote: the same section sung again settles doubtful notes (SPEC 12.2a step 3).
- Analysis by synthesis: render, compare with the recording bar by bar, refit (SPEC 12.2 step 4).
- Bass line, drum groove and band parts (SPEC 12.1).
- Lyrics aligned by Whisper's word timings, to split notes at syllables more surely.
