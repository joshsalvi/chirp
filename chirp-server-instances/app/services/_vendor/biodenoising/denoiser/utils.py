# Adapted from https://github.com/facebookresearch/denoiser under the MIT License
# Original Copyright (c) Facebook, Inc. and its affiliates. Also used by
# Earth Species Project's biodenoising (same license), which this is
# vendored from — see the parent package's __init__.py for why.
#
# Trimmed to just the two functions Chirp's ai_enhance.py actually calls
# (capture_init, load_model_state_dict) out of upstream's denoiser/utils.py,
# which otherwise pulls in a much larger set of training/eval-only helpers.

import functools


def capture_init(init):
    """Decorate __init__ with this, and you can then recover the *args and
    **kwargs passed to it in self._init_args_kwargs. demucs.py's Demucs
    class is decorated with this upstream; kept for compatibility even
    though Chirp's own model construction always passes explicit kwargs."""
    @functools.wraps(init)
    def __init__(self, *args, **kwargs):
        self._init_args_kwargs = (args, kwargs)
        init(self, *args, **kwargs)
    return __init__


def load_model_state_dict(model, state_dict):
    """Load a state dict into `model`, silently skipping any key whose
    tensor shape doesn't match the model's own — the same tolerant
    behavior upstream uses, since a checkpoint can carry a few extra/
    stale keys (e.g. from a training-time EMA wrapper) that aren't part
    of the plain inference-time module."""
    current_model_dict = model.state_dict()
    new_state_dict = {
        k: v for k, v in state_dict.items()
        if k in current_model_dict and list(v.size()) == list(current_model_dict[k].size())
    }
    model.load_state_dict(new_state_dict, strict=False)
    return model
