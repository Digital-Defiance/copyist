# Copyist specification

*The song, the score, the sound.* Version 0.1, October 2026. This is the source of truth for what Copyist is and how it works. If code and this document disagree, fix one of them in the same change and note it in DECISIONS.md.

## 1. What Copyist is

Copyist is an open-source system that makes songs the way a composer, a copyist and a band would. It produces three things from one source:

1. **The song**: melody, harmony, lyrics and form.
2. **The score**: a lead sheet, a full score, and a correct part for every player.
3. **The sound**: a recording made from exactly those notes.

### Why

Audio-first generators (Suno, Mozart AI, Udio) create sound directly. The notes never exist as data, so any MIDI or sheet music has to be transcribed back out of the audio, with wrong octaves, ghost notes, smeared rhythms, no key, no chord names, no note spelling and no lyric alignment. Copyist inverts the pipeline: **the score is the source of truth, and audio is rendered from it.** Sheet music is correct by construction, and what you hear always matches what is written.

### Principles

- **Notes first.** Every output is derived from one canonical score. Nothing is guessed back from audio.
- **Correct, then beautiful.** Deterministic validators gate every stage. A score that fails validation is never presented as finished.
- **People write the heart.** The best melodies, hooks and lyrics come from people. Copyist helps write, smooth, harmonize, arrange, engrave and perform; it can also propose melodies, but a human can always see, edit and own every note.
- **Real musicians can use it.** Parts must be playable and readable: correct transpositions, ranges, clefs, beaming, spelling, page turns.
- **Clean data, real consent.** No training on scraped copyrighted scores or recordings. Public domain, licensed, synthetic and opt-in material only. No voice is cloned without its owner's consent.
- **Open and private.** Runs locally where possible. No telemetry.

### Who it's for

- Songwriters who think in lyrics and melodies and want finished arrangements and charts.
- Musical theater: lead sheets in each singer's key, piano-vocal scores, pit parts, rehearsal tracks with changeable key and tempo.
- Bands and church or school ensembles that need parts for their actual instrumentation.

## 2. Outputs

For every song:

| Output | Format | Notes |
|---|---|---|
| Lead sheet | PDF, MusicXML | Melody, chord symbols, all verses of lyrics, title and credits |
| Full score | PDF, MusicXML | Every instrument, concert pitch or transposed (option) |
| Parts | PDF per player | Transposed for the instrument, correct clef and range |
| MIDI | .mid | Full arrangement; one track per instrument |
| Demo audio | WAV | Rendered from the MIDI (sampled instruments at M0; better renderers later) |
| Validation report | Markdown | Every check, pass or fail, with bar and beat |

## 3. Architecture

```
 song plan ──> melody ──> validators ──> arrangement ──> engraving ──> PDF / MusicXML
 (form, key,   (person or                (instruments,    (Verovio)
  chords,       model, as ABC)            voicings, parts)
  lyrics)                │                     │
                         └──────── canonical score (music21) ──> MIDI ──> renderer ──> audio
                                                                            │
                                                     verify: transcribe audio, compare to score
```

### 3.1 Canonical score

Internally every song is a `music21` `Score`. On disk the source of truth is the **song file** (section 4), and the canonical exchange format is **MusicXML**, which MuseScore, Dorico, Sibelius and Finale all read.

### 3.2 Stages

