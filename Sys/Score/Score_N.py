"""
Score_N — 根因定位评测模块
=========================
从 res.json 读取结果，计算 Top-1~5 命中率。
输出 sum.json: {skill_evaluation, llm_evaluation}

用法:
    python Sys/Score/Score_N.py path/to/res.json
"""

import json
import os
import re
from typing import List, Dict, Any
from dataclasses import dataclass


# ══════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════

@dataclass
class GroundTruth:
    ips: List[str]
    source: str = ""


@dataclass
class Prediction:
    ips: List[str]


# ══════════════════════════════════════════════════════════════════
# LLM response parser
# ══════════════════════════════════════════════════════════════════

class ResponseParser:
    """解析 LLM 输出中的 IP 列表。"""

    def __init__(self):
        self._json_block = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL | re.IGNORECASE)
        self._ip_quoted = re.compile(r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"')
        self._ip_loose = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')

    def parse(self, text: str) -> Prediction:
        if not text or not isinstance(text, str):
            return Prediction(ips=[])
        blocks = self._json_block.findall(text)
        if blocks:
            for block in reversed(blocks):
                ips = self._try_json_block(block)
                if ips is not None:
                    return Prediction(ips=ips)
        ips = self._ip_quoted.findall(text)
        if not ips:
            ips = [ip for ip in self._ip_loose.findall(text)
                   if not ip.startswith(("0.", "255."))]
        return Prediction(ips=ips)

    @staticmethod
    def _try_json_block(json_str: str):
        for candidate in (json_str, json_str.replace("'", '"')):
            try:
                data = json.loads(candidate)
                ips = data.get("ip", [])
                if isinstance(ips, str):
                    return [ips]
                if isinstance(ips, list):
                    return [ip for ip in ips if isinstance(ip, str)]
            except (json.JSONDecodeError, ValueError):
                pass
        return None


# ══════════════════════════════════════════════════════════════════
# Metrics
# ══════════════════════════════════════════════════════════════════

class MetricsEvaluator:
    """计算 Top-1~5 命中。"""

    def evaluate(self, gt: GroundTruth, pred: Prediction) -> Dict[str, Any]:
        pred_ips = list(dict.fromkeys(pred.ips))

        hits = {f"top{i}_hit": 0 for i in range(1, 6)}
        if gt.ips:
            best = None
            for g in gt.ips:
                if g in pred_ips:
                    idx = pred_ips.index(g)
                    if best is None or idx < best:
                        best = idx
            if best is not None:
                for i in range(1, 6):
                    if best < i:
                        hits[f"top{i}_hit"] = 1

        any_hit = any(g in pred_ips for g in gt.ips) if gt.ips else False
        return {
            **hits,
            "best_rank": (best + 1) if (gt.ips and best is not None) else None,  # 1-based, None=未命中
            "is_failed": bool(pred_ips and gt.ips and not any_hit),
            "pred_ips": pred_ips,
        }


# ══════════════════════════════════════════════════════════════════
# Scorer
# ══════════════════════════════════════════════════════════════════

class Scorer:
    def __init__(self, res_file_path: str):
        self.res_path = res_file_path
        self.out_dir = os.path.dirname(res_file_path)
        self.evaluator = MetricsEvaluator()
        self.parser = ResponseParser()

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _load_json(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save_json(data, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _get_groundtruth(dir_name: str) -> GroundTruth:
        label_v2_path = os.path.join(dir_name, "label_v2.json")
        if os.path.exists(label_v2_path):
            labels_v2 = Scorer._load_json(label_v2_path)
            gt_ips = Scorer._get_groundtruth_v2(labels_v2)
            if gt_ips:
                return GroundTruth(ips=gt_ips, source="label_v2.json")

        label_path = os.path.join(dir_name, "label.json")
        if not os.path.exists(label_path):
            return GroundTruth(ips=[])
        labels = Scorer._load_json(label_path)
        if not isinstance(labels, list):
            return GroundTruth(ips=[])
        labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
        gt_ips = []
        for lb in labels_sorted[:3]:
            for an in lb.get("abnormal_node", []):
                ip = an.get("ip")
                if ip and ip not in gt_ips:
                    gt_ips.append(ip)
        return GroundTruth(ips=gt_ips, source="label.json:top3_ranking")

    @staticmethod
    def _extract_ips(value) -> List[str]:
        """Extract IP strings from flexible label_v2 fields."""
        ips = []
        if value is None:
            return ips
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, dict):
            for key in ("ip", "mgmt_ip", "device_ip"):
                ip = value.get(key)
                if ip:
                    return [ip]
            return ips
        if isinstance(value, list):
            for item in value:
                for ip in Scorer._extract_ips(item):
                    if ip not in ips:
                        ips.append(ip)
        return ips

    @staticmethod
    def _get_groundtruth_v2(labels: Any) -> List[str]:
        """
        Preferred strict label schema for paper-grade evaluation.

        Supported fields:
          - primary_root_cause / primary_root_causes: counted first
          - secondary_root_causes: counted after primary roots
          - root_causes: fallback when primary/secondary split is absent

        Fields such as victims/affected_nodes are intentionally ignored.
        """
        if not isinstance(labels, dict):
            return []

        gt_ips = []
        primary = []
        for key in ("primary_root_cause", "primary_root_causes"):
            primary.extend(Scorer._extract_ips(labels.get(key)))

        secondary = Scorer._extract_ips(labels.get("secondary_root_causes"))
        fallback = Scorer._extract_ips(labels.get("root_causes"))

        for ip in primary + secondary + fallback:
            if ip and ip not in gt_ips:
                gt_ips.append(ip)
        return gt_ips

    # ── core eval ──────────────────────────────────────────────────

    def _eval_ips(self, res_data: List[Dict], ip_source: str) -> Dict[str, Any]:
        """ip_source: "skill_ips" (纯算法) 或 "response" (LLM 解析)。"""
        sums = {f"sum_top{i}": 0 for i in range(1, 6)}
        n = 0
        # Top-1 失败案例 (按 gt 实际落点分桶)
        fail_in_top3 = []   # Top-1 未命中, 但 gt 在 rank 2-3
        fail_in_top5 = []   # gt 在 rank 4-5
        fail_miss = []      # gt 不在 Top-5

        for rd in res_data:
            dir_name = rd.get("dir")
            gt = self._get_groundtruth(dir_name)
            if not gt.ips:
                continue

            if ip_source == "skill_ips":
                ips = rd.get("skill_ips", [])
                pred = Prediction(ips=ips if isinstance(ips, list) else [])
            else:
                pred = self.parser.parse(rd.get(ip_source, ""))

            res = self.evaluator.evaluate(gt, pred)
            n += 1
            for i in range(1, 6):
                sums[f"sum_top{i}"] += res[f"top{i}_hit"]

            # 收集 Top-1 失败案例
            if not res["top1_hit"]:
                rec = {
                    "dir": dir_name,
                    "gt_ips": gt.ips,
                    "gt_source": gt.source,
                    "pred_ips": res["pred_ips"][:10],
                    "best_rank": res["best_rank"],
                }
                if res["top3_hit"]:
                    fail_in_top3.append(rec)
                elif res["top5_hit"]:
                    fail_in_top5.append(rec)
                else:
                    fail_miss.append(rec)

        if n == 0:
            return {}
        return {
            "ranking_metrics": {
                "Total Evaluated Cases": n,
                **{f"Top-{i} Acc (%)": round(sums[f"sum_top{i}"] / n * 100, 2)
                   for i in range(1, 6)},
            },
            "_top1_failures": {
                "in_top3 (rank 2-3)": fail_in_top3,
                "in_top5 (rank 4-5)": fail_in_top5,
                "miss (not in top5)": fail_miss,
            },
        }

    # ── main entry ─────────────────────────────────────────────────

    def calculate_metrics(self):
        res_data = self._load_json(self.res_path)
        if not res_data:
            raise ValueError(f"empty: {self.res_path}")

        skill_eval = self._eval_ips(res_data, "skill_ips")
        llm_eval = self._eval_ips(res_data, "response")

        # 分离失败案例详情, 单独存盘, sum.json 只留指标
        failures = {}
        for name, ev in [("skill", skill_eval), ("llm", llm_eval)]:
            if ev and "_top1_failures" in ev:
                failures[name] = ev.pop("_top1_failures")

        summary = {
            "total_cases_in_file": len(res_data),
            "skill_evaluation": skill_eval,
            "llm_evaluation": llm_eval,
        }

        sum_path = os.path.join(self.out_dir, "sum.json")
        self._save_json(summary, sum_path)

        # Top-1 失败案例详情 (标注 gt 落在 top3 / top5 / miss)
        if failures:
            fail_path = os.path.join(self.out_dir, "top1_failures.json")
            self._save_json(failures, fail_path)
            for name, buckets in failures.items():
                counts = {k: len(v) for k, v in buckets.items()}
                print(f"  [{name}] Top-1 失败分布: {counts}")

        print(f"评测完成 -> {sum_path}")
        return summary


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Score_N — RCA 评测")
    p.add_argument("res_json", help="res.json 路径")
    args = p.parse_args()

    s = Scorer(args.res_json)
    summary = s.calculate_metrics()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
