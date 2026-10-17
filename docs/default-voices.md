# Default singing voices (research, 17 October 2026)

Copyist needs a few good built-in voices (women's and men's, a few styles) without hiring singers, and without copying anyone who hasn't agreed.

## What the law and the licences allow

- **Non-commercial licences fit Copyist** because it's free. YuE2 itself is CC BY-NC.
- **Being a nonprofit or open source doesn't by itself make a use non-commercial, or fair use.** Training on commercial recordings is what the major labels sued Suno and Udio over.
- **Copying a recognizable real singer without consent is out,** whatever the licence. Voice-likeness laws (Tennessee's ELVIS Act, California's) apply, and a federal NO FAKES Act cleared the Senate Judiciary Committee in June 2026.

## Sources checked

| Source | Licence | What's in it | Fit |
|---|---|---|---|
| [GTSinger](https://arxiv.org/html/2409.13832v8) | CC BY-NC-SA 4.0 | 20 singers, 9 languages, 1,366 songs with MusicXML scores and alignments. English: 3 singers (one tenor, two altos), 13.1 hours of singing. Singers consented to open release "for academic research". | Good for a free tool; a voice trained on it is shared under the same licence. "For academic research" is the singers' stated consent, so treat it as research data. |
| [VocalSet](https://zenodo.org/records/1442513) | CC BY 4.0 | 20 professional singers (9 men, 11 women), 10.1 hours: scales, arpeggios, long tones, excerpts. No full songs. | Clean licence; good for timbre, not for songs. |
| US public-domain recordings | Public domain | Recordings published in 1925 or earlier ([UCSB, Public Domain Day 2026](https://adp.library.ucsb.edu/index.php/resources/detail/516)), including jazz, blues, country and classical singers. | Free, but acoustic-era sound, and real (if long-dead) singers. |
| [Free Music Archive dataset](https://arxiv.org/abs/1612.01840) | Creative Commons, per track | 106,574 tracks from 16,341 artists. | Good for style LoRAs over many artists, never one artist's voice. Check each track's licence. |

## The plan

1. **Voice presets, now.** Style lines and seeds that YuE2 renders as a consistent singer (female Broadway alto, folk soprano, country male baritone, soul tenor, choir). They're synthetic, so they belong to nobody. Test each across several songs and keep the steady ones.
2. **Synthetic voice LoRAs.** Have YuE2 sing many songs in one preset; group the takes by voice with a speaker-embedding model (for example SpeechBrain's ECAPA model) and keep the biggest group that sounds like one singer; train a LoRA on that group with `scripts/yue-lora/`. A steady voice that's nobody's.
3. **GTSinger's English singers** as research voices, credited, under CC BY-NC-SA.
4. **Style LoRAs** (a pit band, a folk band, a country band) from Creative Commons music across many artists.
