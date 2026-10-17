# Copyist specification

*The song, the score, the sound.* Version 0.2, 17 October 2026. This is the source of truth for what Copyist is and how it works. If code and this document disagree, fix one of them in the same change and note it in DECISIONS.md.

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
- **People direct; no musical skills required.** The words and the intent come from people. Nobody should need to sing, play an instrument or read notation to use Copyist: every choice can be made by reading plain language and listening, then saying keep, change or try again. A person who does read music can always see and edit every note.
- **Melodies are earned, not assumed.** A melody comes from one of three places: transcribed from a recording the person already has (section 12), proposed by Copyist and auditioned by ear, or written as notation by someone who reads music. Whatever the source, it passes the same validators.
- **Real musicians can use it.** Parts must be playable and readable: correct transpositions, ranges, clefs, beaming, spelling, page turns.
- **Clean data, real consent.** No training on scraped copyrighted scores or recordings. Public domain, licensed, synthetic and opt-in material only. No voice is cloned without its owner's consent.
- **Open and private.** Runs locally where possible. No telemetry.

### Who it's for

- Songwriters who write words and know what they want to hear, whether or not they sing, play or read music, and want finished arrangements and charts.
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
| Band audio | WAV, plus a stem per part | The arrangement performed (section 6) and played part by part on sampled instruments through sfizz, mixed in one room and mastered gently (docs/sound-set.md). For checking the score by ear. The GeneralUser GS SoundFont plays when the instruments aren't installed |
| Production | WAV, one folder per take | YuE2 performs the score, band and singer together, optionally in a trained voice (section 6) |
| Validation report | Markdown | Every check, pass or fail, with bar and beat |
| Melody check | Markdown | `copyist follow`: how many sung notes match the score, in which octave, and each phrase's timing |

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
2. **Melody.** In ABC notation, from one of three sources: transcribed from an existing recording (section 12, milestone MT), proposed by a model (models trained on ABC exist, e.g. MuPT, and LLMs write it reasonably well; M3), or written by someone who reads music. Auditioning is by ear: candidates are rendered so the person listens and chooses, and Copyist can choose on its own when asked. Every melody must pass the validators.
3. **Validators.** Deterministic checks (section 5). Failing checks block "finished" status and, during generation, trigger regeneration of the failing section.
4. **Arrangement.** From the lead sheet to an instrumentation template (piano-vocal, rock/pop band, country band, pit orchestra, string quartet, choir). Rule-based first (M1), model-assisted later (M4). Every instrument stays in range and is written in its own transposition.
5. **Engraving.** music21 exports MusicXML; Verovio engraves it to SVG; PyMuPDF assembles PDF. Lead sheet, full score and one PDF per part. Verovio's SVG relies on CSS and an embedded music font that MuPDF ignores, so each page is rewritten into plain SVG first (`engrave.printable_svg`). The page header (title, subtitle, words and music credits) is written into Verovio's MEI directly.
6. **Rendering.** Two renders, for two jobs. The band render plays the score exactly: each part on a sampled instrument through sfizz, mixed and mastered, for checking the arrangement by ear (docs/sound-set.md). The production render is YuE2 performing the score (section 6): that's the one meant to be heard.
7. **Verification.** `copyist follow` separates the vocal (Demucs), finds the recording's timing and each phrase's drift, and compares every sung note with the score. A take that doesn't sing the score isn't finished. Later: the same for the bass and drums, and regenerating phrases that drift.

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
  clef: treble         # optional: treble (default), treble-8vb or bass
style: waltz           # optional; a style from copyist/styles/ (section 8.2, docs/styles.md); default by meter
instruments: [voice, piano, bass, drums]   # optional; default all four. Left out = no part at all
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

