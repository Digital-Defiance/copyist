# Using the whole computer (plan)

**Goal:** Copyist uses everything the owner's Mac has, the CPU, the GPU and the Neural Engine, at the same time where it can, so songs, takes, transcriptions and training finish sooner and the GPU, the scarce part, is kept for the work only it can do. It stays usable on Linux and Windows: an NVIDIA GPU (CUDA), another GPU (Vulkan), or the CPU alone. This is milestone HW in ROADMAP.md, asked for by the owner on 21 October 2026.

**Constraints** (AGENTS.md, "The owner's machine"):
- The Mac is her laptop, an M4 Max with 64 GB. GPU work comes in windows she agrees to, one GPU job at a time, run unattended.
- LM Studio's models take about 36 GB when loaded; they're unloaded before a window.
- $0: free downloads only.
- An agent in a cloud container can't use the Mac's GPU. It writes the scripts and says how long they take; an agent on the Mac runs them.

## The machine

An M4 Max has three engines that can all work at once, on one pool of memory:

| Engine | What it's good at | In Copyist today |
|---|---|---|
| CPU: 12 performance + 4 efficiency cores (16-core model) | Signal processing, rendering samples, engraving, anything branchy | Mostly one core at a time |
| GPU (Metal) | Large models: YuE2, SoulX, training | YuE2 (yue2.cpp), SoulX, Demucs and LoRA training (PyTorch) |
| Neural Engine (16 cores) | Small and mid-size networks with fixed shapes, at low power | Basic Pitch in the open transcriber (Core ML) |

The GPU needs a window and draws the most power. The CPU and the Neural Engine are mostly idle and don't: work moved to them can run outside a window, or alongside a GPU job inside one.

## Where the time goes (measured 21 October 2026)

`scripts/hardware/bench.py` on the M4 Max (16 CPU cores, 12 of them performance cores, 40 GPU cores, 64 GB; macOS 26.6), LM Studio unloaded. The test is verse 1 of Amazing Grace with a 4-bar intro, 47.2 s of audio. Results: `out/hardware/bench-20261021-1423.json` and its log.

