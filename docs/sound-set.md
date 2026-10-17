# A sound set for the score preview and the parts

The production take comes from YuE2, which plays the whole band itself. But Copyist also renders the score directly: the preview, and audio for each part a band would read. Today that's the GeneralUser GS SoundFont through TinySoundFont, and it sounds like old MIDI. The plan is to swap in properly sampled free libraries, played by sfizz.

## Libraries (licences checked 17 October 2026)

| Part | Library | Licence | Format | Notes |
|---|---|---|---|---|
| Piano | [Salamander Grand Piano V3](https://github.com/sfzinstruments/SalamanderGrandPiano) | CC BY 3.0 | SFZ + FLAC | 48 kHz, 24-bit, 16 velocity layers. Credit: "Salamander Grand Piano V3 by Alexander Holm, CC BY 3.0". |
| Orchestra | [VSCO 2 Community Edition](https://versilian-studios.com/vsco-community/) | CC0 | SFZ + WAV | About 3,000 samples, about 3 GB: strings, woodwinds, brass, percussion. No credit required. |
| Everything else | [VCSL, the Versilian Community Sample Library](https://github.com/sgossner/VCSL) | CC0 | WAV, SFZ release | Aerophones, chordophones, electrophones, idiophones, membranophones. No credit required. |
| Bass | [Karoryfer Growlybass](https://github.com/sfzinstruments/karoryfer.growlybass) (Squier Jazz Bass) and [Meatbass](https://github.com/sfzinstruments/karoryfer.meatbass) (1958 double bass) | CC0 | SFZ + WAV | Public domain, like all of Karoryfer's libraries in the sfzinstruments collection. |
| Drums | [AVL Drumkits](https://www.bandshed.net/avldrumkits/) | CC BY-SA 3.0 | SFZ (also Hydrogen, SF2) | Music made with them can be sold without credit; credit and share-alike apply only to changed samples. |
| Player | [sfizz](https://github.com/sfztools/sfizz) | BSD-2-Clause | C/C++ library, macOS supported | `sfizz_render --sfz … --midi … --wav …` renders one MIDI file with one instrument to WAV. |

| Electric guitars | [Karoryfer Black and Green Guitars](https://github.com/sfzinstruments/karoryfer.black-and-green-guitars) (Gretsch Anniversary, Hofner Club) and [Emilyguitar](https://github.com/sfzinstruments/karoryfer.emilyguitar) (Epiphone; ready-made major, minor and power chords) | CC0 | SFZ + WAV | Twang, staccato and hammer-on programs; good for country, rockabilly and jazz. |
| Electric piano | [jRhodes3d](https://github.com/sfzinstruments/jlearman.jRhodes3d) (1977 Rhodes Mark I) | CC0 to play; the samples are CC BY-NC 4.0 to redistribute | SFZ + FLAC | Fine for a free app (credit Jeff Learman). |

Still to find: an acoustic steel-string guitar for folk and country strumming. Nothing with a clear licence turned up yet (Pianobook libraries have their own terms).

## First test (17 October 2026)

Amazing Grace's band MIDI, split into one file per part and rendered with `sfizz_render` (built from source with `-DSFIZZ_RENDER=ON -DSFIZZ_JACK=OFF`): melody and chords on the Salamander piano, Growlybass (`growlybass_clean.sfz`), AVL `Black_Pearl_4pc.sfz` (its keys follow General MIDI drums, so Copyist's drum part plays as written). Each part took under 2 seconds on a 2-core CPU. Download sizes: Salamander 1.4 GB, Growlybass 330 MB for the clean mapping, the AVL kit 17 MB. The playing is still mechanical (flat velocities); the expressive-performance layer (SPEC section 6) is what fixes that.

## How it fits

- Render each part on its own: the arrangement already writes one MIDI track per instrument, so each part goes through `sfizz_render` with its library, and the parts are mixed. That gives stems too.
- The libraries are big (several GB), so they download on first use into the data folder, pinned and verified like the models (`copyist/models.py`), rather than shipping in the app.
- Attribution goes in the app's credits, and in each song's report when a CC BY instrument played in it.

## Next

1. ~~Build `sfizz_render` and render Amazing Grace with the Salamander piano and an AVL kit~~ (done; compare by ear).
2. Find a guitar with a clear licence.
3. Add these to the catalog as an "Instruments" download (pinned to a git revision, only the files each instrument uses), bundle `sfizz_render` as a sidecar, and switch `render.py` over: one render per part, mixed, with stems kept.
4. A melody instrument for previews (a VSCO 2 flute or clarinet) instead of the piano.