1. **Sampled render.** M0 played the score through a SoundFont (TinySoundFont and GeneralUser GS): exact, but it sounded like old MIDI. Since 17 October 2026, each part plays on a properly sampled instrument through sfizz, one part at a time, and the parts are balanced by loudness (BS.1770), share one room, and are mastered to -16 LUFS with peaks under -1 dBFS (`copyist/render.py`, `copyist/mixdown.py`). Instruments download in packs, pinned to a git commit and checked file by file (`copyist/instruments.py`); the first pack, the band, is a Salamander grand, Karoryfer upright and electric basses, an AVL drum kit and a VSCO clarinet for the melody. The SoundFont is the fallback. More packs (orchestra and pit, keys, folk and country, percussion, music box and bells, synths) follow, each with arranger templates that write for it (docs/sound-set.md).
2. **Expressive performance (M5; first version done, `copyist/perform.py`).** Turn the plain score into a humanized performance while keeping the same notes. Output is still MIDI. It shapes each phrase's dynamics, leans on strong beats, lets the melody sing over the band and follow its contour, varies timing by a few milliseconds (the melody slightly ahead, piano chords rolled upward), breathes at phrase ends, pedals the piano with the harmony, slows into the last chord, and lets it ring. It's seeded, on by default in `copyist build`, and `--plain` turns it off.
3. **Neural MIDI-to-audio (M6).** A MIDI-conditioned adapter on an open model (ACE-Step 1.5, Apache-2.0, is the leading candidate). Trained on paired score/audio data built by transcribing licensed audio and keeping only confident passages. Verified by transcribing the output and comparing it to the score, plus a realism metric and human listening: both must pass.
4. **Vocals.** Copyist already knows which syllable sits on which note, which is exactly what singing synthesis needs. Candidates, as of October 2026:
   - **SoulX-Singer** (Apache-2.0, February 2026): zero-shot singing voice synthesis conditioned on a score; English, Mandarin, Cantonese. The cleanest path for vocals sung from Copyist's own notes and syllables.
   - **YuE2** (HKUST / M-A-P, September 2026): open song generator that itself plans in ABC notation and accepts a ready-made ABC score to perform. In the authors' blind expert test it roughly tied Suno v5 (best of 8). Weights are CC BY-NC 4.0, with an added permission for individual creators to sell songs; companies need a separate license. Strong candidate for full-band-plus-vocal rendering of Copyist scores, licence permitting.
   - **ACE-Step 1.5** (Apache-2.0): the most permissive full-song model.
   - Fallbacks: DiffSinger guide vocal plus consented voice conversion (e.g. Seed-VC).
   Whatever renders the voice, every sung note's pitch is checked against the score (pYIN; the middle of each note, ±50 cents) and the words are checked by transcribing the vocal with Whisper. Drifting phrases are nudged or regenerated.

   **Status, 17 October 2026.**

   - **YuE2 is the production render** (`copyist produce`, `copyist/yue.py`, docs/production.md). Copyist writes the score in YuE2's own ABC and yue2.cpp performs it, band and singer together; on an M4 Max a verse takes about as long to render as to play. YuE2 sings **one octave below** the ABC it's given (measured twice on Amazing Grace: written D4–D5 came back D3–D4, 32 of 32 notes; written an octave up came back in the right octave, 30 of 32), so the vocal goes to YuE2 an octave up. It also shortens the intro and drifts, coming in up to about 2 s early, so `copyist follow` finds the timing before comparing notes.
   - **SoulX-Singer and the band render are checking tools** (`copyist sing`, docs/singing.md; docs/sound-set.md). SoulX sings the exact notes and syllables (10 of 10 on pitch, every word heard), but it doesn't sound like a record, and it can be glitchy.
   - **A voice for YuE2 comes from a LoRA** (docs/voice-lora.md): a small add-on trained on one artist's recordings, called up by a trigger word in the style. `copyist lora-songs` turns prompt sheets (a style and tagged lyrics per song) into training data; `scripts/yue-lora/` tokenizes the audio and trains on Apple Silicon, CUDA or CPU; `copyist produce --lora` renders with it. The first one trained on the 41 songs of *I Left the Lights On* (trigger word `lightson`; 800 steps on the M4 Max, finished 17 October). Loss on two held-out songs was lowest at steps 300 to 500 (4.77 at the start, 3.83 at 300, 4.01 by 800, while the training songs kept falling: it starts memorizing them), and the general singing it was guarded with didn't drift, so steps 300 and 500 are the ones to compare by ear.
   - **Continuation** (opening a render with a few seconds of a real recording) carried a singer's sound into the score, but the melody followed only 14 of 32 notes when the opening's tempo differed. Not reliable yet.

   **Copyist ships no voices.** A voice is a reference recording in the git-ignored `voices/` folder (SoulX), or a LoRA in `.cache/` (YuE2); neither is committed or published. A voice Copyist ever ships or sells must come from a consenting person, never from another AI generator. Suno's terms (September 2026) forbid using its output to "power, enable or train other artificial intelligence and machine learning models" or to build competing products. The YuE2 weights are CC BY-NC 4.0 with an individual-creator permission; a company needs its own licence before commercial use, and LoRAs trained on them carry the same terms.

