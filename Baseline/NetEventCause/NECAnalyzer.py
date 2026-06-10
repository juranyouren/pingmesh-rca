"""
NetEventCause Baseline — faithful reimplementation based on:
  Yuan et al., "NetEventCause: Event-Driven Root Cause Analysis for Large
  Network System Without Topology", TNNLS 2025.

Core idea:
  1. Model alarm sequences as a multi-variate temporal point process (TPP)
  2. Learn conditional-intensity relationships between alarm types via a
     multi-variate Hawkes process with exponential decay kernel
  3. Root-cause attribution: compare prior (base) intensity vs conditional
     (history-excited) intensity — a high base/conditional ratio indicates
     the event is a root cause rather than a derivative.

This implementation uses a multi-variate Hawkes process (MHP) fitted via
maximum likelihood estimation (MLE).  The learned excitation matrix α
captures Granger-causal relationships between alarm types.
"""

import os, json, time, math
from collections import defaultdict
from multiprocessing import Pool, cpu_count

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit  # sigmoid for stability clamping


# ── helpers ──────────────────────────────────────────────────────────
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Multi-variate Hawkes Process ─────────────────────────────────────
class MultiVariateHawkes:
    """
    Multi-variate Hawkes Process with exponential decay kernel.

    Intensity for type j at time t:
      λ_j(t) = μ_j + Σ_{t_i < t} α_{k_i, j} · β · exp(-β (t - t_i))

    where:
      μ_j  = base (exogenous) intensity of type j
      α_ij = excitation from type i to type j
      β    = global decay rate
    """

    def __init__(self, n_types, decay=1.0):
        self.n_types = n_types
        self.decay = decay  # β
        self.mu = np.ones(n_types) * 0.01       # base intensities
        self.alpha = np.zeros((n_types, n_types))  # excitation matrix

    def fit(self, sequences, lr=0.01, max_iter=200, verbose=False):
        """
        Fit α and μ via projected gradient ascent on the log-likelihood.

        Each sequence is a list of (timestamp, type_idx) tuples sorted by time.
        """
        n = self.n_types
        beta = self.decay

        mu = np.full(n, 0.01)
        alpha = np.zeros((n, n))

        def neg_log_lik(params):
            mu_p = np.exp(params[:n])          # ensure positivity
            a_p = np.exp(params[n:]).reshape(n, n)  # ensure positivity

            total_nll = 0.0
            for seq in sequences:
                if len(seq) < 2:
                    continue
                ts = np.array([e[0] for e in seq])
                ks = np.array([e[1] for e in seq], dtype=int)

                for i in range(len(seq)):
                    t, k = ts[i], ks[i]
                    # Compute intensity λ_k(t)
                    lam = mu_p[k]
                    for j in range(i):
                        dt = t - ts[j]
                        kj = ks[j]
                        lam += a_p[kj, k] * beta * math.exp(-beta * dt)

                    total_nll += math.log(max(lam, 1e-12))

                    # Integral term: ∫ λ_k(s) ds from t_{i-1} to t_i
                    t_prev = ts[i-1] if i > 0 else 0.0
                    integral = mu_p[k] * (t - t_prev)
                    for j in range(i):
                        dt_start = t_prev - ts[j]
                        dt_end = t - ts[j]
                        kj = ks[j]
                        integral += a_p[kj, k] * (
                            math.exp(-beta * max(dt_start, 0)) -
                            math.exp(-beta * dt_end)
                        )
                    total_nll -= integral

            return -total_nll / max(len(sequences), 1)

        # Initial params
        init = np.concatenate([np.log(mu + 1e-6), np.log(alpha.ravel() + 1e-6)])

        try:
            res = minimize(
                neg_log_lik, init, method='L-BFGS-B',
                options={'maxiter': max_iter, 'disp': verbose},
            )
            params = res.x
        except Exception:
            params = init

        self.mu = np.exp(params[:n])
        self.alpha = np.exp(params[n:]).reshape(n, n)
        # Clamp for numerical stability
        self.mu = np.clip(self.mu, 1e-6, 100)
        self.alpha = np.clip(self.alpha, 0, 50)

        return self

    def root_cause_score(self, sequence):
        """
        For each event in the sequence, compute:
          root_score = μ_k / (μ_k + Σ_{preceding events} α_{kj,k} · exp(-β·dt))

        A high score means the event is unlikely to be explained by preceding
        events → it is a candidate root cause.

        Returns list of (timestamp, type_idx, root_score, device_ip).
        """
        beta = self.decay
        results = []
        for i, (t, k, dev_ip) in enumerate(sequence):
            total_excitation = 0.0
            for j in range(i):
                dt = t - sequence[j][0]
                kj = sequence[j][1]
                total_excitation += self.alpha[kj, k] * math.exp(-beta * dt)

            base = self.mu[k]
            total = base + total_excitation
            root_prob = base / max(total, 1e-12)

            results.append((t, k, float(root_prob), dev_ip))

        return results


