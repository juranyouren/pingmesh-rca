from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig, normalize_config, root_devices


def _path_score(edges: Sequence[Mapping[str, Any]], target_prize: float) -> float:
    if not edges:
        return 1.0 if target_prize > 0 else 0.0
    scores = [float(edge.get("support_score", 0.0) or 0.0) for edge in edges]
    grounded = sum(1 for edge in edges if edge.get("evidence_ids")) / len(edges)
    contradiction = max(
        float(edge.get("features", {}).get("contradiction", 0.0) or 0.0)
        for edge in edges
    )
    complexity = max(0, len(edges) - 1) * 0.02
    score = (
        0.40 * min(scores)
        + 0.35 * (sum(scores) / len(scores))
        + 0.15 * target_prize
        + 0.10 * grounded
        - complexity
        - 0.20 * contradiction
    )
    return round(max(0.0, min(1.0, score)), 6)


def _search_target_paths(
    roots: Sequence[str],
    target: Mapping[str, Any],
    scored_edges: Sequence[Mapping[str, Any]],
    config: PropagationConfig,
) -> List[Dict[str, Any]]:
    target_id = str(target.get("device_id", "") or "")
    if not target_id:
        return []
    if target_id in set(roots):
        return [
            {
                "target": target_id,
                "devices": [target_id],
                "edges": [],
                "score": 1.0,
                "target_prize": float(target.get("target_prize", 0.0) or 0.0),
            }
        ]

    outgoing: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in scored_edges:
        edge = dict(raw)
        if edge.get("support_level") == "rejected":
            continue
        if float(edge.get("support_score", 0.0) or 0.0) < config.min_edge_support:
            continue
        outgoing[str(edge.get("from", ""))].append(edge)
    for rows in outgoing.values():
        rows.sort(key=lambda item: (-float(item.get("support_score", 0.0)), item.get("to", "")))

    beam: List[Tuple[List[str], List[Dict[str, Any]]]] = [([root], []) for root in sorted(set(roots))]
    completed: List[Dict[str, Any]] = []
    for _depth in range(config.max_path_depth):
        expanded: List[Tuple[List[str], List[Dict[str, Any]]]] = []
        for devices, edges in beam:
            current = devices[-1]
            for edge in outgoing.get(current, []):
                neighbor = str(edge.get("to", "") or "")
                if not neighbor or neighbor in devices:
                    continue
                next_devices = [*devices, neighbor]
                next_edges = [*edges, edge]
                if neighbor == target_id:
                    completed.append(
                        {
                            "target": target_id,
                            "devices": next_devices,
                            "edges": next_edges,
                            "score": _path_score(
                                next_edges,
                                float(target.get("target_prize", 0.0) or 0.0),
                            ),
                            "target_prize": float(target.get("target_prize", 0.0) or 0.0),
                        }
                    )
                else:
                    expanded.append((next_devices, next_edges))
        if not expanded:
            break
        expanded.sort(
            key=lambda state: (
                -_path_score(state[1], 0.0),
                len(state[0]),
                tuple(state[0]),
            )
        )
        beam = expanded[: config.beam_width]

    unique: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for path in completed:
        key = tuple(path["devices"])
        current = unique.get(key)
        if current is None or path["score"] > current["score"]:
            unique[key] = path
    return sorted(
        unique.values(),
        key=lambda item: (-float(item["score"]), len(item["devices"]), tuple(item["devices"])),
    )[: config.top_k_paths_per_target]


