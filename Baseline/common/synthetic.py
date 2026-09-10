"""Small deterministic interface fixture, never a paper performance dataset."""
from __future__ import annotations

import argparse
from pathlib import Path

from .io import dump_json, normalize_incident


def make_cases(count=6):
    cases, labels, groups = [], [], {}
    for i in range(count):
        start = 1700000000 + i * 1000
        cid = f"synthetic-{i}"
        case = normalize_incident({
            "case_id": cid, "group_id": f"simulated-incident-{i}", "group_verified": True,
            "window": {"start": start, "end": start + 60, "cutoff": start + 60, "timezone": "UTC"},
            "devices": [{"id": d, "type": "switch"} for d in "ABC"],
            "physical_links": [{"u": "A", "v": "B"}, {"u": "B", "v": "C"}],
            "events": [{"event_id": f"{cid}-e{j}", "device_id": d,
                        "event_time": start + 5 + 10 * j + i / 10,
                        "event_type": f"alarm-{d}", "source": "alarm", "message": "Synthetic interface fixture"}
                       for j, d in enumerate("ABC")],
            "observation_coverage": {"complete": True},
        })
        cases.append(case)
        groups[cid] = case["group_id"]
        labels.append({"case_id": cid, "root_status": "confirmed", "root_device": "A",
                       "graph_complete": True, "positive_nodes": list("ABC"),
                       "positive_edges": [["A", "B"], ["B", "C"]]})
    return cases, labels, groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output)
    cases, labels, groups = make_cases()
    dump_json(root / "inputs.json", {"incidents": cases})
    dump_json(root / "labels.json", {"labels": labels, "purpose": "synthetic interface check only"})
    dump_json(root / "groups.json", groups)
    dump_json(root / "nec-smoke.json", {"epochs": 2, "hidden_size": 8, "embedding_size": 8,
                                       "ig_steps": 8, "ode_step": 0.5})


if __name__ == "__main__":
    main()