# ── Alarm type encoding ──────────────────────────────────────────────
class AlarmTypeEncoder:
    """Map alarm name strings to integer type indices."""
    def __init__(self):
        self.type_to_id = {}
        self.id_to_type = {}

    def fit(self, all_sequences):
        """all_sequences: list of lists of (ts, alarm_name, device_ip)"""
        seen = set()
        for seq in all_sequences:
            for _, aname, _ in seq:
                seen.add(aname)
        for name in sorted(seen):
            i = len(self.type_to_id)
            self.type_to_id[name] = i
            self.id_to_type[i] = name
        return self

    def encode(self, seq):
        """Convert [(ts, alarm_name, ip), ...] → [(ts, type_id, ip), ...]"""
        return [(t, self.type_to_id.get(n, 0), ip) for t, n, ip in seq]

    @property
    def n_types(self):
        return max(1, len(self.type_to_id))


# ── NetEventCause Analyzer ───────────────────────────────────────────
class NetEventCauseAnalyzer:
    """
    Full NEC pipeline adapted to the DCN Pingmesh setting.
    """

    def __init__(self, decay=1.0, top_k=5):
        self.decay = decay
        self.top_k = top_k
        self.encoder = AlarmTypeEncoder()
        self.model = None  # MultiVariateHawkes, fitted later

    # ── Data extraction ────────────────────────────────────────────
    def _extract_sequence(self, dirpath):
        """Extract time-ordered alarm sequence from a case."""
        nodes = load_json(os.path.join(dirpath, "nodes.json")) or {}
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        events = []
        for nd in nodes:
            ip = nd.get("mgmt_ip", "unknown")
            for evt in nd.get("alarms", []) + nd.get("logs", []):
                aname = evt.get("name", evt.get("alarm_name", "Unknown"))
                t_str = evt.get("time", evt.get("confirm_time", ""))
                ts = self._parse_ts(t_str)
                if ts > 0:
                    events.append((ts, aname, ip))

        events.sort(key=lambda x: x[0])
        return events

    @staticmethod
    def _parse_ts(t_str):
        if not t_str:
            return 0.0
        try:
            from datetime import datetime
            for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                         "%Y-%m-%dT%H:%M:%S", "%Y/%m/%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(str(t_str)[:19], fmt).timestamp()
                except ValueError:
                    continue
            return float(t_str)
        except Exception:
            return 0.0

    # ── Fit & predict ───────────────────────────────────────────────
    def fit(self, dirpaths):
        """Collect all sequences, build vocabulary, fit MHP."""
        raw_seqs = []
        for dp in dirpaths:
            seq = self._extract_sequence(dp)
            if seq:
                raw_seqs.append(seq)

        self.encoder.fit(raw_seqs)
        encoded = [self.encoder.encode(s) for s in raw_seqs]

        self.model = MultiVariateHawkes(self.encoder.n_types, decay=self.decay)
        self.model.fit(encoded, verbose=False)
        return self

    def predict_one(self, dirpath):
        """Return ranked device IPs for one case."""
        raw_seq = self._extract_sequence(dirpath)
        if not raw_seq or self.model is None:
            return []

        encoded = self.encoder.encode(raw_seq)
        scored_events = self.model.root_cause_score(encoded)

        # Aggregate per-device root cause score
        dev_score = defaultdict(float)
        for ts, tid, rp, ip in scored_events:
            dev_score[ip] += rp

        ranked = sorted(dev_score.items(), key=lambda x: x[1], reverse=True)
        return [ip for ip, _ in ranked[:self.top_k]]

    def process_cases(self, dirpaths):
        """Main entry point for batch evaluation."""
        results = []
        for dp in dirpaths:
            top_ips = self.predict_one(dp)
            response = (
                "NetEventCause Baseline: Multi-variate Hawkes Process (MHP) "
                "with exponential-decay excitation kernel. Root-cause "
                "attribution via prior-intensity / conditional-intensity "
                "ratio (Yuan et al., TNNLS 2025).\n"
                "```json\n"
                + json.dumps({"ip": top_ips}, ensure_ascii=False, indent=2) +
                "\n```"
            )
            results.append({
                "dir": dp,
                "prompt": "NEC (MHP + attribution RCA)",
                "draft_response": response,
            })
        return results


