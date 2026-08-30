"""Machine-learning slot for ARES.

Models here are trained OFFLINE and loaded as frozen artifacts. At
inference they are pure functions (fixed weights -> deterministic output),
so they live inside the deterministic hot path without breaking
reproducibility. Nothing here calls the network at trade time.
"""
