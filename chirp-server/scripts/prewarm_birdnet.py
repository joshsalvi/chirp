"""Pre-warm BirdNET at image build time so the first upload is instant."""
from birdnetlib.analyzer import Analyzer
a = Analyzer()
name = getattr(a, "model_name", "loaded")
print(f"BirdNET pre-warm OK — model: {name}")