def _would_create_cycle(adjacency: Mapping[str, Set[str]], source: str, target: str) -> bool:
    queue = deque([target])
    seen = {target}
    while queue:
        node = queue.popleft()
        if node == source:
            return True
        for neighbor in adjacency.get(node, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def _node_episode_data(
    device_id: str,
    episode_by_device: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Tuple[List[int] | None, List[str], str]:
    episodes = list(episode_by_device.get(device_id, []))
    intervals = [
        item.get("onset_interval_ms")
        for item in episodes
        if isinstance(item.get("onset_interval_ms"), list)
        and len(item.get("onset_interval_ms")) == 2
        and item.get("lifecycle") != "clear"
    ]
    onset = list(min(intervals, key=lambda value: (value[0], value[1]))) if intervals else None
    evidence_ids = sorted(
        {str(item.get("evidence_id")) for item in episodes if item.get("evidence_id")}
    )
    relevance = max(
        (float(item.get("incident_relevance", 0.0) or 0.0) for item in episodes),
        default=0.0,
    )
    support_level = "strong" if relevance >= 0.8 else "moderate" if relevance >= 0.55 else "weak"
    return onset, evidence_ids, support_level


def _build_dag(
    selected_paths: Sequence[Mapping[str, Any]],
    root_hypothesis: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]],
    episode_by_device: Mapping[str, Sequence[Mapping[str, Any]]],
    config: PropagationConfig,
) -> Dict[str, Any]:
    roots = root_devices(root_hypothesis)
    root_set = set(roots)
    target_set = {str(item.get("device_id")) for item in targets if item.get("device_id")}
    selected_edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    selected_nodes: Set[str] = set(roots)
    used_alternative_groups: Set[str] = set()
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    covered_targets: Set[str] = set()
    accepted_paths: List[Mapping[str, Any]] = []

    for path in sorted(
        selected_paths,
        key=lambda item: (-float(item.get("score", 0.0)), str(item.get("target", ""))),
    ):
        path_edges = [dict(edge) for edge in path.get("edges", [])]
        can_add = True
        local_groups: Set[str] = set()
        local_adjacency = {node: set(values) for node, values in adjacency.items()}
        for edge in path_edges:
            source = str(edge.get("from", "") or "")
            target = str(edge.get("to", "") or "")
            group = str(edge.get("alternative_group", "") or "")
            if group and group in used_alternative_groups and (source, target) not in selected_edges:
                can_add = False
                break
            if _would_create_cycle(local_adjacency, source, target):
                can_add = False
                break
            local_adjacency.setdefault(source, set()).add(target)
            if group:
                local_groups.add(group)
        if not can_add:
            continue
        adjacency = defaultdict(set, local_adjacency)
        used_alternative_groups.update(local_groups)
        for edge in path_edges:
            key = (str(edge.get("from", "")), str(edge.get("to", "")))
            selected_edges[key] = edge
            selected_nodes.update(key)
        selected_nodes.update(path.get("devices", []))
        target_id = str(path.get("target", "") or "")
        if target_id:
            covered_targets.add(target_id)
        accepted_paths.append(path)

    root_scope = str(root_hypothesis.get("root_scope", "device"))
    node_rows = []
    for device_id in sorted(selected_nodes):
        if device_id in root_set:
            role = "root_endpoint" if root_scope == "inter_device_link" else "root"
        elif device_id in target_set:
            role = "affected"
        else:
            role = "propagation"
        onset, evidence_ids, support_level = _node_episode_data(device_id, episode_by_device)
        node_rows.append(
            {
                "device_id": device_id,
                "role": role,
                "onset_interval_ms": onset,
                "support_level": support_level,
                "evidence_ids": evidence_ids,
            }
        )

    edge_rows = []
    for index, key in enumerate(sorted(selected_edges), 1):
        edge = dict(selected_edges[key])
        edge["edge_id"] = f"P{index}"
        edge.pop("root_distances", None)
        edge_rows.append(edge)

    coverage = len(covered_targets) / len(target_set) if target_set else 0.0
    meaningful_paths = [path for path in accepted_paths if path.get("edges")]
    accepted_scores = [float(path.get("score", 0.0) or 0.0) for path in meaningful_paths]
    graph_score = (sum(accepted_scores) / len(accepted_scores)) if accepted_scores else 0.0
    supported_edge_count = sum(
        1 for edge in edge_rows if edge.get("support_level") in {"moderate", "strong"}
    )
    supported_edge_ratio = supported_edge_count / len(edge_rows) if edge_rows else 0.0
    grounded_edge_ratio = (
        sum(1 for edge in edge_rows if edge.get("evidence_ids")) / len(edge_rows)
        if edge_rows
        else 0.0
    )
    contradiction_score = max(
        (
            float(edge.get("features", {}).get("contradiction", 0.0) or 0.0)
            for edge in edge_rows
        ),
        default=0.0,
    )
    weak_edge_ratio = (
        sum(1 for edge in edge_rows if edge.get("support_level") == "weak") / len(edge_rows)
        if edge_rows
        else 0.0
    )
    root_consistency_score = (
        sum(
            float(edge.get("features", {}).get("root_distance_consistency", 0.0) or 0.0)
            for edge in edge_rows
        )
        / len(edge_rows)
        if edge_rows
        else 0.0
    )
    return {
        "root_hypothesis": dict(root_hypothesis),
        "nodes": node_rows,
        "edges": edge_rows,
        "covered_targets": sorted(covered_targets),
        "target_coverage": round(coverage, 6),
        "graph_score": round(graph_score, 6),
        # M2 ranks roots outside the path solver. This field is retained only
        # for deterministic ordering of alternative paths for the same root.
        "hypothesis_score": round(graph_score, 6),
        "diagnostics": {
            "selected_edge_count": len(edge_rows),
            "supported_edge_ratio": round(supported_edge_ratio, 6),
            "grounded_edge_ratio": round(grounded_edge_ratio, 6),
            "weak_edge_ratio": round(weak_edge_ratio, 6),
            "contradiction_score": round(contradiction_score, 6),
            "root_distance_consistency": round(root_consistency_score, 6),
            "uncovered_targets": sorted(target_set - covered_targets),
        },
    }


