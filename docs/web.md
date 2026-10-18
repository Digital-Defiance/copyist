# Copyist in a browser

```
copyist serve
```

Run it from the Copyist folder, or give it a library folder with `--root` (it creates `songs/` and `out/` there; `--demo` adds a demo song to an empty one). It opens http://127.0.0.1:8765/ (`--port` changes the port, `--no-open` skips opening a browser window), and Ctrl-C stops it. `--machine` prints one JSON line with the URL first, for the desktop app (docs/desktop-app.md).

If the singer (YuE2's model files) isn't installed, the sound tab offers to download it: it shows the licence, asks you to accept it, and shows progress.

What's there:

- **Songs**: every song in `songs/`.
- **The song**: the lyrics, and the validators' checks.
- **The score**: the lead sheet, full score and parts, shown as pages. "Write the score" runs `copyist build`.
- **The sound**: every take, with a player, and the form that makes a new one. Pick a trained voice, adjust its strength, the verses and the seed, edit the style, and press "Make the take". That runs `copyist produce --take …`, so each take keeps its own folder in `out/<song>/takes/`. "Check the melody" separates the vocal with Demucs and runs `copyist follow` on it. **The band** plays the score exactly as written, on the sampled instruments, and lists each part with its instrument and a download of its stem, plus the credits the instruments' licences ask for. If the instruments aren't installed, it says the SoundFont played and offers them as a download (1.1 GB, with each instrument's licence shown) with a progress bar; once they're in, "Play it on the real instruments" rebuilds the score. **Styles** plays the song in every style that fits its meter, grouped by family, each with its tempo and what it does: a band preview (`copyist gallery`, seconds a style) and, once made, a finished YuE2 take in that style (`copyist gallery --takes`, in the voice chosen for takes, about 45 s a style); "Use this style" switches the song to it (`copyist use-style`, which changes only the song file's style and tempo lines) and writes the score again. Older experiments (SoulX vocals) are listed under "Earlier tests".
- **Write a song** (in the drawer): a title, the lyrics, a style, the voice, how many melodies, and which writer (YuE2, Copyist's own rules, or auto). "Write the songs" runs `copyist write` (docs/melody-writing.md): the chosen writer makes each melody, Copyist fits the lyrics and checks it, and the band plays it. Each candidate shows up as it lands, best first, with its key, meter, tempo, sections, a band preview and its checks in plain words. "Keep this one" copies it into `songs/` and writes its score, then opens it; "Write 4 more" runs the next seeds. Songs being written are listed under "Being written".
- **Try another melody** (on a kept song's Song tab): pick a section, then **Try again**, **Higher** or **Simpler**. That runs `copyist rewrite` and opens the candidates with band previews; "Keep this one" replaces the song and writes its score. Open rewrites are listed under "Rewrites" in the drawer.
- **Edit the lyrics** (on a kept song's Song tab): change the words, then **Fit lyrics and write the score** (`copyist refit --build`). The melody stays; the words are placed again and the score is rewritten.
- **Transcribe a recording** (in the drawer): choose an audio file (it's copied into `out/uploads/`), give the title and, if you have them, the lyrics, and pick the transcriber: Copyist's own, or SheetSage2 if it's installed (its licence is non-commercial, and the page asks you to accept that). "Transcribe it" runs `copyist transcribe`. The result plays the original and Copyist's band playing the transcription, one after the other, and lists the doubtful spots, what was heard (key, meter, tempo) and the checks. "Keep it" adds it to the songs and writes its score. Transcriptions are listed under "Transcribed".
- **Voice training**: the progress of any run of `scripts/yue-lora/run.sh`: the step, the time left, the losses, and the checkpoints ready to try. "Ready to try" opens the sound tab with that voice chosen and its trigger line in the style.

How it works: `copyist/web/server.py` is Python's own HTTP server. It reads `songs/`, `out/` and `.cache/lora/`, and runs one `copyist` command at a time (the GPU can only do one), keeping each command's output in `out/.jobs/`. The page is plain HTML, CSS and JavaScript in `copyist/web/static/`, with no build step. Fonts (Instrument Serif, Instrument Sans and Source Serif 4, SIL Open Font License) are bundled, so it never fetches anything from the internet.

Safety: it listens on 127.0.0.1 only, serves files from `out/` only, answers only requests addressed to 127.0.0.1 or localhost, and starts jobs only for requests from its own page (a custom header plus an origin check). Other websites can't reach it or start anything.

Not there yet: rewriting one section of a written song, comparing two takes side by side, and running on a server for other people.
