# A voice for YuE2: training a LoRA

`copyist produce` has YuE2 perform a score with the band and singer together. YuE2 picks the singer from the style text, so the voice changes from song to song. A **LoRA** fixes that: a small add-on (about 140 MB) trained on one artist's recordings, which teaches YuE2 how that artist sounds (the singer, the band, the mix). Its style caption starts with a made-up **trigger word**, and putting that word in a render's style calls the sound up.

The training follows the recipe Mothersuperior published for YuE2 artist LoRAs (Hugging Face `Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4`): an AR-half LoRA, half the training songs from the artist and half from YuE2's own songs, stopped well before it memorizes. The code here is Copyist's own.

## 1. The song list

Each song needs its audio, its **full** lyrics with section tags, and a style caption. `copyist lora-songs` builds that from Suno/Mozart-style prompt sheets: one Markdown file per song, numbered like the audio files, with `## Demo style` and `## Lyrics` code blocks.

```
copyist lora-songs "AI Prompts/Act One" "AI Prompts/Act Two" --audio AUDIO_DIR \
  --trigger lightson --out .cache/lora/lights-on/songs.jsonl
```

Section tags become YuE2's (`[Verse 2]` → `[verse]`, `[Pre-Chorus]` → `[prechorus]`), spoken passages become `[spoken]`, and voice tags and production cues are dropped, so the lyrics hold only what the recording sings or says. Check a few songs in the `.jsonl` by eye.

## 2. Setup (once)

Run `scripts/setup-yue.sh` (the renderer) first, then `scripts/setup-yue-train.sh`. The second one downloads about 8.5 GB into `.cache/`: YuE2-3B and its Python package, the realaudio tokenizer and MERT (they turn audio into YuE2 tokens), a pack of 4,732 YuE2 songs used as a regularizer, and the realaudio decoder adapter.

## 3. Train

```
scripts/yue-lora/run.sh .cache/lora/lights-on/songs.jsonl AUDIO_DIR lights-on
```

This tokenizes every song on the GPU with yue2.cpp (`yue-tokenize`), builds `.cache/lora/lights-on/dataset.pt`, then trains under `caffeinate` so the Mac stays awake. It prints seconds per step and the time left. Defaults: 800 steps, rank 32, one song per step, songs up to 8,192 tokens (about 5 minutes). Two songs are held out, and every 100 steps it reports the loss on them, on 4 trained songs, and on YuE2's own songs. Trained songs should fall, held-out songs should fall a little or hold, and YuE2's own should hold. If the held-out loss climbs while the trained loss keeps falling, it's memorizing: use an earlier checkpoint.

Checkpoints land in `.cache/lora/lights-on/lora/` as `step-300.safetensors` … `step-800.safetensors`. If it's interrupted, run the same command with `--resume` on the end.

Memory: the published runs used 14–18 GB on an NVIDIA GPU. A 64 GB Mac fits it. It's slower than a big NVIDIA card, so expect an overnight job.

## 4. Listen

```
copyist produce songs/amazing-grace.yaml --lora .cache/lora/lights-on/lora/step-600.safetensors \
  --style "lightson, in the style of lightson. Theatrical female Broadway lead smooth alto vocal with clear, standard American diction. Broadway cast recording, piano and strings, gentle 3/4 waltz, 80 BPM"
```

Try a few checkpoints and keep the one that sounds most like the artist while still singing the score (`copyist follow`). Add `:0.7` after the file name to soften a LoRA that's too strong.

The LoRA learns from songs without a score (YuE2's `cot=off`), and `produce` sends a score. The recipe uses its LoRAs the same way for covers, but if the score fights the voice, the next step is training with each song's own score as well (transcribed with yue2.cpp's SheetSage2).

## Terms and privacy

The YuE2 weights, the regularizer pack and the realaudio files are CC BY-NC 4.0, so a LoRA trained on them is for non-commercial use, like the base model (DECISIONS.md). A LoRA is trained on whatever recordings you give it, and it stays in `.cache/`, which git ignores: never commit or publish one.
