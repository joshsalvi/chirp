# AI Features (Optional LLM Integrations)

Three optional features run on an LLM, each independently assignable to
a provider in Settings → Experimental → AI Features, off by default:

| Feature | Type | What it does |
|---|---|---|
| Daily Journal | Text | A short, personality-driven daily summary of what showed up |
| Bird Profile Summaries | Text | A presence summary on each species' profile page |
| Call Re-analysis (**AI Second Opinion** button, in the UI) | Vision | Shows the model a spectrogram image as a second opinion on an uncertain detection — also does a required second pass over the whole image for anything else visible (other bird calls BirdNET didn't flag, with its own species guess; other animal sounds like a chipmunk's chip or an insect chorus). The per-species verdict only ever covers detections shown above `min_confidence_display` — the same threshold the spectrogram overlay and detections list use — so it never discusses a species the recording's own detail page never displayed as a flagged detection. The image uses a mel-spaced, labeled frequency axis so low calls (owls, doves) are visible; each species line carries a frequency band measured from the audio, and recordings over 60 s are cropped to the 60 s stretch with the most detections. Each species line also carries measured facts: nothing above the background in its boxes, energy only in the wind/traffic rumble range (below 0.4 kHz, for species that call higher), faint (under 8 dB above background), whether the server's BirdNET pass agreed, and the eBird relative frequency for this month. When any of those count against the primary species, the note ends with an **Audio check for <species>:** paragraph saying so in plain sentences (e.g. "The call is faint, only 6 dB louder than the background."), and a Consistent verdict becomes Uncertain when the boxes hold nothing measurable or only rumble. Non-bird sounds are measured too: short loud broadband bursts (dog barks, other mammals, voices, knocks), with a note on any species whose boxes they fall in, and steady bands above 1.5 kHz (insect chorus, electrical whine, hiss); if the model's **Also visible** paragraph leaves either out, the measured description is added there. It runs in the background (the page polls until the note or an error appears); image requests time out after 120 s on hosted providers and 420 s on Ollama. Requests use temperature 0.2. Ollama requests use a 16k-token context (`CHIRP_OLLAMA_NUM_CTX`) and ask thinking models to answer directly (`think: false`; set `CHIRP_OLLAMA_THINK=1` to let them reason first, at several times the wait). Opening a recording page loads the Ollama model in the background (`POST /recordings/ai-warm`), and the model stays loaded for 30 min. The spectrogram goes as a JPEG, 1024 px wide for Ollama and 1344 px for hosted providers; Anthropic requests cache the instructions. |

Supported providers: Anthropic, OpenAI, Gemini, and Ollama — configured
independently per feature.

## Ollama's single-model constraint

Unlike the hosted providers, Ollama has one shared `base_url` + `model`
setting, not a separate model per feature — you pick a *provider* per
feature, but every feature assigned to "ollama" uses that same single
model. Since Call Re-analysis needs a vision-capable model and the other
two are text-only, this leaves two real strategies:

- **A. One model does everything** — pick a vision-capable model (they
  handle plain text fine too) and assign all three features to Ollama.
- **B. Split it** — assign Daily Journal + Bird Profile Summaries to
  Ollama with a fast text-only model, and leave Call Re-analysis on a
  hosted provider (Anthropic/OpenAI/Gemini). Local vision models are
  noticeably behind frontier hosted models on fine-grained visual
  judgment calls like "does this spectrogram support this species
  guess" — Strategy B trades a few cents per re-analysis for meaningfully
  better judgment on the one feature where a wrong answer is most
  misleading.

There's no wrong choice here — B is the more accuracy-conscious pick, A
is the fully self-hosted/zero-cost pick.

## Setting up Ollama

**1. Install** (bare-metal or Docker — if the rest of Chirp already runs
in Docker, Docker is the natural fit):

```bash
# Bare-metal (Linux):
curl -fsSL https://ollama.ai/install.sh | sh

# Or Docker:
docker run -d --gpus=all -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
```