1. **Song plan.** Form (verse/chorus/bridge), key, meter, tempo, chord chart, lyrics broken into syllables with stress marks. Can be written by hand or drafted by an LLM. (M2)
2. **Melody.** Written by a person, or proposed by a model, in ABC notation. Models trained on ABC exist (e.g. MuPT), and LLMs write it reasonably well. Every proposal must pass the validators. (Hand-written at M0; generation at M3.)
3. **Validators.** Deterministic checks (section 5). Failing checks block "finished" status and, during generation, trigger regeneration of the failing section.
4. **Arrangement.** From the lead sheet to an instrumentation template (piano-vocal, rock/pop band, country band, pit orchestra, string quartet, choir). Rule-based first (M1), model-assisted later (M4). Every instrument stays in range and is written in its own transposition.
5. **Engraving.** music21 exports MusicXML; Verovio engraves it to SVG; PyMuPDF assembles PDF. Lead sheet, full score and one PDF per part. Verovio's SVG relies on CSS and an embedded music font that MuPDF ignores, so each page is rewritten into plain SVG first (`engrave.printable_svg`). The page header (title, subtitle, words and music credits) is written into Verovio's MEI directly.
6. **Rendering.** MIDI → audio. M0: sampled instruments via a SoundFont (GeneralUser GS) with TinySoundFont. Later: an expressive-performance layer (timing, dynamics, articulation as MIDI), better sample libraries, a MIDI-conditioned neural renderer, and singing (section 6).
7. **Verification.** For neural renders: transcribe each rendered stem, compare it to the score within tolerances, and regenerate sections that drift. (M5)

## 4. Song file format (`copyist-song/0`)

A song is one YAML file in `songs/`. The melody is written in ABC notation, which is compact, readable, widely supported, and what symbolic-music models are trained on.

```yaml
format: copyist-song/0
title: Amazing Grace
credits:
  words: John Newton (1779)
  music: Traditional, tune "New Britain" (1829)
key: G                 # ABC key: G, Em, Bb, F#m, D dorian, ...
meter: 3/4
unit: 1/4              # ABC default note length (L:). Optional, default 1/4.
tempo: 80              # quarter notes per minute, or an ABC tempo string like "3/8=60"
voice:
  name: Melody
  range: [D4, E5]      # optional; the range check uses it
style: waltz           # optional; picks the arrangement pattern (see section 7)
melody: |
  D | "G"G2 B/G/ | B2 A | "C"G2 E | "G"D2 D |
lyrics:                # one entry per verse
  - A-maz-ing_ grace, how sweet the sound
```

### Melody (ABC subset)

- Notes `C D E F G A B c d e f g a b`, octave marks `,` (down) and `'` (up). `C` is middle C (C4). Accidentals `^` sharp, `_` flat, `=` natural.
- Lengths are multiples of `unit`: `A2` = two units, `A/` = half a unit, `A3/2` = one and a half.
- Rests `z`. Ties `-` (e.g. `d3- | d2`). Bar lines `|`.
- Chord symbols in double quotes before the note they start on: `"G"`, `"D7"`, `"Am/C"`. A chord lasts until the next chord symbol.
- A first bar shorter than the meter is a pickup; the last bar should complete it.

### Lyrics

Same syntax as ABC `w:` lines, aligned by Copyist:

- Syllables are separated by spaces; a hyphen splits one word into syllables: `A-maz-ing`.
- `_` holds the previous syllable over the next note (a melisma): `ing_` sings "ing" across two notes.
- `*` skips a note (no syllable).
- Tied continuation notes and rests never take a syllable.
- Punctuation stays attached to its syllable.

### Versioning

Breaking changes to the format bump the version (`copyist-song/1`) and get a converter.

## 5. Validators

Each check reports `pass`, `warn` or `fail`, with bar and beat. A song is **finished** only with no `fail`.

| ID | Check | Severity |
|---|---|---|
| `bars` | Every bar, as written between bar lines in the song file, adds up to the meter (pickup and final bar may be partial, and should add up to one bar together). Checked on the source text because music21 silently re-bars overfull bars | fail |
| `lyrics-fit` | Each verse has exactly one syllable per available note (after ties, rests, `_` and `*`) | fail |
| `range` | Melody stays within the voice's range | fail outside by more than a whole step, else warn |
| `chord-tones` | Melody notes on strong beats are chord tones, or are listed as non-chord tones (suspensions and appoggiaturas are allowed but listed) | warn |
| `prosody` | In multi-syllable words, the stressed syllable doesn't land on a weaker beat than an unstressed syllable of the same word (CMU Pronouncing Dictionary) | warn |
| `key` | Chord symbols parse and melody accidentals outside the key are listed | warn |

