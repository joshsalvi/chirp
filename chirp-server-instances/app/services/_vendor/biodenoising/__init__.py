"""
Chirp — vendored inference-only subset of Earth Species Project's
`biodenoising` (github.com/earthspecies/biodenoising, MIT license).

WHY VENDORED RATHER THAN A PYPI DEPENDENCY
--------------------------------------------------------------------------
The upstream `biodenoising` PyPI package pulls in a training/research
dependency stack (asteroid, openunmix, scikit-fuzzy, prosemble, an
omegaconf==1.4.1 pin) entirely unused for running a single pretrained
checkpoint's forward pass — the only thing Chirp needs. Only the two
files required for that are kept here, both copied verbatim from
upstream (denoiser/demucs.py, denoiser/resample.py — see each file's own
header for the original license/attribution), plus a small
denoiser/utils.py reimplementing the two small helper functions actually
used (capture_init, load_model_state_dict).

WHY THIS EXACT PACKAGE NAME/PATH IS NOT ARBITRARY
--------------------------------------------------------------------------
The pretrained checkpoint downloaded from Earth Species Project's own
hosting (see ai_enhance.py's BIO_DNS_48_URL) is a pickled object graph
that references classes by their ORIGINAL module path at unpickle time —
confirmed directly via `pickletools.dis()` against the real downloaded
checkpoint, which shows `GLOBAL 'biodenoising.denoiser.demucs Demucs'`.
A differently-named or differently-nested local module would fail to
load the real checkpoint with a ModuleNotFoundError. This is why
ai_enhance.py inserts this directory's PARENT onto sys.path rather than
importing this as a submodule of app.services — `biodenoising` has to
resolve as an actual top-level module, not app.services.<something>.

Not a general-purpose package — nothing outside ai_enhance.py should
import from this.
"""
