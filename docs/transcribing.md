# Transcribing recordings (`copyist transcribe`): spec

**Goal:** someone who has a recording of their song (a Suno or Mozart AI song, a demo, a YuE2 take) and can't read or write music gets a correct lead sheet from it: the melody as sung, the chords, the lyrics under the notes, the key, meter and tempo. From there every Copyist output follows: the score, the parts, the band, new takes. This is milestone MT (SPEC section 12). The owner asked for it on 18 October 2026; her musical is built from songs that exist only as recordings.

Status, 18 October 2026: the first version is built and tested (`copyist transcribe`, `copyist/transcribe.py`, the page's "Transcribe a recording"). Next: more sung test recordings, then the owner tries it on her own songs. TASKS.md section 7 lists the steps.

**Rights:** only recordings the person owns or has rights to (SPEC 12.5). Their recordings stay in their own `out/` folder and are never committed.

## Setting up

`pip install -e ".[transcribe]"` (librosa, soundfile, faster-whisper), and Demucs for separating the voice: `scripts/setup-demucs.sh`, as for `copyist follow --separate`. The desktop app will bundle both.

## What the person does

1. **Transcribe a recording** on the page, or `copyist transcribe RECORDING --title "…" [--lyrics lyrics.txt]`.
2. Listen: the page plays the original and Copyist's band playing the transcription, one after the other. It lists the doubtful spots in words ("bar 12, beat 3: between E and F; wrote E").
3. **Keep it**: the song file goes into `songs/` and its score is written. Fix anything still wrong by choosing between alternatives by ear (later: per-doubt A/B, SPEC 12.2a step 7).

Giving the lyrics helps a lot: they fix how many syllables, and so how many notes, the singer sings. Without them, Whisper's hearing of the words is used.

## Engines: who writes the first draft

| Engine | What | Licence | Measured (below) |
|---|---|---|---|
| `open` (default) | Copyist's own (`copyist/transcribe.py`): beats from the band and the voice, chords from chroma with a Viterbi path, the melody from pYIN on the separated vocal, every doubt settled by the music around it | MIT, with librosa (ISC) and Demucs (MIT) | Band renders: 0.89–0.98 note F1. A YuE2 take: 0.87 |
| `sheetsage` (optional) | SheetSage2 through yue2.cpp's `yue-transcribe` (melody, chords, key, meter from the full mix) | Weights CC BY-NC 4.0, with no added permission: **non-commercial use only** | Band render 0.98; the YuE2 take 0.94 notes, 0.97 chords |

SheetSage2 is more accurate today, especially on sung vocals, but its licence forbids commercial use, and unlike YuE2's it has no permission for individual creators to sell their songs. So the open engine is the default. SheetSage2 is offered as an optional download with its licence shown, and the page says plainly what that licence means. SheetSage2 writes melodies an octave above the singing, YuE2's convention; Copyist moves them down.

The open engine's job is to close that gap. The evaluation below is how progress is measured.

## The open engine, step by step

1. **Separate** (`copyist/stems.py`, Demucs): the vocal, and everything else (the accompaniment).
2. **Beats:** librosa's beat tracker on the band's onsets plus the singer's, with a steady tempo. A tight tracker doesn't wander onto the off-beats in a sparse intro (measured on the YuE2 take: a loose one sat a third of a beat late).
3. **The melody:** pYIN on the vocal; notes are voiced runs, split where the pitch moves to a new note and holds there, or where a new syllable starts on the same pitch (an onset the loudness climbs out of). Then tidied (`clean_notes`):
   - quiet notes dropped (other instruments bleeding into the vocal stem, mostly in the intro);
   - notes far outside the body of the line dropped (octave errors);
   - fragments too short to be sung folded into the neighbour nearest in pitch;
   - slides folded: a short note a semitone or so from a much longer neighbour whose pitch wanders (a steady passing note stays);
   - same-pitch neighbours joined, unless a new syllable starts the second;
   - with the lyrics known, the likeliest leftovers folded until the count is within reach of the syllables.

   A note's start moves back to the consonant's onset, just before the pitch settles.
4. **Meter, in two steps, on a grid of eighths** (each tracked beat split in two):
   - the beat: every two eighths (3/4, 4/4) or every three (6/8, 12/8), whichever puts the accents, bass notes and sung onsets on beats and not between them;
   - the bar: which beats start bars, by harmonic change, long sung notes, the bass and accents. 4/4 is favoured a little over 3/4, and 6/8 over 12/8.
5. **Key:** Krumhansl–Kessler profiles on the accompaniment's chroma.
6. **Chords:** chroma above the bass, per beat, against templates (triads first; sevenths, then maj7, sus4 and dim need clearer evidence), the key favouring its own chords, and the bass naming the root on downbeats (between them it alternates or walks). A Viterbi path changes chord only when it pays: cheaply on a downbeat, dearly mid-bar. A slash bass is written only where a chord starts.
7. **Rhythm:** each beat's onsets take the plainest pattern that fits them (two eighths, a dotted eighth and a sixteenth, three eighths in 6/8, ...), weighing timing error against reading cost, after the small shift that best fits the singer to the grid.
8. **Pitch by context (SPEC 12.2a):** each note keeps the audio's top candidates. A Viterbi path picks the sequence that's likely both as audio and as music: in the key, a chord tone on strong beats, near the note before. Notes still in doubt are listed.
9. **Syllable starts:** for each note, how surely a syllable starts on it: after a silence almost surely, after a dip in loudness (a consonant) likely, when the voice only glides to a new pitch probably not (a melisma). The lyric fit (`copyist/fit.py`) weighs these against stress and beat.
10. **Write the draft** as planner-dialect ABC, so melody writing's path (`write.song_from_plan`) makes the song file: the octave as sung, a voice preset that fits, the lyrics fitted under the notes, validation.

## Measured

The truth set is Copyist's own public-domain songs, where every note is known: the band rendering of each (melody on the clarinet stem), and YuE2's take of Amazing Grace separated with Demucs. `scripts/transcribe/evaluate.py SONG.yaml DRAFT.abc` aligns a transcription to the true score (time shift and tempo ratio) and reports note F1 (onset within a quarter beat, same pitch, `--octave-free` for takes in another octave) and chord accuracy (root and major/minor, by time).

| Recording | Open: notes, chords | SheetSage2: notes, chords |
|---|---|---|
| Amazing Grace, band (3/4) | 0.97, 0.97 | 0.98, 0.98 |
| When the Saints, band (4/4) | 0.98, 0.89 | not run yet |
| Silent Night, band (6/8) | 0.89, 0.89 | not run yet |
| Amazing Grace, YuE2 take, Demucs vocal | 0.87, 0.75 | 0.94, 0.97 |

Meter, key and tempo are right on all four (3/4, 4/4, 6/8, 3/4).

On a 2-core cloud CPU the open engine takes 5–16 s a song; SheetSage2 takes 8–15 minutes there (on a Mac with Metal it should be seconds; not measured).

Known weaknesses, in order of what to fix next:
- chords on real mixes, where the band's own voicings and passing chords blur the chroma (0.75 on the take);
- sung ornaments and re-articulations (YuE2 sings "G, G" for one written G), which a transcription rightly hears but a lead sheet shouldn't show;
- sixteenth-note passing notes in slow music (Silent Night's "A" in "G A G");
- where exactly the singer starts each syllable: the lyric fit uses syllable-start hints from the audio, but no word timings yet.

## Output

`out/<slug>/transcribe/`:
- `source.<ext>`: a copy of the recording;
- `stems/`: the vocal and the accompaniment;
- `draft.abc`: the engine's score;
- `<slug>.yaml`: the song file;
- `report.md`: the engine's notes, the doubts, the validation;
- `preview.wav`: the transcription played by the band, to compare with the original;
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