## 7. Arrangement (M1 and later)

Arrangement templates are data, not code: a list of instruments with ranges, clefs, transpositions and patterns per `style`.

M1 template **band** (instruments chosen by the song file's `instruments`; anything left out gets no part and is never heard). What each part plays comes from the song's style, a data file (section 8.2, docs/styles.md); there are 23 styles, from waltz, hymn and lullaby to swing, bossa nova, reggae, disco and Broadway. The three original patterns, as examples:

- **Voice**: the melody and lyrics.
- **Piano**: right hand plays close-position chords between G3 and D5, choosing each voicing to move as little as possible from the last (for chords bigger than a triad: root, 3rd and 7th, dropping the 5th); left hand plays the root between E2 and D♯3. Pattern by style (`waltz`: bass on 1, chords on 2 and 3; `ballad`: whole-bar chords; `straight`: chords on every beat). A chord change inside a pattern note splits it.
- **Bass**: root on each chord change and on beat 1; adds the fifth on beat 3 in 4/4. Written an octave above sounding pitch, as bass parts are.
- **Drums**: a groove per style (`waltz`: kick on 1, hi-hat with side-stick on 2 and 3; `ballad`: hi-hat eighths, side-stick on 2 and 4, kick on 1 and 3; `straight`: hi-hat eighths, snare on 2 and 4, kick on 1, the "and" of 2, and 3). A fill every 8 bars, a crash on bar 1 and after each fill, crash and kick on the last bar. Written on a percussion staff in two voices (hands stems up, feet stems down): kick F4, snare and side-stick C5, hi-hat G5 (x), crash A5 (x). The same list of hits builds the MIDI on the General MIDI drum channel, so what's written and what's heard can't differ.

Lyrics with held syllables (`_`) get an extender line when a word ends on the held syllable, and the held notes are slurred when every verse holds there.

Later templates: piano-vocal score, country band (adds acoustic guitar and fiddle), pit orchestra (reeds, brass, strings, keys, percussion), string quartet, SATB choir, music box (a lullaby texture, high and delicate, alone or over strings). Copyist is for everyone's music, so the templates and the sound set grow together: each new template comes with the instrument pack that plays it, and each pack with templates that write for it.

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

A style is a data file in `copyist/styles/` (format `copyist-style/0`, docs/styles.md), not an adjective in a prompt. Copyist aims to arrange in as many styles as can be written as correct scores in twelve-note notation: everyone's music, from music boxes to Broadway, gospel, bluegrass and synth pop. Music built on notes between the piano keys (maqam, raga) and rap verses are out of scope for now.

**Today** a style file gives: its name, family and description; its feel (straight, swing or shuffle, which the performance plays); its usual tempo range; which instrument plays each part; the words YuE2 gets for a finished take; and, for every meter it supports, what each part plays in one bar (chords, shells, arpeggios, chord tones, a walking or boogie bass, drum grooves and fills). `copyist gallery` plays a song in every style for its meter so a style can be chosen by ear, and `copyist use-style` switches a song to one.

**In time**, each profile also defines:

- harmony: typical chord vocabulary and progressions, how often chords change, cadences;
- melody habits: range and tessitura, rhythmic density, syncopation, typical intervals, how phrases end;
- the ensemble: more parts than piano, bass and drums (organ, guitars, strings, brass and reeds, a choir), default and optional instruments, and what each one plays;
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
- LoRAs and voices are trained or made locally from the person's own recordings, kept in `.cache/` and `voices/`, and never committed or published (section 6).
- Sound assets: sampled instruments with clear licences only (CC0, CC BY, or CC BY-SA where music made with them can be sold), downloaded from their authors' own repositories at a pinned commit, never committed; the credits a licence asks for go in each song's report and on the page (docs/sound-set.md). The GeneralUser GS SoundFont (free for any music creation, including commercial) remains as a fallback; its author can't vouch for the origin of every sample, so it isn't the product's sound.

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
| MT Transcription | A recording becomes a song file and charts by fitting (section 12) | For the owner's own AI-generated songs: lead sheet, bass and drum groove close enough that a band could play it and it sounds like the song |

## 12. Transcribing recordings (fit to audio)

Many songs already exist as recordings (for example, songs made with Suno or Mozart AI) and have no sheet music. Milestone MT turns a recording into a song file and charts. It also produces paired recordings and scores, which are training data for M6, but only for audio we have the rights to.

### 12.1 Goal

**The simplest readable score that sounds like the recording.** Not every vibrato wobble written as 32nd notes: what a professional chart would contain. Lead sheet (melody, lyrics, chords), a written bass line, a drum groove with fills, and comping written as chord symbols with rhythm slashes, plus written lines only where a part is distinctive.

### 12.2 Pipeline

1. **Separate** the mix into stems with Demucs (vocals, drums, bass, piano, guitar, other).
2. **Measure:** beats and downbeats, tempo map, key, chord labels, vocal pitch contour, bass notes, drum hits (kick, snare, hi-hat, cymbals), note onsets for other stems, and word timings from Whisper on the vocal stem.
3. **Draft a score:** quantize to the beat grid, choose straight or swing, spell notes in the key, align the lyrics' syllables to vocal notes (held syllables become `_`), write the result as a `copyist-song` file plus arrangement parts.
4. **Fit by analysis by synthesis:** render the draft with Copyist's own renderer and compare it to the original stem by stem: pitch contour for voice and bass, onset timing for drums, harmony (chroma) for chords. Make small edits (fix an octave, move a note to the beat, merge or split notes, relabel a chord, switch the feel) and keep an edit when it improves *closeness to the recording* plus *simplicity of notation*. Validators stay on throughout, so the score is always singable and correct.
5. **Review by ear:** the person A/B-switches between the original and the fitted render and marks anything that sounds wrong; marked bars get refitted.

### 12.3 Expected accuracy (to be measured)

| Part | Expectation | Main risk |
|---|---|---|
| Vocal melody | high | slides, vibrato, loose rhythm |
| Lyrics on notes | high | Whisper mishearing; fixed by the person's own lyric text |
| Bass | high | octave errors (range priors fix most) |
| Chord symbols | good | unusual chords |
| Drums | medium | toms and cymbals |
| Piano, guitar, strings (exact notes) | low | many notes at once in a mix; charts use chord symbols and slashes instead |

### 12.4 Tools to evaluate

Demucs (separation), Basic Pitch (notes), torchcrepe or pYIN (vocal pitch), Beat This! or madmom (beats), a chord recognizer, a drum transcriber, Whisper (word timings). Check every license before adding a dependency; some audio libraries are AGPL.

### 12.5 Rights

Only transcribe recordings the user owns or has rights to. The fitted score of someone else's song is still their song.

## 13. In a browser

`copyist serve` (docs/web.md) is a local web page for everything above: the songs, their lyrics and checks, the score as pages, every take with a player, making a new take (voice, strength, verses, seed, style), checking a take's melody, the band playing the score (with each part, its instrument and its stem, and a download for the instruments), and the progress of a voice training run. It also plays the song in every style that fits it and switches the song to the one you pick. It runs the same `copyist` commands, one at a time, on the machine with the GPU, listens on 127.0.0.1 only, and loads nothing from the internet. Choices are made by listening and pressing buttons; nothing on the page needs musical skills.

The plan is for this page to become a free desktop app (Tauri, with the engine and yue2.cpp bundled, models downloaded on first run), so anyone can make songs on their own computer: docs/desktop-app.md.

## 14. Open questions

- License for the code (MIT, Apache-2.0, or GPL to match tools like Seed-VC).
- Which local LLM or API drafts song plans (M2), and how prompts are versioned.
- How users edit notes: YAML by hand, MuseScore round-trip via MusicXML, or editing on the web page.
- Hosting for other people: accounts, a GPU queue, and which renderer licence allows it (YuE2's weights don't, for a company).
- Several singers in one LoRA (the musical has a cast): one trigger word per character, or one LoRA per voice.
- Free libraries with clear licences for the instruments still missing: music box and celesta first, then acoustic guitars, banjo, mandolin, ukulele, pedal steel, accordion, snare brushes and a choir (docs/sound-set.md).
