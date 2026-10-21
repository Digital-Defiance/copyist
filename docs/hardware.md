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

## Where the time goes now

Measured on the M4 Max unless noted (TASKS, docs/melody-writing.md, docs/singing.md, docs/transcribing.md):

| Step | Runs on | Time |
|---|---|---|
| A melody plan (`yue-plan`) | GPU | 7-8 s a candidate, one run each, the model loaded each time |
| A YuE2 take (`yue-synth`) | GPU | About real time (a 47 s verse in 45 s), one take a run |
| A take per style (`copyist gallery --takes`) | GPU | About 45 s a style |
| SoulX singing | GPU | 0.5× real time, plus 8 s loading a call |
| Separating the vocal (Demucs) | GPU (MPS) on a Mac; the CPU elsewhere, even with an NVIDIA GPU (fixed: see H5) | Under 10 s a song, with the open transcriber |
| Hearing the words (faster-whisper base.en) | CPU, int8 | Not measured |
| Pitch tracking (librosa pYIN) | One CPU core | 0.34× real time on a cloud core: about a minute for a 3-minute song |
| The band (sfizz) | CPU, one part after another (fixed: H4) | About 2 s a part |
| Engraving (music21, Verovio) | CPU | Seconds |
| The page | One job at a time, of any kind | A band preview waits behind a take |

`scripts/hardware/bench.py` measures all of these in one unattended run, about 10-15 minutes, including the YuE2 batch levers below (H1).

## The levers, in order

### H1. Measure first

One GPU window runs `caffeinate -i python scripts/hardware/bench.py`. It times one take against 2 and 4 takes in one run, 4 variations of one take, the planner, Demucs on the GPU and the CPU, Whisper, pYIN, and the band one part at a time against side by side. It also checks that take 2 of a batch is the same as that take rendered alone. Results go in `out/hardware/bench-<time>.md`; the numbers go in this file and TASKS. No speed claim below counts until it's measured there.

### H2. YuE2: several takes in one run, and staying loaded

yue2.cpp already has the levers; Copyist didn't use them.

- **Several takes in one run** (`lm_batch_size`). yue2.cpp draws song *i* of a batch with `lm_seed + i`, the batch decoding in lockstep. Writing a take is limited by memory bandwidth, not arithmetic, so a batch of 4 should cost far less than 4 runs (to measure). **Built:** `copyist produce --takes N` and the page's "Takes" choice (1-4). Each take lands in its own folder with its own request and yue2.cpp's replay request. If a batch fails, each take is rendered alone with the same seeds.
- **Variations of one take** (`synth_batch_size`, up to 9). The same performance under different noise, from the half of the work that's cheap. For "the same take, a little different".
- **One plan run for several candidates.** `yue-plan` makes one plan a run, but the generator underneath takes a batch (`yue2_generate` with several prefixes). A small patch (`yue-plan --batch N`, offered upstream to ServeurpersoCom/yue2.cpp) would let `copyist write` plan four candidates in one run.
- **Staying loaded** (`yue-server --keep-loaded`). One process holds the model between requests instead of loading it for every plan and take. The page's GPU work would go through it. Its job queue is FIFO with cancel, which fits "one GPU job at a time".
- **Smaller weights.** Copyist uses `YuE2-3B-Q6_K`; yue2.cpp's `quantize` makes Q5_K and Q4_K. Smaller is faster when bandwidth-bound, but quality has to be checked automatically: the melody check (`copyist follow`) and the word check (`hear.py`) on the same seeds. Only if H1 shows the GPU is the bottleneck.
- All of this is the same on Linux and Windows: yue2.cpp builds for CUDA, Vulkan and SYCL (`buildcuda.sh`, `buildvulkan.sh`).

### H3. The page: a GPU lane and a CPU lane

The page runs one job at a time, whatever it is. Split it in two lanes:
- **GPU:** takes, plans, SoulX, training; one at a time, as now.
- **CPU:** engraving, band previews, the rules writer, checks, import, refit; several at once, up to the performance cores.

