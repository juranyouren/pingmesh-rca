import json
import os
import re
from typing import List, Dict, Any, Tuple, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass

from Sys.config import config

# ==========================================
# 1. 数据模型 (Data Models)
# ==========================================
@dataclass
class GroundTruth:
    ips: List[str]
    ppath: Dict[str, Any]

@dataclass
class Prediction:
    ips: List[str]
    ppath: Dict[str, Any]

# ==========================================
# 2. 解析器模块 (Parsers - 策略模式)
# ==========================================
class BaseParser(ABC):
    """解析器基类：所有的输入形式都必须继承此基类，并实现 parse 方法"""
    @abstractmethod
    def parse(self, raw_input: Any) -> Prediction:
        pass

class LlmTextParser(BaseParser):
    """用于解析 LLM 生成的带有 Markdown 和文本的 Response"""
    def __init__(self):
        self.ip_pattern = re.compile(r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"')
        self.ip_generic_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
        self.ppath_pattern = re.compile(r'"propagation_path"\s*:\s*"([^"]+)"')
        self.json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL | re.IGNORECASE)

    def parse(self, raw_input: str) -> Prediction:
        if not raw_input or not isinstance(raw_input, str):
            return Prediction(ips=[], ppath={})

        # 尝试提取 JSON 块
        json_blocks = self.json_pattern.findall(raw_input)
        if json_blocks:
            last_json_str = json_blocks[-1]
            # 先尝试直接解析
            try:
                data = json.loads(last_json_str)
                ips = data.get("ip", [])
                if isinstance(ips, str): ips = [ips]
                ppath = data.get("propagation_path", {})
                return Prediction(ips=ips, ppath=ppath)
            except json.JSONDecodeError:
                pass
            # 回退：替换单引号后重试（LLM 偶尔输出单引号 JSON）
            try:
                last_json_str = last_json_str.replace("'", '"')
                data = json.loads(last_json_str)
                ips = data.get("ip", [])
                if isinstance(ips, str): ips = [ips]
                ppath = data.get("propagation_path", {})
                return Prediction(ips=ips, ppath=ppath)
            except json.JSONDecodeError:
                pass

        # 如果 JSON 提取失败，使用正则兜底
        ips = self.ip_pattern.findall(raw_input)
        if not ips:
            # JSON 数组格式回退: "ip": ["10.0.0.1", ...] 或裸 IP
            ips = self.ip_generic_pattern.findall(raw_input)
            # 排除常见的非设备 IP (如 0.0.0.0, 255.255.255.255)
            ips = [ip for ip in ips if not ip.startswith(('0.', '255.'))]
        ppaths = self.ppath_pattern.findall(raw_input)
        
        ppath_dict = {}
        if ppaths:
            try: ppath_dict = json.loads(ppaths[-1])
            except: pass

        return Prediction(ips=ips if ips else [], ppath=ppath_dict)

class DictParser(BaseParser):
    """用于处理输入已经是结构化字典的情况 (例如 API 直接返回的结构)"""
    def parse(self, raw_input: Dict[str, Any]) -> Prediction:
        if not isinstance(raw_input, dict):
            return Prediction(ips=[], ppath={})
            
        ips = raw_input.get("ip", [])
        if isinstance(ips, str): ips = [ips]
        
        ppath = raw_input.get("propagation_path", {})
        if isinstance(ppath, str):
            try: ppath = json.loads(ppath)
            except: ppath = {}
            
        return Prediction(ips=ips, ppath=ppath)

# ==========================================
# 3. 指标计算模块 (Metrics Evaluator)
# ==========================================
class MetricsEvaluator:
    """纯粹的数学和统计逻辑，不涉及 IO 和 解析"""
    def __init__(self):
        pass

    def evaluate_ranking(self, gt: GroundTruth, pred: Prediction) -> Dict[str, Any]:
        pred_ips = []
        for ip in pred.ips:
            if ip not in pred_ips:
                pred_ips.append(ip)

        top1_hit = 0
        top2_hit = 0
        top3_hit = 0
        top4_hit = 0
        top5_hit = 0

        if gt.ips:
            # 命中任意一个 gt_ip 即算命中：取所有 gt_ip 在预测中的最佳（最小）排名
            best_idx = None
            for g in gt.ips:
                if g in pred_ips:
                    idx_g = pred_ips.index(g)
                    if best_idx is None or idx_g < best_idx:
                        best_idx = idx_g
            if best_idx is not None:
                if best_idx < 1: top1_hit = 1
                if best_idx < 2: top2_hit = 1
                if best_idx < 3: top3_hit = 1
                if best_idx < 4: top4_hit = 1
                if best_idx < 5: top5_hit = 1

        # 命中任意 gt_ip 即不算失败；全部未命中才算失败
        any_gt_hit = any(g in pred_ips for g in gt.ips) if gt.ips else False
        is_failed = bool(pred_ips and gt.ips and not any_gt_hit)

        return {
            "top1_hit": top1_hit,
            "top2_hit": top2_hit,
            "top3_hit": top3_hit,
            "top4_hit": top4_hit,
            "top5_hit": top5_hit,
            "is_failed": is_failed,
            "pred_ips_dedup": pred_ips
        }

