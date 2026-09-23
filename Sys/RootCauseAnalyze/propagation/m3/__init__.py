"""M3: anchor-conditioned global backbone reconstruction.

Turns M1's local directional relation likelihoods into one globally consistent
propagation graph: a maximum-evidence backbone around the anchor, followed by
evidence-gated DAG augmentation.
"""

from .arborescence import (
    VIRTUAL_ROOT,
    ArborescenceForest,
    WeightedEdge,
    maximum_arborescence,
    maximum_arborescence_with_null_option,
)
from .decode import decode_backbone

__all__ = [
    "VIRTUAL_ROOT",
    "ArborescenceForest",
    "WeightedEdge",
    "decode_backbone",
    "maximum_arborescence",
    "maximum_arborescence_with_null_option",
]
