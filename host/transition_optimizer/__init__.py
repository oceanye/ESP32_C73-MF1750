"""Measured-profile transition-aware six-colour optimization.

The package is deliberately host-only.  It never talks to a panel and never
turns an optimizer result into a visible-refresh authorization.
"""

from .optimizer import (
    MissingProfileMode,
    TransitionMetricWeights,
    TransitionInputBinding,
    TransitionOptimizationError,
    TransitionOptimizationOptions,
    TransitionOptimizationResult,
    UnknownCurrentMode,
    build_pareto_report,
    optimize_transition_aware,
    validate_pareto_report,
    validate_transition_optimization_report,
)

__all__ = [
    "MissingProfileMode",
    "TransitionMetricWeights",
    "TransitionInputBinding",
    "TransitionOptimizationError",
    "TransitionOptimizationOptions",
    "TransitionOptimizationResult",
    "UnknownCurrentMode",
    "build_pareto_report",
    "optimize_transition_aware",
    "validate_pareto_report",
    "validate_transition_optimization_report",
]