# ==========================================
# 4. IO 处理模块 (Data/File Handler)
# ==========================================
class DataIOHandler:
    """负责所有文件的读取和写入"""
    _silent_cache_file = ""
    _silent_cache = None  # None = 未初始化，{} = 已加载（可能为空）

    @classmethod
    def set_cache_file(cls, path: str):
        """设置静默案例缓存文件路径，并重置缓存。"""
        cls._silent_cache_file = path
        cls._silent_cache = None

    @staticmethod
    def load_json(path: str) -> Any:
        if not os.path.exists(path): return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_json(data: Any, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def get_groundtruth(dir_name: str) -> GroundTruth:
        label_file = os.path.join(dir_name, "label.json")
        labels = DataIOHandler.load_json(label_file) or []
        labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))

        gt_ips = []
        for label in labels_sorted[:3]:
            for node in label.get("abnormal_node", []):
                if "ip" in node and node["ip"] not in gt_ips:
                    gt_ips.append(node["ip"])

        return GroundTruth(ips=gt_ips, ppath={})

    @classmethod
    def is_silent_case(cls, dir_name: str) -> bool:
        """
        判断给定的 case 是否为 silent。自带缓存机制减少时间消耗。
        """
        csn = os.path.basename(os.path.normpath(dir_name))

        # 首次调用时尝试从缓存文件加载
        if cls._silent_cache is None:
            loaded = False
            if cls._silent_cache_file and os.path.exists(cls._silent_cache_file):
                try:
                    with open(cls._silent_cache_file, 'r', encoding='utf-8') as f:
                        cls._silent_cache = json.load(f)
                    loaded = True
                except Exception:
                    pass
            if not loaded:
                cls._silent_cache = {}

        if csn in cls._silent_cache:
            return cls._silent_cache[csn]

        original_dir = config.data.pingmesh_raw
        target_file_path = None
        if os.path.exists(original_dir):
            for filename in os.listdir(original_dir):
                if csn in filename and filename.endswith(".json"):
                    target_file_path = os.path.join(original_dir, filename)
                    break
                    
        is_silent = False
        if target_file_path:
            data = cls.load_json(target_file_path)
            if data:
                full_link = data.get("full_link", {})
                if isinstance(full_link, dict):
                    alarm_list = full_link.get("alarm_list", [])
                    log_list = full_link.get("log_list", [])
                    is_silent =  (len(alarm_list)+log_list.get("total"))>1000  

        cls._silent_cache[csn] = is_silent
        # 持久化缓存（最佳努力）
        if cls._silent_cache_file:
            try:
                with open(cls._silent_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cls._silent_cache, f, ensure_ascii=False)
            except Exception:
                pass
        return is_silent