**2. Give the container your GPU.** Docker doesn't expose a GPU to a
container by default, even with working host drivers — this is the
single most common reason Ollama silently runs on CPU with no error. On
Linux, install the NVIDIA Container Toolkit; on Unraid, the Nvidia-Driver plugin (Community Applications).
Then make sure the container requests the GPU. In
docker-compose:

```yaml
services:
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
volumes:
  ollama:
```

**3. Pull a model** (see the table below), then confirm it's on
the GPU:

```bash
ollama pull <model>
ollama ps          # PROCESSOR column should show 100% GPU, not CPU
nvidia-smi         # confirm an ollama process is using VRAM while generating
```

**4. Configure in Chirp** — Settings → Experimental → AI Features → set Ollama's base
URL (e.g. `http://192.168.1.X:11434` — use the host's LAN IP, not
`localhost`, if Ollama runs in a separate container from chirp-server)
and model name, then assign whichever features you want to it.

**Reaching Ollama over the internet:** Ollama has no sign-in, so don't
expose port 11434 directly. Put a proxy in front that requires a key
(e.g. Caddy matching `Authorization: Bearer <key>`), and enter that key
in the optional API key field. Chirp sends it on every Ollama request;
it's masked like the other keys. Leave it blank for a LAN-only server.

## Which Ollama model should you use?

Model names, sizes, and exact VRAM figures shift often — always
double-check current tags with `ollama pull <name>` (it errors clearly
if the tag doesn't exist) or at ollama.com/library before committing.
Figures below are Q4 quantization estimates — treat as a floor rather
than exact:

| Model | Type | Approx. VRAM | Pros | Cons |
|---|---|---|---|---|
| `gemma4:e2b` | Vision + text | ~2–4 GB | Runs on almost anything; multimodal, not a bolted-on vision head | Weakest reasoning of the family — fine for short summaries, shakier on nuanced spectrogram judgment |
| `gemma4:e4b` | Vision + text | ~6–8 GB | Best quality-per-GB tradeoff for a modest GPU; still fast | Meaningfully behind the larger tiers on fine visual detail |
| `gemma4:26b` (MoE, ~4B active) | Vision + text | ~16–20 GB | Strong quality while staying fast (MoE only activates a fraction of params per token) | Needs a real GPU; larger download |
| `gemma4:31b` | Vision + text | ~20–24 GB+ | Best quality in the family; dense model, no MoE inconsistency | Needs a high-end GPU; slower per-token than the MoE tier |
| `llama3.2-vision:11b` | Vision + text | ~8–10 GB | Mature, widely tested, stable in Ollama | Vision quality trails Gemma 4 at a comparable size |
| `llama3.2-vision:90b` | Vision + text | ~48 GB+ | High quality | Needs serious multi-GPU hardware — unrealistic for most home setups |
| `llama3.3:8b` | Text only | ~6–8 GB | Fast, well-rounded, best all-around text choice for Strategy B | No vision — can't be used for Call Re-analysis at all |
| Qwen2.5-VL (7B) | Vision + text | ~6–8 GB | Strong document/chart understanding | Newer Qwen 3.5/3.6 vision variants are currently broken in Ollama specifically (the text half loads fine, but the vision sidecar isn't wired up) — stick to Qwen2.5-VL or Qwen3-VL, not 3.5/3.6 |

**Recommendation:** given working GPU passthrough, `gemma4:e4b`
(Strategy A, one model for everything) is the best starting point —
multimodal, fast, and modest on VRAM. If Call Re-analysis's
judgment calls matter and there's VRAM to spare, `gemma4:26b` is a
meaningful step up for that feature specifically. To keep Call
Re-analysis on a hosted provider and use Ollama only for the two text
features (Strategy B), `llama3.3:8b` is the better dedicated pick — it
won't be doing double duty as a vision model it doesn't need to be.
