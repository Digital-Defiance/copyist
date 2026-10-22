# The transcriber: song to score, best in the field for copyists

**Goal (owner, 22 October 2026):** Copyist turns a recorded song into the score a professional copyist would write, and does it better than anything else a copyist can use. That means the lead sheet (melody, lyrics under the notes, chord symbols) and the band's parts (bass, drums, keys, guitar, strings and the rest), readable and correct, under licences that let people sell what they make with it. "Best" is shown with numbers on public test sets, next to the published numbers of the strongest systems.

This plan replaces the encoder bake-off as the way there (DECISIONS, 22 October). The rights rules, the held-out songs and the GPU-window rules are unchanged (AGENTS.md, SPEC §10 and §12.5).

## Where the field is (October 2026)

| System | What it does | How good | Can Copyist ship it? |
|---|---|---|---|
| MuScriptor (Kyutai and Mirelo, July 2026; 1.3B parameters) | Every instrument in a real recording, as MIDI notes | 60.4% of note starts right on its authors' test set, against 32.5% for YourMT3+ | No: weights CC BY-NC 4.0 (code MIT). A yardstick only |
| YourMT3+, MT3 | Every instrument, as MIDI notes | On MulTTiPop (real pop, July 2026) the best of them gets 38% of note starts right | MT3 yes (Apache); YourMT3+ licence to check |
| SheetSage2 | Lead sheet: melody and chords | 82.5 (published, RWC-Pop vocal notes) | No: non-commercial. A yardstick only, never on the owner's songs |
| GAME (openvpi; successor of SOME) | Singing to notes, also with the band still in | No published numbers | Code MIT; the released weights state no licence or training data. A yardstick and a recipe until settled |
| Copyist today (`open`, `neural`) | Lead sheet with lyrics | 20–25 strict on real dev sets; 0.83–0.88 of notes right at lead-sheet level on YuE2 takes | Yes |

What none of them does: write a score. They give notes in seconds, not bars in a meter and key with spelled notes, parts, chord symbols and lyrics under the melody. And none of the strongest is both open and usable commercially.

## The three bets

1. **Song to score, measured as a score.** The output is a Copyist song file plus the band's parts, and it's judged as a copyist would judge it: the right note, in the right place in the bar, in the right part, with the right chord and the right syllable under it. Note-start accuracy in seconds is kept too, so we can compare with the field.
2. **Copyist as the training-data factory.** The strongest new systems start by training on music made by computer. Copyist can make better computer-made *songs* than anyone open: complete songs with singing and lyrics, every part played with real sampled instruments, in many styles and mixes, with every note known because the score came first. The existing training sets (Slakh and friends) have no singing and no lyrics.
3. **Play it back and compare, as a teacher.** Transcribe a recording, play the transcription back with Copyist, compare the two, and reward getting closer. That needs no hand-made answers, so the model can keep learning from any recording it's allowed to learn from, and the same check tells a copyist which bars to look at. Hand-labelled real music is what limits the whole field, and the labelled real songs we have (RWC, the karaoke songs) are for testing only.

## How we measure

One scoreboard, updated every loop (`out/judge/scoreboard.md` on the Mac, numbers only; a summary goes into docs/transcribing.md when it moves). A loop that moves no number twice in a row stops and is reconsidered (TASKS ground rules).

**Sets:**
- **Real songs, dev:** RWC-other dev (30) and karaoke dev (12), frozen in open-transcriber. Non-commercial: testing only, never trained on.
- **AI-made songs like the owner's demos:** YuE2 takes of public-domain songs with known scores (5 now; grow to about 20). The closest domain to *Lights On*.
- **Copyist's own renders:** held-out seeds, every part known. Practice, not proof.
- **Public multi-instrument sets:** the Slakh2100 test split (CC BY 4.0) for the band's parts; MulTTiPop if its audio can be had lawfully (evaluation only).
- **Later, the proof:** COTB, public-domain recordings with checked truth (TASKS §7), used once per candidate.

**Measures, per part:**
- **Melody:** strict (pitch class or exact octave, note start within 50 ms, heard time) and lead-sheet level (the right note in the right place in the bar).
- **Chords:** duration-weighted root and quality.
- **Bass and other parts:** note-start F1 per instrument, the field's usual measure.
- **The score:** meter, key and bar lines right; notes right after quantising; syllables on the right notes.

**Yardsticks, testing only:** MuScriptor, YourMT3+, SheetSage2 and GAME, on public sets only. Never on the owner's songs.

## How we train

- **The data engine:**
  - songs from Copyist's sampler, with the held-out guard;
  - each arranged and played part by part with sampled instruments in many styles, with mix variants (levels, EQ, reverb);
  - YuE2 sings the melody at draft quality, and a take is kept only if it follows its score (`copyist follow`, 90% or better), its notes moved to where they were actually sung;
  - plus VocalSet (CC BY 4.0) for clean singing.
  
  A first batch of about 1,000 songs; then about 10,000. A GPU hour of YuE2 drafts gives an estimated 2–2.5 hours of singing; the band renders on the CPU.
- **The model:** from open code with an MIT or Apache licence (GAME's for the voice; MuScriptor's code, which is MIT, or YourMT3+'s if its licence allows, for the band), sized to train on the M4 Max. The trained weights are ours, MIT.
- **The teacher:** the render-and-compare reward, for post-training on Copyist's renders and on recordings we may learn from.
- **Compute:** the Mac only, in GPU windows the owner grants; $0.

## Steps

1. **This week, no GPU:**
   - this plan in the roadmap, spec, tasks and decisions;
   - a way for the cloud agent to run jobs on the Mac itself;
   - the vocal scoreboard with today's engines and the measured timing correction;
   - GAME measured.
2. **Yardsticks and the band's parts:**
   - MuScriptor and YourMT3+ on the public sets;
   - chords, bass and other parts scored on Copyist renders and the Slakh test split.
3. **Data engine, first batch:** about 1,000 songs. The band renders on the CPU; YuE2 sings in one overnight window.
4. **Train the first model:** the voice first, then every part; measured on the scoreboard after each window.
5. **The teacher:** render-and-compare post-training.
6. **The claim:** numbers on the public sets next to the field's, and the data-engine recipe written up.

Targets, revisited weekly: the scoreboard this week; a first trained voice model in about two weeks; every part in about four to six.

## Parked

- **The ear bake-off** (open-transcriber branch `ear-bakeoff`, 08ad5ce). It asked whether a general music model helps Basic Pitch, a smaller question than this plan's, and three GPU windows gave no answer. Even a clean run wouldn't have given a valid one: it trained on the 80 sampler clips the pre-registration keeps unseen for scoring, never scored synthetic material (so the rule's synthetic test reused the real-dev number), and stopped training by checking its own training data. Kept: the strict scorer, the frozen splits, the guards, the job runner, the 1,200 sampler clips, and the MusicFM, Dasheng and Whisper feature extractors.
- **The SoulX training slice:** SoulX can't pronounce the sampler's letter-sliced syllables (blocker report, 22 October). YuE2 sings the training songs instead.

## *Lights On* in the meantime

Today's engines plus Edit by ear (SPEC §14): transcribe, keep, then fix by listening. Each better engine replaces the first draft, not the workflow.