| Step | Runs on | Measured |
|---|---|---|
| A YuE2 take | GPU | **47.5 s** for 47.2 s of audio; peak memory 4.6 GB |
| 2 takes in one run | GPU | 84.9 s (42.4 s a take); 7.2 GB |
| 4 takes in one run | GPU | 152.9 s (38.2 s a take): **0.8 of four separate runs**; 12.4 GB |
| 4 variations of one take | GPU | 147.2 s: no saving over four takes; 4.5 GB |
| A melody plan (`yue-plan`) | GPU | 2.9-4.2 s each, 13.6 s for four |
| Separating the vocal (Demucs) | GPU (MPS) / CPU | 4.5 s on the GPU with Metal warm, 10.9 s on the CPU (the first run's 20 s on the GPU was a cold start) |
| Hearing the words (faster-whisper base.en) | CPU | 2.2 s |
| Pitch tracking (pYIN, one core) | CPU | 2.2 s (0.05× real time) |
| The band (sfizz, 3 parts) | CPU | 4.1 s one part at a time, 2.9 s side by side |

**Inside a take** (yue2.cpp's own log, the single take):

| Stage | Time | Share |
|---|---|---|
| Loading the three models | 3.2 s cold, about 0.6 s once they're in the disk cache | 7% |
| The performance (the autoregressive half: the codes) | 6.9 s (5.8 ms a frame) | 16% |
| **Rendering it (flow matching: 32 steps over every frame)** | **28.7 s** (0.80-1.0 s a step) | **65%** |
| The VAE (latents to sound) | 5.2 s | 12% |

What that means:
- **The render is the cost, and it doesn't batch.** In a batch, the performances are drawn together: 9.3 s for four, against 6.9 s for one, as expected of a stage limited by memory bandwidth. But each take's 32 render steps still run one take at a time, and the GPU is already full during them: 4 variations in one graph took 3.7 s a step, exactly four times one. So 4 takes in one run save only a fifth.
- **Loading is small.** Keeping YuE2 loaded (`yue-server --keep-loaded`) would save about half a second a take once the files are in the disk cache.
- **The GPU slows as it heats.** A render step took 0.80 s at the start of the first take and 0.97 s by its end, and 0.95-1.02 s through the batches: about 20% slower under sustained load, with the Mac's energy settings already at their highest (owner, 21 October). That's the cost of heat on a laptop; long batches should expect it.
- **Batched takes are the same takes.** Take 2 of a batch has exactly the performance (the same codes) as that take rendered alone; only the last bits of the audio differ.
- **The CPU steps are already quick on this Mac.** Whisper, pYIN and the band take seconds. Demucs is 2.4× faster on the GPU once Metal is warm (second run), so it stays there. It also contacted the Hugging Face Hub on every run, even with its model downloaded (fixed: H4).

## The levers, in order (revised after H1)

### H1. Measure. Done 21 October

### H2. Draft takes, then the final one. Built 21 October

The render's 32 steps are two-thirds of every take, and yue2.cpp can re-render a take from its codes (its replay request) with any number of steps, without drawing the performance again.

**Measured** (`bench.py --only steps`, `out/hardware/bench-20261021-1445.json`): one take's codes rendered again at each step count, each checked automatically.

| Steps | Render | Sound against 32 steps | Notes on pitch | Words heard |
|---|---|---|---|---|
| 32 | 37.0 s | 0 (the floor: two 32-step renders differ by 0.02 dB) | 0.969 | 0.923 |
| 16 | 20.9 s | 0.08 dB | 0.969 | 0.923 |
| **12** | **16.9 s** | **0.11 dB** | **0.969** | **0.923** |
| 8 | 13.3 s | 0.23 dB | 0.969 | 0.923 |

A step costs 0.87-0.95 s whatever the count, and about 6 s of each render is fixed (the VAE and loading). Even 8 steps keep the melody and the words as far as the checks can tell. The checks can't hear the small differences in sound, though, and an earlier 8-step render sounded rougher by ear. So **drafts use 12 steps**: 2.2× quicker to render than a finished take, with half 8's distance from it.

**Built:**
- `copyist produce --draft` (with `--takes N` for several in one run), and `--steps N` to choose.
- `copyist finish SONG TAKE` renders a draft again from its own codes at 32 steps: the same melody, words, phrasing and voice, at full quality. The draft is kept beside it as `draft.wav`.
- The page: "Quality: Quick drafts, to choose from" on the take form, a Draft tag on draft takes, and "Finish this take".

Expected for choosing between four on the Mac, from the step times: about 75 s for four drafts and about 37 s to finish one, against 153 s for four finished takes.

### H3. The page: a GPU lane and a CPU lane

Unchanged. A take holds the GPU for about the length of the song, so a band preview, an engraving or a check shouldn't wait behind it.

### H4. The CPU

- Band parts side by side: built (1.4× on a three-part waltz; more for fuller bands).
- Demucs stays on the GPU (2.4× the CPU, warm). **Built:** it runs offline once its model is downloaded (`HF_HUB_OFFLINE=1`, falling back to the network only to download it).
- pYIN in pieces: **dropped.** It's 0.05× real time on one performance core.

### H5. The Neural Engine

For the listening models, the reason is now quality and a free GPU, not speed:
- whisper.cpp with Core ML, to afford a better model (large-v3-turbo) for checking a take's words;
- HTDemucs on Core ML, if the GPU is busy with takes.

### H6. Training

Unchanged: one LoRA training step in MLX against PyTorch MPS before any port, with Kiro.

### Deferred by the measurement

- `yue-server --keep-loaded`: half a second a take.
- `yue-plan --batch`: plans take 3-4 s each.
- Smaller YuE2 weights: the render is limited by arithmetic, not by reading weights, so a smaller file wouldn't speed the 65% that matters.

## Not worth it now

- **YuE2 on the Neural Engine.** It's a 3-billion-parameter language model. The Neural Engine suits smaller fixed-shape networks, and the M4 Max's GPU has the bandwidth a model this size needs.
- **Porting yue2.cpp to MLX.** ggml already gives Metal, CUDA, Vulkan and the CPU from one code base.
- **Running everything at once inside a window.** The GPU still does one job at a time; the gain is the CPU and Neural Engine working beside it.

## Memory (64 GB)

- **LM Studio:** about 36 GB loaded (unloaded before a window).
- **YuE2:** 3B Q6_K is 2.9 GB, the VAE 0.5 GB, and each take in a batch has its own cache. Measured on a 47 s verse: 4.6 GB peak for one take, 7.2 GB for two in one run, 12.4 GB for four (about 2.6 GB more a take). Even nine would fit beside LM Studio's 36 GB. The page allows 4; the command line up to 9.
- **The CPU lane and the Neural Engine models:** a few GB.

## Cross-platform rules

- One place decides where work runs: `copyist/compute.py`. It covers CPU jobs at once (`COPYIST_JOBS`), the performance cores, and the PyTorch device a tool's own environment can use. A `copyist doctor` report of what's found and where each step will run comes next.
- Prefer runtimes with every backend:
  - ggml (yue2.cpp, whisper.cpp): Metal, CUDA, Vulkan, CPU;
  - ONNX Runtime: Core ML, CUDA, DirectML, CPU;
  - PyTorch for training: MPS, CUDA, CPU.
- Every accelerated path keeps a CPU fallback, and its tests run on the CPU.
- Every choice can be overridden with an environment variable (`COPYIST_YUE_DEVICE`, `COPYIST_DEMUCS_DEVICE`, `COPYIST_JOBS`).

## Steps

1. **Built and measured (21 October):**
   - `copyist/compute.py`;
   - band parts side by side;
   - Demucs on CUDA where its PyTorch has it;
   - `copyist produce --takes N` and the page's "Takes";
   - `scripts/hardware/bench.py`.
2. H1, measured (above).
3. H2, measured and built: draft takes at 12 steps, `copyist finish`, the page's Quality choice and "Finish this take"; Demucs offline once downloaded.
4. H3: the page's two lanes.
5. H4: band previews of candidates and styles in parallel; `copyist doctor`.
6. H5: whisper.cpp with Core ML for a better word check; HTDemucs on Core ML if the GPU stays busy.
7. H6: an MLX training-step measurement, with Kiro.
