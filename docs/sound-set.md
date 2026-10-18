# The sound set: sampled instruments for the score

The finished take comes from YuE2, which plays the whole band itself (docs/production.md). Copyist also plays the score directly, so it can be checked by ear: the band recording on the Sound tab, `out/<song>/<song>.wav` from `copyist build`, and one stem per part. This document covers how that sound is made, the instruments it uses, and what's still to come.

The sound set is for everyone who uses Copyist, not one kind of music. Music boxes, Broadway pit orchestras, country bands, hymns and synth pop all need their own instruments, and the arranger needs to learn to write for each one (SPEC section 7).

## How a song is played (`copyist/render.py`, `copyist/mixdown.py`)

1. **Performance.** The arrangement's MIDI is performed first (`copyist/perform.py`): phrase dynamics, metric accents, small timing variation, rolled piano chords, pedal, breaths and a final ritardando. No note is changed.
2. **One part at a time.** The MIDI is split into its parts (melody, piano, bass, drums). Every part keeps the song's tempo and meter events, so the parts stay together. Each part is played by `sfizz_render` with its instrument at 48 kHz:
   - the melody on the clarinet;
   - the piano on the Salamander grand;
   - the bass on the upright for waltzes and ballads, or the electric bass otherwise;
   - the drums on the AVL kit.
   Amazing Grace takes about 2 seconds a part.
3. **Balance by loudness.** Each part is measured as broadcast meters do (ITU-R BS.1770: K-weighted and gated), then set relative to the melody:
   - piano 4 dB under the melody;
   - bass 6 dB under;
   - drums 9 dB under.
   Balancing by loudness rather than by peak means a quiet clarinet sample and a loud piano sample still sit where they should.
4. **One room.** The parts share one short hall: a synthetic impulse of about 1.3 s that darkens as it decays, with no low end so the bass stays clear. Each part keeps its stereo place in the wet (not a mono wash). The melody and piano get more of it than the bass.
5. **A gentle master.** The mix is set to -16 LUFS, then a look-ahead limiter keeps peaks under -1 dBFS. If that would take more than 4 dB of limiting, the mix stays quieter instead. Amazing Grace needed none.
6. **What you get:**
   - the mix, as 16-bit with dither;
   - `stems/<part>.wav`, 24-bit, each part as it sits in the mix;
   - `stems/midi/<part>.mid`;
   - `audio.json`, saying what played what, which the page reads;
   - an "Audio" section in the report, listing the instruments, the loudness and the credits owed.

If sfizz or an instrument isn't installed, the GeneralUser GS SoundFont plays instead, through TinySoundFont as before. The report and the page say why.

Measured on Amazing Grace:
- every melody and bass note is within half a semitone of the score (pYIN);
- the parts' onsets line up within about 15 ms of each other;
- the stems measure melody -17.8, piano -22.5, bass -24.7 and drums -27.8 LUFS, under a -16.0 LUFS mix that peaks at -3.5 dBFS.

## Getting the instruments (`copyist/instruments.py`)

Each instrument is an SFZ library in a public git repository, pinned to one commit. Only the files the instrument plays are downloaded:
- the SFZ itself;
- its `#include`s;
- the samples its regions name;
- the licence and readme.

Each file is checked against its git object id at that commit. `copyist/sound/manifest.json` lists every file's path, size and id, and is written by `scripts/instruments/manifest.py` from local clones. A file is moved into place only once it matches, so an interrupted download picks up where it stopped. A folder is complete when its `.copyist-complete` marker holds the pinned revision.

Instruments come in **packs**, so nobody downloads an orchestra they won't use. To get them:
- from the command line: `copyist models download band`;
- on the page: the Sound tab's "The band" section has a Download button with a progress bar.

They go into the data folder (`~/Library/Application Support/Copyist/instruments/` on a Mac). A developer copy in `.cache/instruments/` or `COPYIST_INSTRUMENTS` works too.

The player, `sfizz_render` (sfizz, BSD-2-Clause), is built by `scripts/setup-sfizz.sh` into `.cache/sfizz/`. That script pins sfizz at `f5c6e29f` and fetches CMake and Ninja into a private folder if they're missing. The desktop app will bundle `sfizz_render` as a sidecar. `COPYIST_SFIZZ` points at another build.

## The band pack (in Copyist now)

