# A sound set for the score preview and the parts

The production take comes from YuE2, which plays the whole band itself. But Copyist also renders the score directly: the preview, and audio for each part a band would read. Today that's the GeneralUser GS SoundFont through TinySoundFont, and it sounds like old MIDI. The plan is to swap in properly sampled free libraries, played by sfizz.

## Libraries (licences checked 17 October 2026)

| Part | Library | Licence | Format | Notes |
|---|---|---|---|---|
| Piano | [Salamander Grand Piano V3](https://github.com/sfzinstruments/SalamanderGrandPiano) | CC BY 3.0 | SFZ + FLAC | 48 kHz, 24-bit, 16 velocity layers. Credit: "Salamander Grand Piano V3 by Alexander Holm, CC BY 3.0". |
| Orchestra | [VSCO 2 Community Edition](https://versilian-studios.com/vsco-community/) | CC0 | SFZ + WAV | About 3,000 samples, about 3 GB: strings, woodwinds, brass, percussion. No credit required. |
| Everything else | [VCSL, the Versilian Community Sample Library](https://github.com/sgossner/VCSL) | CC0 | WAV, SFZ release | Aerophones, chordophones, electrophones, idiophones, membranophones. No credit required. |
| Drums | [AVL Drumkits](https://www.bandshed.net/avldrumkits/) | CC BY-SA 3.0 | SFZ (also Hydrogen, SF2) | Music made with them can be sold without credit; credit and share-alike apply only to changed samples. |
| Player | [sfizz](https://github.com/sfztools/sfizz) | BSD-2-Clause | C/C++ library, macOS supported | `sfizz_render --sfz … --midi … --wav …` renders one MIDI file with one instrument to WAV. |

Still to find: electric and upright bass, and guitars. Karoryfer's free instruments are "royalty-free" but don't name a licence, so they need checking before use.

## How it fits

- Render each part on its own: the arrangement already writes one MIDI track per instrument, so each part goes through `sfizz_render` with its library, and the parts are mixed. That gives stems too.
- The libraries are big (several GB), so they download on first use into the data folder, pinned and verified like the models (`copyist/models.py`), rather than shipping in the app.
- Attribution goes in the app's credits, and in each song's report when a CC BY instrument played in it.

## Next

1. Build `sfizz_render` and render Amazing Grace with the Salamander piano and an AVL kit; compare with the SoundFont by ear.
2. Find a bass and a guitar with clear licences.
3. Add these to the model catalog as an "Instruments" download, and switch `render.py` over.
