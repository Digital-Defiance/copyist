# Melody writing (`copyist write`): spec

**Goal:** someone who can't read or write music gives Copyist lyrics and a few words of direction, and gets back several finished songs to choose between by ear. Each one has a real melody and chords, the lyrics placed correctly under the notes, and every Copyist output: lead sheet, score, parts, band preview, YuE2 take. This is milestone MW in ROADMAP.md. The owner's stated goal for Copyist is "really good melodies and solid themes", so this is the heart of the product.

Status, 18 October 2026: built and tested (`copyist write`, `copyist/write.py`, the page's "Write a song"). On the owner's M4 Max with Metal: four folk candidates for a Dickinson verse in about 31 s (~8 s each); four waltz candidates for a Blake verse in about 28 s. Listen to the previews in `out/<slug>/write/candidate-*/preview.wav`.

## The idea in one paragraph

YuE2 already composes. Before it renders audio, its first stage writes the song as an ABC score: the melody, the chords and an instrumental line. yue2.cpp exposes that stage alone as `yue-plan`: text in, text out, no audio. Copyist asks it for several scores for the same lyrics and style, then turns each one into a correct Copyist song file:
- the melody in the singer's octave;
- the lyrics placed under the notes by an alignment that respects stress and phrasing;
- the validators run on the result.

Each candidate is played on the exact band preview so the person picks by ear. A YuE2 take is optional (`--takes`) when you want to hear a production, not the default audition (SPEC §15). The picked song file then goes through everything Copyist already does.

## What `yue-plan` produces (measured)

- **Command:** `yue-plan --model YuE2-3B-Q6_K.gguf --request req.json --out score.abc [--lm-seed N] [--device MTL0]`. The request is the same JSON `yue-synth` takes, with `"cot": "full"` and `"abc": ""`. Copyist's existing `paths.find_program` finds the binary in `.cache/yue2.cpp/build/` on the owner's Mac.
- **Speed:** on a 2-core Linux CPU (the cloud container), a 12-line lyric took 2 min 42 s (640 score tokens, 203 ms a token). On an M4 Max with Metal (`--device MTL0`), about 7–8 s a candidate (four Dickinson or Blake verses in ~30 s total, including band previews).
- **Determinism:** the same `--lm-seed` gives the same score. Different seeds give different songs.
- **The style line steers it.** "gentle folk ballad ... 84 BPM" gave 3/4 in D at 86 BPM. "slow pop ballad, 4/4, piano ... 72 BPM" gave 4/4 in B-flat at 72 BPM.
- **It chooses its own form** from the lyrics. Three `[Verse]` stanzas came back as an intro, a verse covering stanzas 1 and 2, a "chorus" covering stanza 3, and an outro. Copyist keeps the section names YuE2 writes.

The ABC dialect, as written by yue-plan:

```
X:1
T:
M:3/4
L:1/32
Q:1/4=86
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:D
% intro
V: Vocal
z16z4"D"z4|"D"z24|"G/D"z24|"D"z24|
V: Ins
Z|D4A2d4A2e2f4d6|A2B4d6A6d6|z6d6e2f4d6|
V: Vocal
"G/D"z16z4d4|
V: Ins
A2B4d6A8z4|
% verse
V: Vocal
"D"d8d4a8f4|"G"e2d6z12d4|"Bm"d8f4f8e4|"A"e8z12d4|
V: Ins
Z4|
...
```

How to read it:
- `% name` starts a section: intro, verse, chorus, bridge, outro, and so on.
- `V: Vocal` and `V: Ins` alternate, one block per phrase.
- Chord symbols are quoted and attached to notes or rests. They can be slash chords (`G/D`) and suspensions (`Dsus4`).
- Durations are integers in units of `L:` (1/32).
- `Z` and `Zn` are whole-bar rests.
- `-` ties a note to the next.

**YuE2 sings one octave below the ABC it plans**, the same as with scores Copyist gives it (`yue.SUNG_OCTAVE_BELOW`). So the melody comes down an octave for the song file.

**Lyrics and notes:** in the first test, one Vocal block held two lyric lines, and the notes matched the syllables exactly (13 and 13) for the first couplet. The second couplet had 13 notes for 14 syllables. The fit has to absorb differences like that (see Fitting the lyrics).

## The command

```
copyist write LYRICS.txt --title "Hope" [--style folk | --words "free style words"] [--voice alto]
              [--candidates 4] [--seed 1] [--takes] [--out out] [--device MTL0]
```

**Inputs:**
- **The lyrics file:** plain text, sections tagged `[Verse]`, `[Chorus]`, `[Pre-Chorus]`, `[Bridge]`, `[Intro]` or `[Outro]` (case-insensitive, numbers allowed: `[Verse 2]`), one sung line per line. Untagged text counts as a verse. Reuse `lora.yue_lyrics` to turn this into YuE2's tags.
- **`--style`:** a Copyist style id (`copyist styles`). Its `production` words go into the planner's style line. `--words` adds or replaces words.
- **`--voice`:** a range preset:

  | Preset | Range | Clef |
  |---|---|---|
  | soprano | C4–A5 | treble |
  | alto (default) | G3–E5 | treble |
  | tenor | C3–A4 | treble-8vb |
  | baritone | A2–F4 | bass |

  The style line gets matching words, such as "warm female alto vocal".

**Output:** `out/<slug>/write/` with, for each candidate `k`:
- `candidate-k/plan.abc`: what yue-plan wrote;
- `candidate-k/request.json`: the planner request;
- `candidate-k/<slug>.yaml`: the Copyist song file;
- `candidate-k/report.md`: validation, fit and scores;
- `candidate-k/preview.wav`: the band preview in the chosen style;
- with `--takes`, `candidate-k/take/production.wav`.

Plus `candidates.json`, the index the page reads, ranked. Candidate folders are named by seed (`candidate-1`, `candidate-2`, ...), so "Write more" continues with the next seeds. A plan is reused when its request hasn't changed, so running again only re-reads it. When the lyrics change, the list starts afresh.

`copyist write --title T --keep SEED` (or the page's "Keep this one") copies the candidate's song file to `songs/<slug>.yaml`. It refuses to overwrite a different song unless given `--replace`; `--build` then writes the score, as the page does. From there, everything else applies.

## Rewriting one section

```
copyist rewrite SONG.yaml --section verse --how again|higher|simpler
         [--candidates 4] [--lyrics LYRICS.txt] [--no-plan] [--device MTL0]
copyist rewrite --title T --how higher --keep SEED [--replace] [--build]
```

YuE2's planner writes whole songs, so Copyist rewrites a section in two ways:

- **`higher`:** raises that section by a few semitones (melody and chords together; the key moves when the section is the whole song), clamps to the voice range, and writes several shifts (`+2`…`+5`) as candidates. No planner call.
- **`again` / `simpler`:** reuse (or plan) other write candidates with the same key, meter and section length, then swap that section into the base song. `simpler` prefers the donor whose section has the smallest leaps; when it plans more, it also asks for a stepwise melody. Pass `--no-plan` to use only donors already in `out/<slug>/write/`.

Output: `out/<slug>/rewrite/<how>/candidate-*/` with song file, report and band preview, plus `candidates.json`. Keep one with `--keep` (same rules as `write --keep`). Plain lyrics come from `out/<slug>/write/lyrics.txt` when present, or `--lyrics`.

## Turning a plan into a song file

1. **Parse the dialect** (`copyist/abcplan.py`): the header (M, L, Q, K), then the sections and voices. Keep only the `Vocal` bars, each tagged with its section. Read tokens with a small tokenizer of Copyist's own:
   - chord `"..."`;
   - note `[_^=]*[A-Ga-g][,']*` plus an optional length (`n`, `n/m`, `/`) and an optional tie `-`;
   - rest `z` plus a length;
   - whole-bar rest `Z` plus a count;
   - the bar line `|`.

   Anything else, such as a tuplet `(3`, broken rhythm `>` or decorations, rejects the candidate with a clear note in the report. Don't guess.
2. **Trim to the singing:**
   - Drop bars before the first bar with a vocal note, and after the last.
   - Expand `Zn` into n bars of `z<full bar>`.
   - Keep the first sung bar whole, leading rests included, rather than turning it into a pickup: whole bars keep `yue._placed` and the bar check simple.
   - Keep chords on rests.
3. **Octave:**
   - Lower every note by one octave (YuE2's convention).
   - Then shift by whole octaves to put the most notes inside the voice preset's range, preferring the shift whose median is closest to the middle of the range.
   - If more than 10% of notes are still outside, transpose by the fewest semitones that fit, change `K:` to match, and say so in the report.
   - Write octaves in ABC as uppercase = octave 4, lowercase = 5, `'` adds one, `,` takes one away.
   - **Accidentals:** YuE2's plans carry an accidental through the bar for that letter in every octave; music21, which reads Copyist's song files, carries none (measured: `^F f F` reads F#4 F5 F4). So the song file writes every accidental explicitly, and repeats it after another accidental on the same letter in the bar (`abcplan.respell`).
4. **Meter:** the planner sometimes writes 2/4 even when asked for 4/4. No style plays 2/4, and it doubles the bars to read, so two bars become one 4/4 bar, paired so chord changes and section starts fall on the downbeats (`abcplan.pair_bars`).
5. **Units:** pick the largest unit (1/4, 1/8 or 1/16) that makes every length a whole number, and rescale. Readable files matter, because people open them.
6. **Tempo, key and meter** come from `Q:`, `K:` and `M:`. A `Q:1/4=n` becomes `tempo: n`; anything else stays a string (as in songs/silent-night.yaml).
7. **Sections:** record `sections: [{name: verse, bar: 1}, {name: chorus, bar: 17}]` in the song file.
   - This is a new optional field: add it to SPEC section 4 and to `song.py`.
   - `yue.lyrics_text` uses it so a later take sings `[chorus]` where the planner wrote a chorus, and the lead sheet and score print rehearsal marks ("Verse", "Chorus").
   - A one-bar section followed by another is that section's pickup (the planner often leaves it in the intro), so it joins the next one.
8. **Provenance:** add `written_with: {planner: yue-plan, model: YuE2-3B-Q6_K, seed: N, style: "..."}` (optional, ignored by the loader). Leave `credits:` to the person: `--words-by` and `--music-by` fill them, otherwise they're left empty.

## Fitting the lyrics (`copyist/fit.py`)

**Syllables** (`copyist/syllables.py`):
- Split each word using the CMU dictionary's syllable count (the `pronouncing` package, already a dependency) and English spelling rules:
  - vowel groups;
  - a silent final e;
  - V-CV for one consonant between vowels, VC-CV for two;
  - keep `th`, `sh`, `ch`, `ph` and `wh` with the following vowel, and `ck`, `gh` and `tch` with the preceding one; `-est` and `-ing` keep their own syllable ("sweet-est", "morn-ing"), but a doubled consonant splits ("run-ning");
  - split vowel pairs when the dictionary has more syllables than the spelling shows ("be-ing", "li-on", "al-le-lu-ia").
- Stress comes from the dictionary's digits:
  - primary stress 2, secondary 1, unstressed 0;
  - one-syllable content words 1.5;
  - one-syllable function words 0.3. Keep a list: a, an, the, and, or, but, of, to, in, on, at, by, for, with, from, as, is, it, its, that, this, be, was, were, are, I, you, he, she, we, they, me, my, your, his, her, our, their, so, than, then, if, when.
- Words not in the dictionary count spelling vowel groups and stress their first syllable.
- Punctuation stays on the last syllable.

**Notes:**
- The candidates for syllables are note onsets (not tie continuations).
- Each note carries:
  - its length;
  - its beat strength: downbeat 1.0; the half bar in 4/4 and the second dotted-quarter beat in 6/8, 0.5; other beats 0.25; eighth off-beats 0.125; anything finer 0.0625;
  - whether a rest follows it.

**Alignment** is dynamic programming over syllables and notes. Each syllable takes one note, plus up to 5 more held (a melisma), and every note is used. The costs:

| Situation | Cost |
|---|---|
| Stress against beat | `w * (1 - strength) * 1.0 + (1 - w/2) * strength * 0.3`, where w is the syllable's stress weight |
| Each held note | 0.6; 0.15 on the last syllable of a line; 0.4 inside a word |
| A held syllable that spans a rest | 5 |
| The last syllable of a line on a note with no rest after it and shorter than a beat | 1.5 |
| A rest after a syllable in the middle of a line | 0.8; 2.0 in the middle of a word |
| Neighbouring syllables of one word with the stressed one on the weaker beat ("a-BASH" sung "A-bash") | 1.5 (added after the first real test: `copyist check` warned about it) |
| The first syllable of a line not after a rest or a note at least a beat long | 0.5 |

More syllables than notes: before aligning, split the longest notes (a beat or longer, not ending a line) into two equal notes of the same pitch, one per missing syllable. Each split costs 2.0 and is listed in the report. If it would take more than 10% splits, reject the candidate: it was written for different words.

**Output:**
- Copyist lyric syntax:
  - syllables of a word joined by `-`;
  - a held syllable inside a word written `syl-_ ` and the word continued in the next chunk;
  - at a word's end, `syl_` for each held note.
- The format is in `copyist/lyrics.py` (`tokenize`). Round-trip test: after writing, `lyrics.align` must report `fits` for the verse.
- The whole song is one lyric "verse", because the song is through-composed.

## Scoring and choosing

Run `validate.validate` on each song file. Then rank by:
1. No failing checks.
2. The fit cost per syllable (lower is better).
3. Prosody warnings.
4. Notes outside the voice range, then the largest leap (over a 9th is a warning).
5. Chord-tone warnings.
6. A hook measure: how often the chorus's first two-bar rhythm and contour come back. Higher is better, and only when there's a chorus.

The report shows the measures and the ranking. The person still chooses by ear. The ranking only orders the list.

## The page

A "Write a song" button in the song list opens a form:
- a lyrics box;
- the style (grouped like the Styles section);
- the voice;
- the number of candidates.

It starts a job (`copyist write`) and shows each candidate as it lands:
- the band preview, plus the YuE2 take if it was asked for;
- its key, meter and tempo;
- its sections;
- its scores.

Each candidate has "Keep this one", which keeps it, writes its score and opens it on its Song tab. "Write 4 more" runs the next seeds. The songs being written are listed in the drawer under "Being written". The scores are said in words ("passes every check; the words sit well on the beat"), with the numbers in the report.

## Tests (tests/test_write.py)

Use hand-written plans in the YuE2 dialect, not model output, kept in `tests/data/plans/`. Cover:
- **Parsing:** sections, both voices, `Zn`, ties, chords on rests, and refusal of tuplets.
- **Octave and range:** an alto plan, a tenor plan, and one needing a semitone transposition.
- **Units:** 1/32 data rescaling to 1/8 and to 1/16.
- **Syllables:** a table of 40 words with their expected splits and stresses (feathers, perches, sweetest, extremity, alleluia, being, fire, hour, every, heaven).
- **Alignment:** exact counts; one extra note (a melisma at a line end); one missing note (a split); a line end that must land on a rest.
- **End to end with a fake `yue-plan`** (a script that writes a fixed plan, as tests/test_yue.py fakes `yue-synth`): `copyist write` makes N candidates, every song file loads, `lyrics-fit` passes, and `candidates.json` is ranked.
- **Keep:** the chosen file is copied, and nothing else in `songs/` changes.
- **Rewrite:** `tests/test_rewrite.py` — section bounds, raising notes without moving chords, swapping a chorus from a donor, simpler preferring smaller leaps, `--keep`.

## Later

- **The page:** buttons on a kept song for "again" / "higher" / "simpler", listing rewrite candidates like the write page.
- **A rule-based writer, entirely Copyist's own (MIT),** as a fallback without YuE2: rhythm from the syllables' stress, pitches from the chords with contour templates, motifs repeated and varied, cadences at line ends.
- **The open singer** (docs/open-singer.md) will take Copyist's scores the same way, so melody writing doesn't depend on YuE2's planner forever. The rule-based writer and a planner trained on open data are how to get there.
