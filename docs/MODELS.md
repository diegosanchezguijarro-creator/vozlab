# Models & performance

VozLab uses two models: one for speech-to-text (Whisper, inside the server
container) and one for text cleanup (any Ollama model).

## Speech recognition — Whisper

| Model | Size on disk | VRAM (int8) | Languages | Notes |
|---|---|---|---|---|
| `tiny` | 75 MB | ~0.3 GB | multilingual | fastest, noticeably worse |
| `base` | 145 MB | ~0.4 GB | multilingual | okay for short commands |
| `small` | **490 MB** | **~0.5 GB** | **multilingual** | **default** — good balance |
| `small.en` | 490 MB | ~0.5 GB | English only | more accurate than `small` for English, same speed |
| `medium` | 1.5 GB | ~1.4 GB | multilingual | clearly better; needs ~2 GB free VRAM |
| `large-v3` | 3.1 GB | ~3 GB | multilingual | best; needs a 8 GB+ card alone |

Rule of thumb: **English-only dictation → `small.en`; several languages →
`small`; accuracy over speed → `medium`.**

Change it in `server/data/config.json`:

```json
{ "whisper_model": "medium", "language": "auto" }
```

…or with an environment variable: `VOZLAB_WHISPER_MODEL=medium`.

Notes:

- `int8_float16` quantisation (the default on GPU) costs almost nothing in
  accuracy and halves memory.
- A 6–8 GB GPU comfortably runs `small` or `medium` **plus** a 7B cleanup model.
- Whisper models are MIT-licensed and downloaded from Hugging Face on first use.

## Text cleanup — Ollama models

| Model | Download | VRAM | Licence | Notes |
|---|---|---|---|---|
| `qwen2.5:3b-instruct` | ~2 GB | ~2.5 GB | Apache-2.0 | fastest; good on CPU |
| `qwen2.5:7b-instruct` | **~4.7 GB** | **~4.7 GB** | **Apache-2.0** | **default** — best balance, good Spanish punctuation |
| `llama3.1:8b` | ~4.9 GB | ~5.3 GB | Meta Llama licence | similar quality, heavier, non-Apache licence |
| `gemma2:9b` | ~5.4 GB | ~6 GB | Gemma licence | good, needs more VRAM |

```bash
docker exec vozlab-ollama ollama pull qwen2.5:3b-instruct     # or any model
# then set "cleanup_model": "qwen2.5:3b-instruct" in server/data/config.json
```

Set `"cleanup": false` to skip the LLM entirely: raw transcripts, ~0.2 s faster,
filler words kept.

### Benchmarking your own setup

```bash
python server/tools/benchmark_cleanup.py qwen2.5:7b-instruct llama3.1:8b
```

It unloads models first (two 7–8B models cannot share an 8 GB card), verifies the
model actually landed on the GPU, and scores each model against real dictation
cases — filler removal, question-vs-answer, Spanish accents, numeric formatting.
Sample output from the reference machine (RTX 4060, 8 GB):

```
qwen2.5:7b-instruct          8/8  avg 0.25s  (GPU)
llama3.1:8b                  8/8  avg 0.25s  (GPU)
```

## Measured end-to-end latency

~6 seconds of speech, default models (`small` + `qwen2.5:7b-instruct`):

| Hardware | Whisper | Cleanup | Total |
|---|---|---|---|
| RTX 4060 8 GB | 0.2–0.6 s | 0.25 s | **~0.5–0.9 s** |
| RTX 3060 12 GB | 0.3–0.7 s | 0.3 s | ~0.6–1.0 s |
| GTX 1650 4 GB (`small.en`) | 0.6–1.2 s | 0.4 s | ~1.0–1.6 s |
| Ryzen 5 5600, CPU only | 1.5–4 s | 3–8 s | ~5–12 s |
| Raspberry Pi 5, CPU only | 8–20 s | — (`cleanup: false`) | ~8–20 s |

CPU timings improve a lot by switching to `small.en` + `qwen2.5:3b-instruct`, or
by disabling cleanup.

## Memory footprint at runtime

Reference machine (RTX 4060): `small` + `qwen2.5:7b-instruct` = **5.1 GB VRAM**
of 8.2 GB, leaving room for a browser. System RAM: the server container idles
around 700 MB; the client around 60 MB.
