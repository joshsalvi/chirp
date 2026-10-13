# Adapted from https://github.com/facebookresearch/denoiser under the MIT License
# Original Copyright (c) Facebook, Inc. and its affiliates. Also used by
# Earth Species Project's biodenoising (same license), which this is
# vendored from — see the parent package's __init__.py for why.
#
# Trimmed to just the one class demucs.py actually imports (LayerScale)
# out of upstream's much larger denoiser/transformer.py, which otherwise
# implements a full transformer stack Chirp's plain Demucs model doesn't use.

import torch
from torch import nn


class LayerScale(nn.Module):
    """Layer scale from [Touvron et al 2021] (https://arxiv.org/pdf/2103.17239.pdf).
    This rescales diagonaly residual outputs close to 0 initially, then learnt.
    """

    def __init__(self, channels: int, init: float = 0, channel_last: bool = False):
        """
        channel_last = False corresponds to (B, C, T) tensors
        channel_last = True corresponds to (T, B, C) tensors
        """
        super().__init__()
        self.channel_last = channel_last
        self.scale = nn.Parameter(torch.zeros(channels, requires_grad=True))
        self.scale.data[:] = init

    def forward(self, x):
        if self.channel_last:
            return self.scale * x
        else:
            return self.scale[:, None] * x