# ==========================================
# 5. 主编排器 (Scorer Orchestrator)
# ==========================================
class Scorer:
    def __init__(self, res_file_path: str, parser: BaseParser = None):
        self.res_file_path = res_file_path
        self.failure_dir = os.path.dirname(self.res_file_path)
        self.io = DataIOHandler()
        self.evaluator = MetricsEvaluator()
        self.parser = parser or LlmTextParser()
        # 设置静默案例缓存文件（与 res 文件同目录，加速重复评测）
        DataIOHandler.set_cache_file(
            os.path.join(self.failure_dir, ".silent_cache.json")
        )

    def _evaluate_stage(self, res_data: List[Dict], response_key: str, prompt_key: str) -> Dict[str, Any]:
        total_cases = len(res_data)
        if total_cases == 0: 
            return {}

        categories = ["all", "normal", "silent"]
        metrics = {
            c: {
                "sum_top1": 0, "sum_top2": 0, "sum_top3": 0, "sum_top4": 0, "sum_top5": 0,
                "failure_cases": [], "success_cases": []
            } for c in categories
        }

        for rd in res_data:
            dir_name = rd.get("dir")
            raw_response = rd.get(response_key, rd.get("response", ""))
            pmt = rd.get(prompt_key, rd.get("prompt", ""))

            gt = self.io.get_groundtruth(dir_name)
            if not gt.ips: continue

            pred = self.parser.parse(raw_response)
            rank_res = self.evaluator.evaluate_ranking(gt, pred)

            is_silent = self.io.is_silent_case(dir_name)
            cat = "silent" if is_silent else "normal"

            case_log = {
                "name": dir_name,
                "is_silent": is_silent,
                "pred_ips_dedup": rank_res["pred_ips_dedup"],
                "gt_ips": gt.ips,
                "top1_hit": rank_res["top1_hit"],
                "pmt": pmt,
                "response": raw_response
            }

            for target_cat in [cat, "all"]:
                # 累加 Top-1 ~ Top-5
                metrics[target_cat]["sum_top1"] += rank_res["top1_hit"]
                metrics[target_cat]["sum_top2"] += rank_res["top2_hit"]
                metrics[target_cat]["sum_top3"] += rank_res["top3_hit"]
                metrics[target_cat]["sum_top4"] += rank_res["top4_hit"]
                metrics[target_cat]["sum_top5"] += rank_res["top5_hit"]

                if rank_res["is_failed"]:
                    metrics[target_cat]["failure_cases"].append(case_log)
                else:
                    metrics[target_cat]["success_cases"].append(case_log)

        return self._build_summary(metrics, categories)

    def _evaluate_skill(self, res_data: List[Dict]) -> Dict[str, Any]:
        """评测纯算法排名（skill_ips），不依赖 LLM 输出。"""
        categories = ["all", "normal", "silent"]
        metrics = {
            c: {
                "sum_top1": 0, "sum_top2": 0, "sum_top3": 0, "sum_top4": 0, "sum_top5": 0,
                "failure_cases": [], "success_cases": []
            } for c in categories
        }

        for rd in res_data:
            # skill_pipeline 输出或 SkilledAnalyzer 写入的 skill_ips
            skill_ips = rd.get("skill_ips", [])
            if not skill_ips:
                # fallback: 尝试从 response 中提取（兼容旧 res.json）
                continue
            dir_name = rd.get("dir")
            gt = self.io.get_groundtruth(dir_name)
            if not gt.ips:
                continue

            pred = Prediction(ips=skill_ips, ppath={})
            rank_res = self.evaluator.evaluate_ranking(gt, pred)

            is_silent = self.io.is_silent_case(dir_name)
            cat = "silent" if is_silent else "normal"

            case_log = {
                "name": dir_name,
                "is_silent": is_silent,
                "pred_ips_dedup": rank_res["pred_ips_dedup"],
                "gt_ips": gt.ips,
                "top1_hit": rank_res["top1_hit"],
            }

            for target_cat in [cat, "all"]:
                metrics[target_cat]["sum_top1"] += rank_res["top1_hit"]
                metrics[target_cat]["sum_top2"] += rank_res["top2_hit"]
                metrics[target_cat]["sum_top3"] += rank_res["top3_hit"]
                metrics[target_cat]["sum_top4"] += rank_res["top4_hit"]
                metrics[target_cat]["sum_top5"] += rank_res["top5_hit"]
                if rank_res["is_failed"]:
                    metrics[target_cat]["failure_cases"].append(case_log)
                else:
                    metrics[target_cat]["success_cases"].append(case_log)

        return self._build_summary(metrics, categories)

    @staticmethod
    def _build_summary(metrics, categories):
        """将聚合指标转为百分比 summary dict。"""
        result_summary = {}
        for c in categories:
            m = metrics[c]
            actual = len(m["failure_cases"]) + len(m["success_cases"])
            if actual == 0:
                result_summary[c] = {"status": f"No {c} cases found."}
                continue
            top1 = round((m["sum_top1"] / actual) * 100, 2)
            top2 = round((m["sum_top2"] / actual) * 100, 2)
            top3 = round((m["sum_top3"] / actual) * 100, 2)
            top4 = round((m["sum_top4"] / actual) * 100, 2)
            top5 = round((m["sum_top5"] / actual) * 100, 2)
            result_summary[c] = {
                "ranking_metrics": {
                    "Total Evaluated Cases": actual,
                    "Top-1 Acc (%)": top1, "Top-2 Acc (%)": top2,
                    "Top-3 Acc (%)": top3, "Top-4 Acc (%)": top4, "Top-5 Acc (%)": top5,
                },
                "failed_cases_count": len(m["failure_cases"]),
                "success_cases_count": len(m["success_cases"]),
                "_raw_failures": m["failure_cases"],
                "_raw_successes": m["success_cases"],
            }
        return result_summary

    @staticmethod
    def _has_stage_data(res_data: List[Dict], key: str) -> bool:
        """检查 res_data 中是否存在非空的 stage key（如 response/refine_prompt）。"""
        for rd in res_data[:5]:  # 抽样前 5 条即可
            val = rd.get(key, "")
            if val and isinstance(val, str) and len(val.strip()) > 10:
                return True
        return False

    def calculate_metrics(self, ):
        summary_file_path = os.path.join(self.failure_dir, "sum.json")

        res_data = self.io.load_json(self.res_file_path)
        if not res_data:
            raise ValueError(f"未能加载测试数据: {self.res_file_path}")

        # 纯算法排名评测（skill_ips — LLM 未介入）
        skill_res = self._evaluate_skill(res_data)

        d_res = self._evaluate_stage(res_data, "draft_response", "draft_prompt")
        if self._has_stage_data(res_data, "response"):
            r_res = self._evaluate_stage(res_data, "response", "refine_prompt")
        else:
            r_res = {"all": {"status": "N/A — 基线/单阶段方法无 refine 输出"}}

        def extract_pure_metrics(stage_res):
            if not stage_res: return {}
            clean_res = {}
            for cat, data in stage_res.items():
                if "status" in data:
                    clean_res[cat] = data
                else:
                    clean_res[cat] = {k: v for k, v in data.items() if not k.startswith("_raw")}
            return clean_res

        overall_summary = {
            "total_cases_in_file": len(res_data),
            "skill_evaluation": extract_pure_metrics(skill_res),
            "llm_evaluation": extract_pure_metrics(d_res),
            "refined_evaluation": extract_pure_metrics(r_res)
        }

        print("💾 评测完成，正在将结果写入本地缓存...")
        self.io.save_json(overall_summary, summary_file_path)
        
        def save_details(stage_res, prefix):
            if not stage_res or "all" not in stage_res or "status" in stage_res["all"]:
                return
            
            fail_data = {
                "normal_cases": stage_res.get("normal", {}).get("_raw_failures", []),
                "silent_cases": stage_res.get("silent", {}).get("_raw_failures", [])
            }
            succ_data = {
                "normal_cases": stage_res.get("normal", {}).get("_raw_successes", []),
                "silent_cases": stage_res.get("silent", {}).get("_raw_successes", [])
            }

            if fail_data["normal_cases"] or fail_data["silent_cases"]:
                self.io.save_json(fail_data, os.path.join(self.failure_dir, f"{prefix}_ranking_failures.json"))
            if succ_data["normal_cases"] or succ_data["silent_cases"]:
                self.io.save_json(succ_data, os.path.join(self.failure_dir, f"{prefix}_ranking_success.json"))

        save_details(d_res, "draft")
        save_details(r_res, "refined")

        print(f"✅ 结果已全部存入: {self.failure_dir}")
        return overall_summary

# ================= 使用示例 =================
if __name__ == "__main__":
    file_path = os.path.join(config.data.results, "1778218041", "res.json")
    
    parser_llm = LlmTextParser()
    scorer = Scorer(res_file_path=file_path, parser=parser_llm)
    
    overall_summary = scorer.calculate_metrics()
    print("\n======= 整体评估结果 =======")
    print(json.dumps(overall_summary, indent=4, ensure_ascii=False))
    
    import pandas as pd
    import os

    # 1. 提取新数据
    new_data = {}
    for category in ["normal", "silent"]:
        metrics = overall_summary["draft_evaluation"][category]["ranking_metrics"]
        for k, v in metrics.items():
            if k != "Total Evaluated Cases":
                new_data[f"{category}_{k}"] = [v]

    new_df = pd.DataFrame(new_data)

    # 2. 判断文件是否存在
    file_path = "result.xlsx"

    if os.path.exists(file_path):
        old_df = pd.read_excel(file_path)
        combined_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined_df = new_df

    # 3. 保存回到 Excel
    combined_df.to_excel(file_path, index=False)
    print(f"✅ 数据已成功追加到 {file_path}")