| Part | Instrument | Licence | Download | Credit |
|---|---|---|---|---|
| Piano | [Salamander Grand Piano V3](https://github.com/sfzinstruments/SalamanderGrandPiano) (a Yamaha C5, 16 velocity layers) | CC BY 3.0 | 748 MB | "Salamander Grand Piano V3 by Alexander Holm" |
| Electric bass | [Karoryfer Growlybass](https://github.com/sfzinstruments/karoryfer.growlybass) (Squier Jazz Bass; `growlybass_clean.sfz`) | CC0 | 184 MB | none needed |
| Upright bass | [Karoryfer Meatbass](https://github.com/sfzinstruments/karoryfer.meatbass) (1958 double bass, pizzicato; `Programs/04_pizz.sfz`) | CC0 | 128 MB | none needed |
| Drums | [AVL Drumkits](https://www.bandshed.net/avldrumkits/), Black Pearl 4-piece (General MIDI keys, so Copyist's drum part plays as written) | CC BY-SA 3.0 | 9 MB | "AVL Drumkits by Glen MacArthur". Music made with them can be sold; share-alike applies to changed samples |
| Melody | [VSCO 2 Community Edition](https://versilian-studios.com/vsco-community/) clarinet, sustained, three dynamics | CC0 | 59 MB | none needed |

That's 1.1 GB in all. The credits Copyist owes show up in each song's report and on the page.

**The clarinet's SFZ is Copyist's own** (`copyist/sound/clarinet.sfz`), because VSCO ships the clarinet as WAV files only. `scripts/instruments/clarinet.py` measures every sample and writes it:
- VSCO names its octaves one lower than MIDI's usual C4 = 60. The file named D4 sounds D5.
- The files named F#5 actually sound F5. The measured pitch wins.
- Recordings start up to 0.2 s late, so `offset` skips the silence.
- `tune` corrects each sample to equal temperament.
- The low register is evened out in loudness.
- Held notes loop inside the steady part of the tone, so long phrase endings don't run out of sample.

## Packs to come

Every pack below comes from libraries with clear, free licences: CC0, or CC BY with credit. Each pack also needs arranger templates that write for it. A pack without parts to play is no use.

| Pack | For | Instruments (found, licence checked) |
|---|---|---|
| Orchestra and pit | Broadway, film, hymns | VSCO 2 CE (CC0): violin, viola and cello sections, solo violin and double bass, harp, trumpet, tenor trombone, French horn, tuba, flute, oboe, clarinet, bassoon, piccolo, timpani, glockenspiel, xylophone, marimba |
| Keys | Pop, soul, gospel, baroque | [jRhodes3d](https://github.com/sfzinstruments/jlearman.jRhodes3d) Rhodes (CC BY-NC samples, free to play; credit Jeff Learman); VSCO and VCSL organs; VCSL harpsichords (English, Flemish, French, Italian), vibraphone, upright pianos, Kawai and Steinway grands, a TX81Z FM piano and clavinet |
| Folk and country | Country, Americana, Western swing | [VCSL](https://github.com/sgossner/VCSL) (CC0) harmonicas (Hohner Special 20 in C and F, Super 64 chromatic); VSCO solo violin as a fiddle; [Karoryfer Black and Green Guitars](https://github.com/sfzinstruments/karoryfer.black-and-green-guitars) and [Emilyguitar](https://github.com/sfzinstruments/karoryfer.emilyguitar) (CC0, electric) |
| Percussion | Everything | VCSL (CC0): shakers, tambourines, congas, bongos, cajón, claves, cowbells, triangles, wood block, sleigh bells, mark tree, tubular bells, gongs, suspended cymbals |
| Music box and bells | Lullabies, musical theatre (*I Left the Lights On* has a music box and celesta theme) | VCSL glockenspiel, tubular glockenspiel, hand chimes, kalimbas, vibraphone. A real music box and a celesta still to find |
| Synths | Pop, electronic, ambient | Generated by sfizz itself (sine, saw, square, triangle, noise, with filters and envelopes): pads, leads and synth bass, no download |
| Choir | Broadway, gospel, hymns | Still to find. For finished songs, YuE2 sings real harmonies |

**Still to find**, free with a clear licence:
1. a music box and a celesta (first, for the musical);
2. acoustic steel-string and nylon guitars;
3. banjo, mandolin and ukulele;
4. pedal steel;
5. accordion;
6. snare brushes (the AVL kit has sticks only);
7. a tonewheel organ (could be built from sfizz's generators);
8. a choir ("oohs" and "aahs");
9. uilleann pipes and tin whistle.

Pianobook libraries come with their own terms, and Spitfire LABS can't be redistributed, so neither fits.
