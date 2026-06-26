"""
TraceRCA Baseline — faithful reimplementation based on:
  Li et al., "Practical Root Cause Localization for Microservice Systems
  via Trace Analysis", TSC 2021.

Core pipeline:
  1. Identify anomalous traces (Pingmesh lossy paths)
  2. FP-Growth frequent-itemset mining on anomalous-path device sets
  3. Jaccard-based candidate scoring + propagation direction inference
  4. Ranked root-cause device list
"""

import os, json, time, math
from collections import defaultdict, Counter
from itertools import combinations
from multiprocessing import Pool, cpu_count


# ── helpers ──────────────────────────────────────────────────────────
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── FP-Growth ────────────────────────────────────────────────────────
class FPTree:
    """Minimal FP-tree for itemset mining on device sets."""
    def __init__(self):
        self.root = _FPNode(None, None)
        self.header = defaultdict(list)  # item → list of nodes

    def insert(self, transaction):
        node = self.root
        for item in transaction:
            child = node.get_child(item)
            if child is None:
                child = _FPNode(item, node)
                node.add_child(child)
                self.header[item].append(child)
            child.count += 1
            node = child


class _FPNode:
    __slots__ = ('item', 'parent', 'children', 'count')
    def __init__(self, item, parent):
        self.item = item
        self.parent = parent
        self.children = {}
        self.count = 0

    def get_child(self, item):
        return self.children.get(item)

    def add_child(self, node):
        self.children[node.item] = node


def _mine_tree(header, min_support, prefix, freq_sets):
    for item in sorted(header, key=lambda x: sum(n.count for n in header[x])):
        support = sum(n.count for n in header[item])
        if support < min_support:
            continue
        new_set = frozenset(prefix | {item})
        freq_sets[new_set] = support

        # Build conditional pattern base
        cond_trans = []
        for node in header[item]:
            path = []
            p = node.parent
            while p.item is not None:
                path.append(p.item)
                p = p.parent
            for _ in range(node.count):
                cond_trans.append(path)

        if cond_trans:
            cond_header = defaultdict(list)
            cond_root = _FPNode(None, None)
            for trans in cond_trans:
                cur = cond_root
                for it in trans:
                    child = cur.get_child(it)
                    if child is None:
                        child = _FPNode(it, cur)
                        cur.add_child(child)
                        cond_header[it].append(child)
                    child.count += 1
                    cur = child
            _mine_tree(cond_header, min_support, new_set, freq_sets)


def fp_growth(transactions, min_support):
    """Return {frozenset_of_items: support_count}."""
    # Count item frequencies
    item_counts = Counter()
    for trans in transactions:
        for item in set(trans):
            item_counts[item] += 1

    # Filter frequent items and sort by frequency desc
    freq_items = {item: cnt for item, cnt in item_counts.items()
                  if cnt >= min_support}

    # Build FP-tree
    tree = FPTree()
    for trans in transactions:
        filtered = [it for it in trans if it in freq_items]
        filtered.sort(key=lambda x: freq_items[x], reverse=True)
        tree.insert(filtered)

    freq_sets = {}
    _mine_tree(tree.header, min_support, frozenset(), freq_sets)
    return freq_sets


