# Compile a BirdNET EdgeTPU model

> **⚠️ Confirmed broken as of 2026-07-03 — read this before running.**
> A real compile attempt against the official INT8 model fails with:
> `ERROR: Attempting to use a delegate that only supports static-sized
> tensors with a graph that has dynamic-sized tensors. Compilation failed.`
> This is a genuine, structural property of BirdNET's own INT8 export —
> the same "dynamic-sized tensors" warning shows up even in BirdNET-
> Analyzer's own official CLI tooling (confirmed via their GitHub issue
> tracker), so it isn't something wrong with this script or how the
> compile is invoked, and it isn't fixable by changing compiler flags or
> retrying. It would need BirdNET-Analyzer to re-export the model with
> fully static tensor shapes from their original training checkpoint —
> outside what's achievable by post-processing the public `.tflite` file.
>
> This tool is kept because model exports do change over time, and this
> exact failure could be resolved upstream someday with zero changes
> needed here — but don't expect a successful compile today. If you just
> want Coral acceleration working, the realistic options right now are
> staying on the CPU backend (already reliable) or checking BirdNET-
> Analyzer's GitHub Discussions for a community-published pre-built
> EdgeTPU model. Full context: `chirp-device/install-coral.sh`'s own
> Step 3 output.

Run this on your Mac or the Unraid server (or any machine with Docker) — **not** on the Pi. The Edge TPU compiler only runs on x86_64 Linux; the Pi's ARM64 architecture isn't supported by Google's compiler (dropped at v2.1+).

## Requirements

- Docker Desktop (Mac) or Docker Engine (Linux) — that's it. Everything else (curl, unzip) is already on macOS/most Linux by default.
- ~200MB free disk space (download + extracted model + compiled output)
- Internet access to zenodo.org and packages.cloud.google.com

## Usage

```bash
cd chirp-device/tools/compile-edgetpu-model
./compile.sh
```

That's it — one command. It downloads the official BirdNET V2.4 INT8 model from Cornell's Zenodo record, builds a small Docker image with Google's real `edgetpu_compiler`, compiles the model, and validates the output.

**On Apple Silicon Macs**, Docker will transparently emulate x86_64 (QEMU) since the compiler has no ARM64 build — this is normal and expected, just slower than native. A one-time model compile like this still only takes a minute or two.

## Output

```
output/BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite
```

(The "FP32" in that filename is just chirp-device's existing expected path — harmless leftover naming, not a description of this file's actual quantization, which is INT8 as required by the Edge TPU hardware.)

## Next step

Copy the output file to the Pi and set the backend — no restart needed, chirp-device hot-swaps it in automatically:

```bash
scp output/BirdNET_GLOBAL_6K_V2.4_Model_FP32_edgetpu.tflite \
    joshsalvi@<pi-ip>:~/chirp-device/models/coral/

# then set backend: "coral" in config.yaml, or toggle it in the Devices UI
```

## If something goes wrong

- **"delegate that only supports static-sized tensors" / "Compilation failed"** — this is the confirmed, current, expected outcome (see the warning at the top of this file). Not a bug in this script, not fixable by retrying or changing flags. Use the CPU backend or check BirdNET-Analyzer's GitHub Discussions instead.
- **"No .tflite file found inside the zip"** — Zenodo may have restructured the archive since this was written. Check `work/extracted/` manually.
- **Compilation fails for a different reason** (not the dynamic-tensors error above, and not just "Mapped to the CPU" warnings, which are normal/expected for some ops) — check the compiler's own error output; it's usually specific about which operation it doesn't support.
- **Checksum mismatch warning** — Zenodo's file may have been updated since this was written, or the download was corrupted. The script continues either way since a checksum mismatch alone isn't necessarily fatal, but worth a second look.