A band preview or a new lead sheet no longer waits behind a three-minute take.

### H4. The CPU, in parallel

Cross-platform for free: it's Python, processes and threads.
- **Band parts side by side. Built:** each part is its own sfizz process, so they play at once (`COPYIST_JOBS` caps it; the default is the performance cores).
- **Band previews of several candidates or styles at once** (`copyist write`, `copyist gallery`): one process each.
- **pYIN in pieces:** split the audio into overlapping pieces, track each on its own core, join them. About ten times faster on the Mac. Used by `copyist follow`, the voice prompt and (Kiro's call) the open transcriber.
- **Checks after a batch of takes**, one per take.

### H5. The Neural Engine, for the listening models

The listening models are small enough for the Neural Engine. There they run beside a YuE2 take without slowing it, and without a window.

- **Words:** whisper.cpp instead of faster-whisper. It's the same ggml family as yue2.cpp. On a Mac its encoder runs on the Neural Engine through Core ML, more than 3× faster than the CPU by its README, and the rest on Metal. Elsewhere it runs on CUDA or Vulkan. With the speed, a better model (large-v3-turbo instead of base.en) hears more of a sung take's words.
- **Separation:** HTDemucs converted to Core ML (schism-audio, MIT, as Demucs is). The fp16 model can run on the Neural Engine. It needs Copyist's own STFT before and after, checked against its test vectors. Elsewhere Demucs stays PyTorch on CUDA or the CPU. **Fixed now:** Copyist asks Demucs's own PyTorch whether it can use CUDA, instead of always choosing the CPU off a Mac.
- **Pitch and notes:** Basic Pitch already runs through Core ML in the open transcriber. Any "ear" the transcriber picks (TASKS §7) should be exported to ONNX, then run on the Neural Engine through ONNX Runtime's Core ML provider and on CUDA or DirectML elsewhere.

### H6. Training

LoRA training (`scripts/yue-lora/train.py`) and the transcriber's training run on PyTorch with MPS. MLX is Apple's own framework, usually faster than MPS on Apple silicon, and it now also runs on Linux with CUDA (not on Windows). Measure one training step both ways before porting anything. The transcriber's training is Kiro's (TASKS §7).

## Not worth it now

- **YuE2 on the Neural Engine.** It's a 3-billion-parameter language model. The Neural Engine suits smaller fixed-shape networks, and the M4 Max's GPU has the bandwidth a model this size needs.
- **Porting yue2.cpp to MLX.** ggml already gives Metal, CUDA, Vulkan and the CPU from one code base.
- **Running everything at once inside a window.** The GPU still does one job at a time; the gain is the CPU and Neural Engine working beside it.

## Memory (64 GB)

- **LM Studio:** about 36 GB loaded (unloaded before a window).
- **YuE2:** 3B Q6_K is 2.9 GB, the VAE 0.5 GB, and each take in a batch has its own cache. yue2.cpp measured a 65 s song's peak at 3.8 GB (`--max-seq 8192`) to 5.8 GB (full context) above idle, so 4 takes of a verse should fit in about 12-20 GB. The page allows 4; the command line up to 9.
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

1. **Built (21 October):**
   - `copyist/compute.py`;
   - band parts side by side;
   - Demucs on CUDA where its PyTorch has it;
   - `copyist produce --takes N` and the page's "Takes";
   - `scripts/hardware/bench.py`.
2. H1: run the benchmark in one window (an agent on the Mac); record the numbers here and in TASKS.
3. H3: the page's two lanes.
4. H4: pYIN in pieces; band previews of candidates and styles in parallel; `copyist doctor`.
5. H2: `yue-plan --batch` (upstream patch), then `yue-server --keep-loaded` behind the GPU lane, if H1 shows loading costs.
6. H5: whisper.cpp with Core ML; then HTDemucs on Core ML.
7. H6: an MLX training-step measurement, with Kiro.