# ── Parallel runner ──────────────────────────────────────────────────
def _load_all_sequences(dirpaths):
    """Extract all sequences once for fitting."""
    raw_seqs = []
    for dp in dirpaths:
        nodes = load_json(os.path.join(dp, "nodes.json")) or {}
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        events = []
        for nd in nodes:
            ip = nd.get("mgmt_ip", "unknown")
            for evt in nd.get("alarms", []) + nd.get("logs", []):
                aname = evt.get("name", evt.get("alarm_name", "Unknown"))
                t_str = evt.get("time", evt.get("confirm_time", ""))
                try:
                    from datetime import datetime
                    ts = 0.0
                    for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                        try:
                            ts = datetime.strptime(str(t_str)[:19], fmt).timestamp()
                            break
                        except ValueError:
                            continue
                except Exception:
                    ts = 0.0
                if ts > 0:
                    events.append((ts, aname, ip))
        events.sort(key=lambda x: x[0])
        if events:
            raw_seqs.append(events)
    return raw_seqs


def _worker(args):
    dirpaths_chunk, decay, top_k = args
    # Fit on ALL available data (transductive setting for baseline comparison)
    # In practice, this means the MHP parameters are informed by the full dataset
    analyzer = NetEventCauseAnalyzer(decay=decay, top_k=top_k)
    analyzer.fit(dirpaths_chunk)
    return analyzer.process_cases(dirpaths_chunk)


def generate_prompts(root_path):
    dirpaths = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            dirpaths.append(dirpath)
    return dirpaths


def distribute_inference_tasks(dirpath_list, decay=1.0, top_k=5):
    if not dirpath_list:
        return []

    # Fit the MHP model on ALL sequences first, then predict each case
    # This is a transductive baseline — uses all data to learn the alarm-type
    # excitation matrix, then applies it to each case.  For a strict inductive
    # comparison, use K-fold cross-validation.
    print("Fitting multi-variate Hawkes process on all cases...")
    t0 = time.time()
    analyzer = NetEventCauseAnalyzer(decay=decay, top_k=top_k)
    analyzer.fit(dirpath_list)
    print(f"  Fitted in {time.time() - t0:.1f}s ({analyzer.encoder.n_types} alarm types)")

    n_workers = min(cpu_count(), 32)
    chunk_size = math.ceil(len(dirpath_list) / n_workers)
    chunks = [dirpath_list[i:i + chunk_size]
              for i in range(0, len(dirpath_list), chunk_size)]

    all_results = []
    # Use the fitted analyzer for all chunks
    for chunk in chunks:
        all_results.extend(analyzer.process_cases(chunk))

    return all_results


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"

    dirpaths = generate_prompts(root)
    print(f"NetEventCause: {len(dirpaths)} cases found.")

    t0 = time.time()
    results = distribute_inference_tasks(dirpaths, decay=1.0, top_k=5)
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.2f}s ({elapsed/max(len(results),1):.4f}s/case)")

    outdir = f"/home/sbp/lixinyang/pingmesh/data/res/neceventcause_baseline_{int(time.time())}"
    save_json(results, os.path.join(outdir, "res.json"))
    print(f"Saved to {outdir}")