Planned: `breath` (singers get a breath at least every N bars), `tessitura` (where the melody sits, not just its extremes), `voice-leading` (arrangements: parallel fifths and octaves between outer voices, unresolved leading tones), `playability` (per-instrument ranges, idiomatic writing), `page-turns` (parts).

## 6. Sound: rendering roadmap

1. **Sampled render (M0).** SoundFont via TinySoundFont. Exact and predictable; sounds like a demo.
2. **Expressive performance (M5).** Turn the plain score into a humanized performance (timing, dynamics, pedaling, articulation) while keeping the same notes. Output is still MIDI.
3. **Neural MIDI-to-audio (M6).** A MIDI-conditioned adapter on an open model (ACE-Step 1.5, Apache-2.0, is the leading candidate). Trained on paired score/audio data built by transcribing licensed audio and keeping only confident passages. Verified by transcribing the output and comparing it to the score, plus a realism metric and human listening: both must pass.
4. **Vocals.** Short term: a guide vocal (singing synthesis such as DiffSinger, or a person's scratch take) plus consented singing voice conversion (e.g. Seed-VC). Long term: a note-conditioned singing model. Pitch is checked per phrase and nudged or regenerated.

## 7. Arrangement (M1 and later)

Arrangement templates are data, not code: a list of instruments with ranges, clefs, transpositions and patterns per `style`.

M1 template **band**:

- **Voice**: the melody and lyrics.
- **Piano**: right hand plays close-position chords between G3 and D5, choosing each voicing to move as little as possible from the last (for chords bigger than a triad: root, 3rd and 7th, dropping the 5th); left hand plays the root between E2 and D♯3. Pattern by style (`waltz`: bass on 1, chords on 2 and 3; `ballad`: whole-bar chords; `straight`: chords on every beat). A chord change inside a pattern note splits it.
- **Bass**: root on each chord change and on beat 1; adds the fifth on beat 3 in 4/4. Written an octave above sounding pitch, as bass parts are.

Later templates: piano-vocal score, country band (adds acoustic guitar and fiddle), pit orchestra (reeds, brass, strings, keys, percussion), string quartet, SATB choir.

## 8. Following directions

A prompt like "slow outlaw-country ballad, no drums, pedal steel and fiddle, for a low alto" must be obeyed, and Copyist must be able to show that it was. Audio-first tools treat instructions as hints to a black box. Copyist turns each one into something it builds and then checks.

### 8.1 The brief

The prompt is turned (by an LLM, M2) into a **brief**: a short YAML file the person can read and edit before anything is generated.

```yaml
format: copyist-brief/0
prompt: slow outlaw-country ballad, no drums, pedal steel and fiddle, for a low alto
style: outlaw-country
feel: ballad            # a pattern within the style
tempo: [66, 76]         # allowed range, quarter notes per minute
meter: 4/4
voice: { type: alto, range: [F3, C5] }
instruments:
  include: [voice, acoustic-guitar, pedal-steel, fiddle, bass]
  exclude: [drums]
form: [verse, verse, chorus, verse, chorus, bridge, chorus]
directions:             # free-text asks, each mapped to a check where possible
  - the chorus should lift
  - end quietly
```

Rules:

- **Exclusions are absolute.** An excluded instrument never gets a part, so it can't be heard. Inclusions always get a part.
- **Ambiguity is resolved in the brief, not silently.** If the prompt doesn't say, the brief records the default it chose, so the person can change it.
- **The brief is versioned with the song.** Regenerating from the same brief and seed gives the same song.

### 8.2 Style profiles

A style is a data file in `styles/`, not an adjective in a prompt. Each profile defines:

- harmony: typical chord vocabulary and progressions, how often chords change, cadences;
- rhythm feel: straight, swing, shuffle, two-beat, train beat; tempo range;
- melody habits: range and tessitura, rhythmic density, syncopation, typical intervals, how phrases end;
- instrument palette: default instruments, optional ones, and what each one plays (patterns, voicings, fills);
- form conventions: intro and outro shapes, typical section lengths.

The arranger only plays what the profile and brief allow. New profiles can be drafted by an LLM from a description and reference notes, then reviewed by a person before use. Profiles describe conventions; they never copy specific songs.

### 8.3 Writing melody to directions

Melody candidates are generated under hard constraints (the lyrics' syllables and stresses, the chord chart, the singer's range, the style's rhythm habits), then:

1. **Validators** (section 5) reject anything that breaks a hard rule.
2. **Scorers** rank the rest against the style and the brief: rhythmic density and syncopation against the profile, contour, repetition and motif strength (does it have a hook), the chorus sitting higher or denser than the verse when asked to "lift".
3. **A person picks and edits.** Several candidates per section, each rendered so it can be heard.

### 8.4 Direction checks

Every item in the brief becomes a line in the report: checked and passed, checked and failed, or *not verified* when no automatic check exists yet. For example: "Excluded drums: no drum part ✓", "Tempo 66–76: 72 ✓", "Chorus lifts: chorus average pitch is a 4th above the verse ✓", "End quietly: not verified". Nothing is silently ignored.

## 9. Quality bar for scores

A score is "good" when a professional player could sight-read it:

- Notes spelled in the key (F♯ in D major, not G♭); accidentals minimal.
- Beaming follows the meter; rhythms are notated the way players expect (no beat-obscuring ties).
- Lyrics aligned with hyphens between syllables and extender lines on melismas.
- Chord symbols above the staff, standard spelling.
- Title, credits, tempo, key and meter on the first page; rehearsal marks at sections.
- Parts transposed and in a readable clef and range for the instrument; multi-bar rests consolidated.
- Nothing collides; pages turn at rests where possible.

## 10. Data and licensing

- Test songs in `songs/` must be public domain or written for this project. Never commit copyrighted lyrics or melodies.
- Training data (later milestones): public-domain scores, licensed or commissioned recordings, synthetic data, and contributions with explicit opt-in. Keep a manifest of every source and its license.
- Sound assets: GeneralUser GS SoundFont (free for any music creation, including commercial; downloaded at first use into `.cache/`, not committed). Its author can't vouch for the origin of every sample, so a product release should switch to a SoundFont or sample library with documented provenance.

## 11. Milestones

See ROADMAP.md for status and the task-level checklist.

| Milestone | Delivers | Done when |
|---|---|---|
| M0 Walking skeleton | Song file → validated lead sheet PDF, MusicXML, MIDI, demo WAV, report | `copyist build songs/amazing-grace.yaml` produces all outputs and the lead sheet passes the section 9 checklist by eye |
| M1 Band arrangement | Full score and parts for the `band` template | Parts are in range, correctly transposed, and readable |
| M2 Song planning | LLM drafts a song plan from a brief and lyrics; syllables and stresses marked | Plans validate; a person can edit them as YAML |
| M3 Melody proposals | Model proposes melodies for sections; validators gate; person picks and edits | Proposals pass validators; a songwriter finds at least one usable per section |
| M4 More arrangements | Piano-vocal, country band, pit orchestra templates; voice-leading checks | A music director would accept the charts |
| M5 Better sound | Expressive performance layer, better instruments, guide vocals | A listener prefers it to M0 audio in blind tests |
| M6 Neural rendering | MIDI-conditioned neural renderer with transcription check | Passes both the note check and listening tests |

## 12. Open questions

- License for the code (MIT, Apache-2.0, or GPL to match tools like Seed-VC).
- Which local LLM or API drafts song plans (M2), and how prompts are versioned.
- How users edit: YAML by hand, MuseScore round-trip via MusicXML, or a web editor.