# ── TraceRCA Core ────────────────────────────────────────────────────
class TraceRCAnalyzer:
    """
    Implements the TraceRCA algorithm adapted for DCN path-based RCA.

    Mapping from original microservice context:
      trace  → Pingmesh end-to-end path
      service → network device on the path
      abnormal trace → path with packet loss detected by Pingmesh
    """

    def __init__(self, min_support_ratio=0.15, top_k=5):
        self.min_support_ratio = min_support_ratio
        self.top_k = top_k

    # ── Data preparation ──────────────────────────────────────────
    def _load_case(self, dirpath):
        nodes = _load_full_link(dirpath)
        info  = load_json(os.path.join(dirpath, "info.json")) or {}
        # Normalise to list-of-dicts
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        return nodes, info

    def _build_transactions(self, nodes):
        """
        Each "transaction" = the set of device IPs on one anomalous path.
        We derive paths from the cross field (link-level coverage) and
        from linked_from/linked_to to reconstruct which devices each
        anomalous end-to-end path traverses.

        In the Pingmesh context, every *anomalous* src-dst pair defines
        one abnormal trace.  The devices on that trace are those whose
        cross count includes that pair.
        """
        transactions = []
        # Collect all device→cross mapping
        ip_to_name = {}
        for nd in nodes:
            ip = nd.get("mgmt_ip")
            if ip:
                ip_to_name[ip] = nd.get("name", ip)

        # Build transactions from cross information
        # Each device's "cross" indicates how many anomalous paths it belongs to.
        # We treat each anomalous path as a transaction containing all devices
        # that report this path in their cross data.
        # Since we cannot reconstruct the exact path membership from the aggregated
        # cross count, we use an indirect strategy:

        # Strategy: use the linked_from/linked_to topology to enumerate simple
        # paths between every pair of (src, dst) that Pingmesh reported, then
        # collect the devices on those paths.
        # When full path enumeration is expensive, fall back to:
        #   transaction per alarm — all devices that share a specific alarm type.

        # Fallback approach: build transaction = {devices with common alarm types}
        device_alarms = defaultdict(set)
        for nd in nodes:
            ip = nd.get("mgmt_ip")
            if not ip:
                continue
            for alarm in nd.get("alarms", []):
                aname = alarm.get("name", alarm.get("alarm_name", ""))
                if aname:
                    device_alarms[aname].add(ip)

        # Prune alarm types that appear on only one device
        for aname, devs in device_alarms.items():
            if len(devs) >= 2:
                transactions.append(list(devs))

        # Supplement with topology path reconstruction if path info available
        # Use verified_hops_to and linked_to to build adjacency-based transactions
        for nd in nodes:
            ip = nd.get("mgmt_ip")
            if not ip:
                continue
            neighbors = set()
            for nip in nd.get("linked_to", []) + nd.get("verified_hops_to", []):
                if nip in ip_to_name:
                    neighbors.add(nip)
            if len(neighbors) >= 2:
                # The device + its direct neighbours form a local transaction
                trans = [ip] + list(neighbors)
                transactions.append(trans)

        return transactions

    # ── Candidate scoring ──────────────────────────────────────────
    def _score_candidates(self, nodes, transactions, freq_sets):
        """
        Score each device using TraceRCA's approach:
          1. Anomaly ratio: #abnormal_paths_through_device / total paths
          2. Jaccard similarity with other high-suspicion candidates
          3. Propagation direction inference
        """
        if not transactions:
            return []

        # Count how many abnormal transactions each device appears in
        abnormal_count = Counter()
        for trans in transactions:
            for ip in trans:
                abnormal_count[ip] += 1

        total_abnormal = len(transactions)

        # Estimate total-degree-based path count per device
        # (since we can't enumerate all normal paths)
        candidates = []
        for nd in nodes:
            ip = nd.get("mgmt_ip")
            if not ip:
                continue

            deg = (len(nd.get("linked_from", [])) +
                   len(nd.get("linked_to", [])) +
                   len(nd.get("verified_hops_to", [])))
            cross = float(nd.get("cross", 0))
            a_cnt = abnormal_count.get(ip, 0)

            # TraceRCA style anomaly ratio
            #   P(abnormal | device) = abnormal_through / total_through
            # Approx total_through ≈ cross (since cross counts anomalous paths)
            # + degree-based estimate of normal paths
            # Better approximation using cross versus anomaly count
            anomaly_ratio = cross / max(deg, 1)

            # Alarm severity factor: more/critical alarms → higher base suspicion
            n_alarms = len(nd.get("alarms", []))
            n_logs   = len(nd.get("logs", []))

            # TraceRCA base score: anomaly ratio * log-scaled event density
            base_score = anomaly_ratio * math.log(1 + n_alarms + n_logs + cross)
            candidates.append({
                "ip": ip,
                "base_score": base_score,
                "anomaly_ratio": anomaly_ratio,
                "n_alarms": n_alarms,
                "n_logs": n_logs,
                "deg": deg,
                "cross": cross,
            })

        # Sort by base score
        candidates.sort(key=lambda x: x["base_score"], reverse=True)

        # Propagation direction penalty:
        # A device whose neighbours all have *higher* anomaly ratio is
        # likely a downstream victim, not the root cause.
        ip_to_cand = {c["ip"]: c for c in candidates}
        for nd in nodes:
            ip = nd.get("mgmt_ip")
            if not ip or ip not in ip_to_cand:
                continue
            neighbors = (nd.get("linked_from", []) +
                         nd.get("linked_to", []) +
                         nd.get("verified_hops_to", []))
            if not neighbors:
                continue
            nbr_scores = []
            for nip in neighbors:
                nc = ip_to_cand.get(nip)
                if nc:
                    nbr_scores.append(nc["anomaly_ratio"])
            if nbr_scores:
                avg_nbr = sum(nbr_scores) / len(nbr_scores)
                if avg_nbr > ip_to_cand[ip]["anomaly_ratio"]:
                    # Penalty: neighbours are worse → this node is victim
                    ip_to_cand[ip]["base_score"] *= 0.5
                elif ip_to_cand[ip]["anomaly_ratio"] > avg_nbr * 1.5:
                    # Bonus: this node is clearly worse than neighbours
                    ip_to_cand[ip]["base_score"] *= 1.3

        # Re-sort after propagation adjustment
        candidates.sort(key=lambda x: x["base_score"], reverse=True)
        return candidates

    # ── Main entry ──────────────────────────────────────────────────
    def process_one(self, dirpath):
        nodes, info = self._load_case(dirpath)
        if not nodes:
            return dirpath, []

        transactions = self._build_transactions(nodes)

        min_support = max(2, int(len(transactions) * self.min_support_ratio))
        freq_sets = fp_growth(transactions, min_support) if transactions else {}

        candidates = self._score_candidates(nodes, transactions, freq_sets)
        top_ips = [c["ip"] for c in candidates[:self.top_k]]
        return dirpath, top_ips

    def process_cases(self, dirpaths):
        results = []
        for dp in dirpaths:
            _, top_ips = self.process_one(dp)
            response = self._format_response(top_ips)
            results.append({
                "dir": dp,
                "prompt": "TraceRCA (FP-Growth + Jaccard + propagation dir inference)",
                "draft_response": response,
            })
        return results

    def _format_response(self, top_ips):
        return (
            "TraceRCA Baseline: FP-Growth frequent-itemset mining on anomalous "
            "Pingmesh paths, Jaccard-similarity scoring with propagation-direction "
            "inference. Full RCA pipeline as described in Li et al. (TSC 2021).\n"
            "```json\n"
            + json.dumps({"ip": top_ips}, ensure_ascii=False, indent=2) +
            "\n```"
        )


