"""
Alarm Weight Table Builder
==========================
Scans all case directories, extracts every unique alarm name across the
dataset, and initialises a global weight dictionary {alarm_name: 0.0}.

This table is the foundation for alarm-level PageRank / attention weighting:
  - PageRank transfer matrix can use per-alarm-type weights
  - LLM reflection can push earned weights back into the table
  - Co-occurrence patterns can be scored against this table

Usage:
  builder = AlarmWeightBuilder(data_root="/path/to/nodes_labeled")
  builder.build()          # scan all cases, init weights to 0
  builder.save("alarm_weights.json")

  # later: load, update, save
  builder.load("alarm_weights.json")
  builder.update({"BGP_邻居中断": 0.8, "端口Down": 1.0})
  builder.save("alarm_weights.json")
"""

import os
import json
from collections import defaultdict


class AlarmWeightBuilder:

    def __init__(self, data_root=None):
        """
        data_root: directory containing case subdirectories, each with
                   nodes.json and info.json.
        """
        self.data_root = data_root
        self.weights = {}          # {alarm_name: float}
        self.alarm_case_count = defaultdict(int)  # how many cases each alarm appears in
        self.case_count = 0

    # ── scan ──────────────────────────────────────────────────────────
    def _list_cases(self):
        """Yield (dirpath, nodes_path) for every case under data_root."""
        if not self.data_root or not os.path.isdir(self.data_root):
            return
        for dirname in sorted(os.listdir(self.data_root)):
            dp = os.path.join(self.data_root, dirname)
            if not os.path.isdir(dp):
                continue
            np = os.path.join(dp, "nodes.json")
            if os.path.exists(np):
                yield dp, np

    def _load_nodes(self, nodes_path):
        """Load nodes.json and normalise to list-of-dicts."""
        with open(nodes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.values())
        return data if isinstance(data, list) else []

    # ── build ─────────────────────────────────────────────────────────
    def build(self):
        """
        Scan all cases and collect every unique alarm name.
        All weights are initialised to 0.0.
        """
        seen = set()
        self.case_count = 0
        self.alarm_case_count.clear()

        for dp, np in self._list_cases():
            self.case_count += 1
            nodes = self._load_nodes(np)
            case_alarms = set()
            for nd in nodes:
                for evt in nd.get("alarms", []) + nd.get("logs", []):
                    aname = evt.get("name", evt.get("alarm_name", ""))
                    if aname:
                        aname = aname.strip()
                        seen.add(aname)
                        case_alarms.add(aname)
            for aname in case_alarms:
                self.alarm_case_count[aname] += 1

        self.weights = {name: 0.0 for name in sorted(seen)}
        return self

    # ── persist ───────────────────────────────────────────────────────
    def save(self, path):
        """Save the weight table to a JSON file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "weights": self.weights,
            "alarm_case_count": dict(self.alarm_case_count),
            "case_count": self.case_count,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[AlarmWeightBuilder] saved {len(self.weights)} alarm types → {path}")

    def load(self, path):
        """Load a previously saved weight table."""
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.weights = payload.get("weights", {})
        self.alarm_case_count = defaultdict(int, payload.get("alarm_case_count", {}))
        self.case_count = payload.get("case_count", 0)
        print(f"[AlarmWeightBuilder] loaded {len(self.weights)} alarm types ← {path}")
        return self

    # ── update ────────────────────────────────────────────────────────
    def update(self, updates):
        """
        Merge weight dict into current table.  Positive values raise
        suspicion; zero leaves the alarm at its current weight.

        updates: {alarm_name: delta_or_value, ...}
          Use delta=True to add to existing weight instead of replacing.
        """
        for name, val in updates.items():
            if name in self.weights:
                self.weights[name] = val
            else:
                self.weights[name] = val  # new alarm type
        return self

    def update_delta(self, deltas):
        """Add delta values to existing weights (for PageRank / LLM feedback)."""
        for name, delta in deltas.items():
            if name in self.weights:
                self.weights[name] += delta
            else:
                self.weights[name] = delta
        return self

    # ── query ─────────────────────────────────────────────────────────
    def get(self, alarm_name):
        """Return weight for a single alarm, 0 if unseen."""
        return self.weights.get(alarm_name, 0.0)

    def top_k(self, k=20):
        """Return the k highest-weighted alarm names."""
        return sorted(self.weights.items(), key=lambda x: x[1], reverse=True)[:k]

    def stats(self):
        """Print a summary of the weight table."""
        nonzeros = sum(1 for v in self.weights.values() if v != 0.0)
        print(f"[AlarmWeightBuilder] {len(self.weights)} alarm types, "
              f"{nonzeros} non-zero, {self.case_count} cases scanned")
        if nonzeros:
            print("  Top-10 by weight:")
            for name, w in self.top_k(10):
                print(f"    {name:60s} {w:8.4f}  (in {self.alarm_case_count.get(name, 0)} cases)")
        return self


# ── quick CLI ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    data_root = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    out_path = sys.argv[2] if len(sys.argv) > 2 else \
        "/home/sbp/lixinyang/pingmesh/data/alarm_weights.json"

    builder = AlarmWeightBuilder(data_root=data_root)
    builder.build()
    builder.stats()
    builder.save(out_path)
