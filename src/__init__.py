"""
OpenFlexure MMSS Fractal Integration

This package provides functionality for analyzing fractal patterns in microscope images
and controlling OpenFlexure microscopes safely.
"""

__version__ = "0.1.0"

from .invariant_measurer import measure_invariants

__all__ = [
    'measure_invariants',
]