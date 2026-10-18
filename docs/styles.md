# Styles

Copyist is for everyone's music, so it should arrange in as many styles as make sense. This document covers:
- what fits Copyist and what doesn't;
- how a style is written down;
- the styles there are now;
- how the list grows.

## What fits

A style fits Copyist when its music can be written as a correct score in ordinary twelve-note notation, because correct sheet music is what sets Copyist apart. That covers a lot:

- pop, rock and their ballads;
- country, folk, Americana and Celtic;
- Broadway and cabaret;
- jazz, swing and blues;
- soul, R&B, gospel and disco;
- Latin and Caribbean styles;
- hymns, marches, classical chamber music and choirs;
- children's songs, lullabies and music boxes;
- film and cinematic music;
- electronic styles (house, synthwave, lo-fi). Nobody reads a house track's score, but its parts are still exact MIDI and stems.

**What doesn't fit, for now:**
- Music built on notes between the piano keys (Arabic maqam, Indian raga, gamelan tunings). The score and the instruments would both be wrong.
- Rap verses. Copyist ties every syllable to a pitched note, so a rapped verse has nothing to sit on. Rhythm-only notation (slashes and x noteheads) could open this up later.

YuE2, which makes the finished take, already plays any genre. The style decides two things: the score Copyist writes, and the words YuE2 gets in its style line.

## A style is a file (`copyist/styles/<id>.yaml`, format `copyist-style/0`)

```yaml
format: copyist-style/0
name: Swing
family: Jazz and blues
about: Swung eighths. A walking bass, the ride cymbal's spang-a-lang, ...
feel: swing                   # straight (default), swing or shuffle
tempo: [110, 200]             # usual range, in beats a minute (a dotted quarter is the beat in 6/8)
instruments: {bass: upright-bass}   # which instrument plays a part (copyist/instruments.py)
keep_rh: false                    # optional; with melody: piano, keep the right-hand figure (open melody pitches)
production: swing jazz, 1940s, walking upright bass, ride cymbal, piano comping, clarinet, ...
meters:
  "4/4":
    rh: [[0, 0.5, shell], [1.5, 0.5, shell]]          # [start, length, what], quarter notes in one bar
    lh: []
    bass: walk
    drums:
      hands: [[0, 1, [ride]], [1, 0.5, [ride]], [1.5, 0.5, [ride]], ...]
      feet: [[1, 1, [hihat-pedal]], [3, 1, [hihat-pedal]]]
      fill: [[2, 0.5, [snare]], [2.5, 0.5, [snare]], [3, 0.5, [tom]], [3.5, 0.5, [snare]]]
```

A part can list **several bars** instead of one; they cycle as a phrase (bar 1 plays the first, bar 2 the second, then it repeats). The waltz does this so it isn't the same om-pah-pah every bar:

```yaml
rh:
  - [[0, 1, arp1], [1, 1, arp2], [2, 1, arp3]]
  - [[0, 3, chord]]
```

**What each part can play:**

