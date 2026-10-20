"""Shared STIX math configuration. Semantic colors are applied by the registry."""
import matplotlib
matplotlib.rcParams.update({'mathtext.fontset': 'stix', 'mathtext.default': 'it'})
def normalize(text): return text
def color_feedback(image, text, size, raster_scale=1.0): return image