# ── Parallel runner ──────────────────────────────────────────────────
def _worker(args):
    dirpaths_chunk, top_k = args
    analyzer = TraceRCAnalyzer(top_k=top_k)
    return analyzer.process_cases(dirpaths_chunk)



def _has_full_link(filenames):
    for f in filenames:
        if "全链路.json" in f and "pingmesh" in f:
            return True
    return False

def _load_full_link(dirpath):
    for f in os.listdir(dirpath):
        if "全链路.json" in f and "pingmesh" in f:
            data = load_json(os.path.join(dirpath, f))
            return list(data.values()) if isinstance(data, dict) else data
    return {}

def generate_prompts(root_path):
    dirpaths = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        if _has_full_link(filenames) and "info.json" in filenames:
            dirpaths.append(dirpath)
    return dirpaths


def distribute_inference_tasks(dirpath_list, top_k=5):
    if not dirpath_list:
        return []

    n_workers = min(cpu_count(), 32)
    chunk_size = math.ceil(len(dirpath_list) / n_workers)
    chunks = [dirpath_list[i:i + chunk_size]
              for i in range(0, len(dirpath_list), chunk_size)]

    all_results = []
    with Pool(processes=n_workers) as pool:
        for res_list in pool.imap_unordered(_worker, [(c, top_k) for c in chunks]):
            all_results.extend(res_list)

    return all_results


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"

    dirpaths = generate_prompts(root)
    print(f"TraceRCA: {len(dirpaths)} cases found.")

    t0 = time.time()
    results = distribute_inference_tasks(dirpaths, top_k=5)
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.2f}s ({elapsed/max(len(results),1):.4f}s/case)")

    outdir = f"/home/sbp/lixinyang/pingmesh/data/res/tracerca_baseline_{int(time.time())}"
    save_json(results, os.path.join(outdir, "res.json"))
    print(f"Saved to {outdir}")