| Part | What it can play |
|---|---|
| Piano right hand (`rh`) | `chord`: a close voicing that moves as little as possible.<br>`shell`: the 3rd and 7th, or the 6th on a plain major chord, for jazz comping.<br>`arp1`–`arp4`: one note of the voicing, lowest first, for broken chords and arpeggios. |
| Piano left hand (`lh`) and bass | `root`, `third`, `fifth`, `sixth`, `seventh` (the chord's own 7th, or the minor 7th).<br>`octave`: the root an octave up.<br>`approach`: a half step into the next chord's root. |
| Bass, instead of a list | `walk`: a walking line, one note a beat. It starts each chord on its root, climbs through chord tones, and ends a half step from the next root.<br>`{line: [...], every: 0.5}`: chord tones climbing from the root, such as a boogie or disco octaves.<br>`none`: no bass part. |
| Drums | `hands`, `feet` and `fill`, from the kit: kick, snare, side-stick, hi-hat (closed, open, pedal), ride, crash, tom, floor tom, tambourine, clap.<br>A fill replaces the end of every 8th bar, and a crash follows it.<br>`none`: no drum part. |

Triplets are written as fractions in quotes, such as `"1/3"`.

A style can support several meters; the hymn has 3/4 and 4/4. A song uses its own `style:`, or the default for its meter:
- 3/4: waltz;
- 4/4: ballad;
- 6/8: lullaby.

A style that doesn't play the song's meter falls back to whole-bar chords, and the report says so. When a style has no bass or no drums, the report notes that it left those parts out.

The arranger reads these files (`copyist/arrange.py`, `copyist/drums.py`). Every file is checked when it loads, and the tests arrange every style on a song in each of its meters (tests/test_styles.py).

**Feel** belongs to the performance: in a swing or shuffle style, off-beat eighths land two thirds of the way through the beat (`copyist/perform.py`), and the score says "Swing" or "Shuffle" over the first bar. `--plain` keeps the swing, since it's how the music is written to be played, and drops the rest of the performance.

## Choosing by ear: the gallery

There are two ways to hear a song in every style that fits its meter. Each plays every style at a tempo inside its usual range.

- **`copyist gallery SONG`: the exact band preview.** Each style is arranged, performed and played on the sampled band. It takes a few seconds a style and runs anywhere. It plays the written notes (the right job for judging a melody or a style sketch). Phrase-level patterns and per-style melody voices (the waltz is piano-vocal, no drums) are how that preview gets less like an arranger keyboard (TASKS 3f, SPEC §15); YuE2 takes stay on demand. Styles whose signature instruments aren't in the band yet (fiddle, steel guitar, organ, horns) are only sketched.
- **`copyist gallery SONG --takes`: finished takes.** YuE2 performs the song in each style, singer and whole band together. The style's own words go into its style line ("swing jazz, walking upright bass, ride cymbal, ... clarinet, horn section"), so each style gets its real instruments.
  - It takes about 45 seconds a style on an M4 Max and needs the singer installed.
  - `--lora` and `--prefix` sing it in a trained voice.
  - Takes go into `out/<song>/gallery/takes/<style>/`, and the song file isn't touched.

Everything goes into `out/<song>/gallery/`, with `gallery.json` as the index.

On the page, the Sound tab's **Styles** section groups the styles by family. Each one has a "Finished take" player and a "Band preview" player when those exist, and a "Use this style" button. The section has buttons for both kinds of gallery; the finished takes use the voice chosen in "Make a take".

`copyist use-style SONG STYLE --tempo N` switches a song from the command line. It changes only the `style:` and `tempo:` lines of the song file, then writes the score again. `copyist styles` lists every style.

## The styles (23 so far)

| Family | Styles |
|---|---|
| Pop and rock | Ballad, Pop, Power ballad, Rock, Straight four, 6/8 ballad |
| Country and folk | Country two-step, Country waltz, Folk (fingerpicked), Celtic jig |
| Musical theatre | Broadway ballad, Broadway uptempo |
| Jazz and blues | Swing, Jazz waltz, Blues shuffle |
| Soul and gospel | Gospel (triplet feel), Disco |
| Latin and Caribbean | Bossa nova, Reggae (one drop) |
| Hymns and classical | Hymn, March, Waltz |
| Children's | Lullaby |

Test songs, all in the public domain:
- *Amazing Grace* (3/4);
- *When the Saints Go Marching In* (4/4);
- *Silent Night* (6/8).

## How it grows

Each wave adds styles together with the parts and instruments they need. A style whose band doesn't exist yet would only be a rough sketch, so the two come together.

1. **New parts in the arranger.** Today it writes voice, piano, bass and drums. Next it needs:
   - organ (sustained chords, reggae bubble, gospel swells);
   - guitar (strummed and fingerpicked patterns, with chord shapes);
   - strings (pads and lines);
   - brass and reeds (hits and backgrounds);
   - a lead line for instrumentals;
   - a choir (oohs and aahs).
   The ensemble becomes part of the style: a string quartet, a pit orchestra, a country band, a big band.
2. **Wave 1, finishing:**
   - music box (high, delicate arpeggios on a music box or celesta; *I Left the Lights On* needs it);
   - gospel and hymn with organ;
   - country with acoustic guitar and fiddle;
   - folk with a real fingerpicked guitar;
   - pop and rock with guitars.
3. **Wave 2:**
   - Latin (salsa with clave, cumbia, bolero, tango);
   - Western swing and bluegrass;
   - Motown and soul;
   - funk;
   - Celtic reel and air;
   - polka;
   - calypso;
   - a 12/8 doo-wop ballad.
4. **Wave 3:**
   - big band;
   - orchestral and cinematic;
   - string quartet;
   - SATB choir;
   - electronic (house, synthwave, lo-fi, ambient).

Every style also needs, over time:
- melody-writing habits for melody proposals (SPEC section 8.2);
- form conventions (intros, endings, section lengths);
- its own melody voice for previews (flute, sax, violin or synth lead, not always the clarinet).

New styles can be drafted from a description, then checked by arranging the test songs and listening. They describe conventions, never copy a particular recording.
