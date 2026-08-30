"""
RAAH Routing Package
====================

Centralized routing and kinematic movement subsystem.
"""

from .engine import RoutingEngine, RouterBase, RouteGeometry
from .local_approx import LocalApproxRouter

# Default global instance
routing_engine = RoutingEngine(router=LocalApproxRouter())

__all__ = [
    "RoutingEngine",
    "RouterBase",
    "RouteGeometry",
    "LocalApproxRouter",
    "routing_engine",
]
