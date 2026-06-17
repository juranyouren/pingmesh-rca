"""
Score_N — 根因定位评测模块
=========================
从 res.json 读取结果，计算 Top-1~5 命中率。
支持分层评测：skill_evaluation (纯算法) / llm_evaluation (LLM 重排)。

用法:
    from Sys.Score.Score_N import Scorer
    s = Scorer("path/to/res.json")
    s.calculate_metrics()  # -> sum.json + failures/success json
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

        # 1. try JSON code block
        blocks = self._json_block.findall(text)
        if blocks:
            for block in reversed(blocks):  # last block wins
                ips = self._try_json_block(block)
                if ips is not None:
                    return Prediction(ips=ips)

        # 2. fallback: regex
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
        pred_ips = list(dict.fromkeys(pred.ips))  # dedup, preserve order

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
        return GroundTruth(ips=gt_ips)

    # ── core eval ──────────────────────────────────────────────────

    def _eval_ips(self, res_data: List[Dict], ip_source: str) -> Dict[str, Any]:
        """
        ip_source:
          "skill_ips"   → 从 res.json 的 skill_ips 字段读（纯算法排名）
          "response"    → 从 LLM 的 response 文本解析 IP
        """
        metrics = {c: {f"sum_top{i}": 0 for i in range(1, 6)}
                     | {"failure_cases": [], "success_cases": []}
                   for c in ["all"]}

        for rd in res_data:
            dir_name = rd.get("dir")
            gt = self._get_groundtruth(dir_name)
            if not gt.ips:
                continue

            if ip_source == "skill_ips":
                ips = rd.get("skill_ips", [])
                pred = Prediction(ips=ips if isinstance(ips, list) else [])
            else:
                text = rd.get(ip_source, "")
                pred = self.parser.parse(text)

            res = self.evaluator.evaluate(gt, pred)

            case_log = {
                "name": dir_name,
                "gt_ips": gt.ips,
                "pred_ips": res["pred_ips"],
                "top1_hit": res["top1_hit"],
            }

            for c in ["all"]:
                for i in range(1, 6):
                    metrics[c][f"sum_top{i}"] += res[f"top{i}_hit"]
                if res["is_failed"]:
                    metrics[c]["failure_cases"].append(case_log)
                else:
                    metrics[c]["success_cases"].append(case_log)

        return self._build_summary(metrics)

    @staticmethod
    def _build_summary(metrics):
        result = {}
        for c in metrics:
            m = metrics[c]
            n = len(m["failure_cases"]) + len(m["success_cases"])
            if n == 0:
                result[c] = {"status": "No cases"}
                continue
            result[c] = {
                "ranking_metrics": {
                    "Total Evaluated Cases": n,
                    **{f"Top-{i} Acc (%)": round(m[f"sum_top{i}"] / n * 100, 2)
                       for i in range(1, 6)},
                },
                "failed_cases_count": len(m["failure_cases"]),
                "success_cases_count": len(m["success_cases"]),
                "_raw_failures": m["failure_cases"],
                "_raw_successes": m["success_cases"],
            }
        return result

    # ── main entry ─────────────────────────────────────────────────

    def calculate_metrics(self):
        res_data = self._load_json(self.res_path)
        if not res_data:
            raise ValueError(f"empty: {self.res_path}")

        skill_res = self._eval_ips(res_data, "skill_ips")
        llm_res = self._eval_ips(res_data, "response")

        # refine stage — only if response field has content
        has_refine = any(len(str(rd.get("response", ""))) > 10 for rd in res_data[:5])
        refine_res = self._eval_ips(res_data, "response") if has_refine else None

        summary = {
            "total_cases_in_file": len(res_data),
            "skill_evaluation": self._clean(skill_res),
            "llm_evaluation": self._clean(llm_res),
        }
        if refine_res:
            summary["refined_evaluation"] = self._clean(refine_res)

        sum_path = os.path.join(self.out_dir, "sum.json")
        self._save_json(summary, sum_path)

        # save failures/success detail files
        self._save_detail(skill_res, "skill")
        self._save_detail(llm_res, "llm")
        if refine_res:
            self._save_detail(refine_res, "refined")

        print(f"评测完成 → {sum_path}")
        return summary

    @staticmethod
    def _clean(stage_res):
        if not stage_res:
            return {}
        return {c: {k: v for k, v in d.items() if not k.startswith("_raw")}
                for c, d in stage_res.items()}

    def _save_detail(self, stage_res, prefix):
        if not stage_res or "all" not in stage_res or "status" in stage_res["all"]:
            return
        fail_data = stage_res["all"]["_raw_failures"]
        succ_data = stage_res["all"]["_raw_successes"]
        if fail_data:
            self._save_json(fail_data,
                            os.path.join(self.out_dir, f"{prefix}_ranking_failures.json"))
        if succ_data:
            self._save_json(succ_data,
                            os.path.join(self.out_dir, f"{prefix}_ranking_success.json"))


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
