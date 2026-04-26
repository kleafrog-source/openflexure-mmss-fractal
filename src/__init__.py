"""
UAGO-3C: Universal Adaptive Geometric Observer - Three-Cycle Core

This package provides functionality for analyzing geometric patterns in images and
generating symbolic representations of their underlying structure.
"""

__version__ = "0.1.0"

from .invariant_measurer import measure_invariants
from .symbolic_regressor import generate_formula_from_invariants
from .jsx_visualizer import generate_jsx_visualization
from .uago_core import UAGO3CEngine

__all__ = [
    'measure_invariants',
    'generate_formula_from_invariants',
    'generate_jsx_visualization',
    'UAGO3CEngine'
]