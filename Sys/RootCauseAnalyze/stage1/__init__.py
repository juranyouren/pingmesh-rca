"""Anchor (root) estimation for propagation reconstruction.

``fusion.rank_root_causes`` is the deterministic anchor prior used by
``propagation_pipeline``: topology/alarm PageRank combined with temporal
evidence. ``neural_model`` / ``neural_graph`` hold the graph-attention anchor
estimator (``q(a) = P(a is anchor | G_E)``); they are kept as the reusable
algorithm and are not currently driven by any runner in this repository.
"""

from .alarm_topology_ranker import score_topo, topo_details
from .fusion import rank_root_causes
from .temporal_ranker import score_temporal, temporal_details

__all__ = [
    "rank_root_causes",
    "score_temporal",
    "temporal_details",
    "score_topo",
    "topo_details",
]
