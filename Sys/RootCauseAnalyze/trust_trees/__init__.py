"""Rule-based trust trees for ranker-level RCA routing."""

__all__ = ["assess_topo_tree", "assess_temporal_tree", "route_with_trust_trees"]


def __getattr__(name: str):
    """Load public helpers lazily to keep policy/router imports acyclic."""
    if name == "assess_topo_tree":
        from .topo_tree import assess_topo_tree

        return assess_topo_tree
    if name == "assess_temporal_tree":
        from .temporal_tree import assess_temporal_tree

        return assess_temporal_tree
    if name == "route_with_trust_trees":
        from .router import route_with_trust_trees

        return route_with_trust_trees
    raise AttributeError(name)
