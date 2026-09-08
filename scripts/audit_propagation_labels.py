"""Audit propagation-label states and the root-distance direction assumption."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, deque
from typing import Any, Dict, Mapping

from Sys.RootCauseAnalyze.propagation.topology_context import (
    load_topology_context,
    physical_adjacency,
)
from Sys.RootCauseAnalyze.stage1.neural_graph import load_training_label
from Sys.utils.case_utils import load_case_info, load_case_nodes
from Sys.utils.io_utils import load_json


def _distances(adjacency: Mapping[str, set[str]], roots: list[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    queue = deque()
    for root in roots:
        if root in adjacency and root not in result:
            result[root] = 0
            queue.append(root)
    while queue:
        node = queue.popleft()
        for neighbor in adjacency.get(node, set()):
            if neighbor not in result:
                result[neighbor] = result[node] + 1
                queue.append(neighbor)
    return result


def _label_edges(label: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = label.get("edges", label.get("dd_edges", []))
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def audit(data_root: str, labels_root: str) -> Dict[str, Any]:
    cases = []
    for dirpath, _dirs, files in os.walk(data_root):
        if "info.json" in files and ("nodes.json" in files or "topology_context.json" in files):
            cases.append(dirpath)

    state_counts: Counter[str] = Counter()
    positive_edges = 0
    positive_with_known_distance = 0
    outward_edges = 0
    non_outward_edges = 0
    missing_distance_edges = 0
    labeled_cases = 0
    case_rows = []

    for dirpath in sorted(cases):
        case_id = os.path.basename(os.path.normpath(dirpath))
        label_path = os.path.join(labels_root, case_id, "propagation_label.json")
        label = load_json(label_path, default=None)
        if not isinstance(label, Mapping):
            continue
        root = load_training_label(dirpath)
        if not root:
            continue
        nodes = load_case_nodes(dirpath)
        info = load_case_info(dirpath)
        context = load_topology_context(dirpath, node_list=nodes, info=info)
        distances = _distances(physical_adjacency(context), [root])
        local_positive = 0
        local_non_outward = 0
        local_missing = 0
        for edge in _label_edges(label):
            state = str(edge.get("membership", edge.get("state", "unknown")) or "unknown")
            state_counts[state] += 1
            if state not in {"definite", "possible"}:
                continue
            positive_edges += 1
            local_positive += 1
            source = str(edge.get("from", edge.get("source", "")) or "")
            target = str(edge.get("to", edge.get("target", "")) or "")
            source_distance = distances.get(source)
            target_distance = distances.get(target)
            if source_distance is None or target_distance is None:
                missing_distance_edges += 1
                local_missing += 1
            else:
                positive_with_known_distance += 1
                if target_distance > source_distance:
                    outward_edges += 1
                else:
                    non_outward_edges += 1
                    local_non_outward += 1
        labeled_cases += 1
        case_rows.append({
            "case_id": case_id,
            "positive_edges": local_positive,
            "non_outward_edges": local_non_outward,
            "missing_distance_edges": local_missing,
        })

    return {
        "case_count_discovered": len(cases),
        "labeled_case_count": labeled_cases,
        "edge_state_counts": dict(sorted(state_counts.items())),
        "positive_edge_count": positive_edges,
        "positive_edges_with_known_distance": positive_with_known_distance,
        "outward_edge_count": outward_edges,
        "non_outward_edge_count": non_outward_edges,
        "missing_distance_edge_count": missing_distance_edges,
        "non_outward_rate_among_known_positive": round(
            non_outward_edges / positive_with_known_distance, 6
        ) if positive_with_known_distance else None,
        "cases_with_non_outward_edges": sum(
            row["non_outward_edges"] > 0 for row in case_rows
        ),
        "cases_with_missing_distance_edges": sum(
            row["missing_distance_edges"] > 0 for row in case_rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--labels-root", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.data_root, args.labels_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
