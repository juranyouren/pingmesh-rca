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
        data_root: 数据集根目录，递归扫描找出所有 case（含 info.json 的目录）。
        """
        self.data_root = data_root
        self.weights = {}          # {alarm_name: float}
        self.alarm_case_count = defaultdict(int)  # how many cases each alarm appears in
        self.case_count = 0

    # ── scan ──────────────────────────────────────────────────────────
    @staticmethod
    def _find_case_files(dirpath, filenames):
        """
        在目录下找到 node 文件和 info 文件。
        兼容两种数据格式：
          - graph_only 用的 merged_pingmesh-*-全链路.json + info.json
          - Collector 输出的 nodes.json + info.json
        Returns (node_file, info_file) or (None, None).
        """
        node_file = None
        info_file = None
        for f in filenames:
            if f == "info.json":
                info_file = f
            elif "pingmesh" in f and "全链路.json" in f:
                node_file = f
        # fallback: Collector 输出的 nodes.json
        if node_file is None and "nodes.json" in filenames:
            node_file = "nodes.json"
        return node_file, info_file

    def _list_cases(self):
        """Yield (dirpath, nodes_path) for every case under data_root."""
        if not self.data_root or not os.path.isdir(self.data_root):
            return
        for dirpath, _dirnames, filenames in os.walk(self.data_root):
            node_file, info_file = self._find_case_files(dirpath, filenames)
            if node_file and info_file:
                yield dirpath, os.path.join(dirpath, node_file)

    def _load_nodes(self, nodes_path):
        """Load node JSON and normalise to list-of-dicts."""
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
                    if isinstance(evt, str):
                        aname = evt.strip()
                    else:
                        aname = str(evt.get("alarm_name", evt.get("name", ""))).strip()
                    if aname:
                        seen.add(aname)
                        case_alarms.add(aname)
            for aname in case_alarms:
                self.alarm_case_count[aname] += 1

        self.weights = {name: 0.0 for name in sorted(seen)}
        return self

    # ── persist ───────────────────────────────────────────────────────
    def save(self, path):
        """
        Save as a JSON array of {alarm_name, alarm_priority} objects,
        directly compatible with graph_only.py's reading convention.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        alarm_list = []
        for name in sorted(self.weights.keys()):
            alarm_list.append({
                "alarm_name": name,
                "alarm_priority": self.weights[name],
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(alarm_list, f, ensure_ascii=False, indent=2)
        print(f"[AlarmWeightBuilder] saved {len(alarm_list)} alarm types → {path}")

    def load(self, path):
        """
        Load a weight file (array format or legacy dict format).
        Array format: [{alarm_name, alarm_priority}, ...]  ← graph_only.py native
        Dict  format: {"weights": {...}, ...}              ← legacy
        """
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, list):
            for item in payload:
                name = item.get("alarm_name", "")
                if name:
                    self.weights[name] = float(item.get("alarm_priority", 0.0))
        elif isinstance(payload, dict):
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
        "/home/sbp/lixinyang/pingmesh/data/weights/alarm_weights.json"

    builder = AlarmWeightBuilder(data_root=data_root)
    builder.build()
    builder.stats()
    builder.save(out_path)