def solve_propagation_dags(
    candidate_graph: Mapping[str, Any],
    root_hypothesis: Mapping[str, Any],
    scored_edges: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
    *,
    config: PropagationConfig | Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = normalize_config(config)
    roots = root_devices(root_hypothesis)
    targets = [dict(item) for item in candidate_graph.get("targets", []) if isinstance(item, Mapping)]
    episode_by_device: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in episodes:
        if item.get("device_id"):
            episode_by_device[str(item["device_id"])].append(dict(item))

    paths_by_target: Dict[str, List[Dict[str, Any]]] = {}
    for target in targets:
        target_id = str(target.get("device_id", "") or "")
        paths_by_target[target_id] = _search_target_paths(roots, target, scored_edges, cfg)

    base_paths = [paths[0] for _target, paths in sorted(paths_by_target.items()) if paths]
    main = _build_dag(base_paths, root_hypothesis, targets, episode_by_device, cfg)

    ranked_chains = []
    all_paths = [path for values in paths_by_target.values() for path in values]
    for index, path in enumerate(
        sorted(
            all_paths,
            key=lambda item: (-float(item.get("score", 0.0)), tuple(item.get("devices", []))),
        )[: cfg.max_ranked_chains],
        1,
    ):
        ranked_chains.append(
            {
                "rank": index,
                "target": path.get("target"),
                "devices": list(path.get("devices", [])),
                "score": path.get("score", 0.0),
                "covered_targets": [path.get("target")] if path.get("target") else [],
            }
        )
    main["ranked_chains"] = ranked_chains

    alternatives: List[Dict[str, Any]] = []
    seen_edge_sets = {
        tuple(sorted((edge["from"], edge["to"]) for edge in main.get("edges", [])))
    }
    for target_id, paths in sorted(paths_by_target.items()):
        for replacement in paths[1:]:
            choices = []
            for other_target, other_paths in sorted(paths_by_target.items()):
                if not other_paths:
                    continue
                choices.append(replacement if other_target == target_id else other_paths[0])
            candidate = _build_dag(choices, root_hypothesis, targets, episode_by_device, cfg)
            edge_set = tuple(sorted((edge["from"], edge["to"]) for edge in candidate.get("edges", [])))
            if edge_set in seen_edge_sets:
                continue
            seen_edge_sets.add(edge_set)
            alternatives.append(candidate)
    alternatives.sort(
        key=lambda item: (-float(item.get("hypothesis_score", 0.0)), len(item.get("edges", [])))
    )
    main["alternative_hypotheses"] = alternatives[: cfg.max_alternative_hypotheses]
    main["diagnostics"] = {
        **dict(main.get("diagnostics", {})),
        "root_count": len(roots),
        "target_count": len(targets),
        "reachable_target_count": sum(1 for paths in paths_by_target.values() if paths),
        "path_candidate_count": len(all_paths),
    }
    return main


def is_dag(edges: Iterable[Mapping[str, Any]]) -> bool:
    adjacency: Dict[str, Set[str]] = defaultdict(set)
    indegree: Dict[str, int] = defaultdict(int)
    nodes: Set[str] = set()
    for edge in edges:
        source = str(edge.get("from", "") or "")
        target = str(edge.get("to", "") or "")
        if not source or not target or source == target:
            return False
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1
        nodes.update((source, target))
        indegree.setdefault(source, indegree.get(source, 0))
    queue = deque(sorted(node for node in nodes if indegree[node] == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in sorted(adjacency.get(node, set())):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    return visited == len(nodes)
