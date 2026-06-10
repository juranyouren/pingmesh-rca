import json
import os
import re
from typing import List, Dict, Any, Tuple, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass

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
        self.MISSING_PENALTY = 10 
        self.PROBS = [0.54, 0.27, 0.18]

    def evaluate_ranking(self, gt: GroundTruth, pred: Prediction) -> Dict[str, Any]:
        pred_ips = []
        for ip in pred.ips:
            if ip not in pred_ips:
                pred_ips.append(ip)

        pred_len = len(pred_ips)
        
        # 增加 Top-2 和 Top-4 变量
        top1_hit = 0
        top2_hit = 0
        top3_hit = 0
        top4_hit = 0
        top5_hit = 0
        expected_steps = 0.0
        min_cost = 0.0  # 记录理论最小步长
        max_cost = 0.0  # 记录理论最大步长
        
        if gt.ips:
            # 严格以首个 IP 作为第一顺位的高权重根因节点
            gt_primary = gt.ips[0]
            if gt_primary in pred_ips:
                idx = pred_ips.index(gt_primary)
                if idx < 1: top1_hit = 1
                if idx < 2: top2_hit = 1
                if idx < 3: top3_hit = 1
                if idx < 4: top4_hit = 1
                if idx < 5: top5_hit = 1

        for i, gt_ip in enumerate(gt.ips):
            prob = self.PROBS[i] if i < len(self.PROBS) else 0.0
            
            steps_to_find = pred_ips.index(gt_ip) + 1 if gt_ip in pred_ips else pred_len + self.MISSING_PENALTY
            
            # 累加各项成本
            expected_steps += prob * steps_to_find
            min_cost += prob * (i + 1)
            max_cost += prob * (pred_len + self.MISSING_PENALTY)

        is_failed = (pred_ips and gt.ips and gt.ips[0] not in pred_ips) or expected_steps > 6

        return {
            "top1_hit": top1_hit,
            "top2_hit": top2_hit,
            "top3_hit": top3_hit,
            "top4_hit": top4_hit,
            "top5_hit": top5_hit,
            "expected_steps": expected_steps,
            "min_cost": min_cost,  
            "max_cost": max_cost,  
            "is_failed": is_failed,
            "pred_ips_dedup": pred_ips
        }

    def evaluate_topology(self, gt: GroundTruth, pred: Prediction) -> Dict[str, float]:
        case_path_f1, case_path_prec, case_path_rec = 0.0, 0.0, 0.0
        
        if not isinstance(gt.ppath, dict) or not gt.ppath:
            return {"f1": 0.0, "prec": 0.0, "rec": 0.0, "is_valid": False}

        current_gt_ips = list(gt.ppath.keys())[:3]
        current_weights = self.PROBS[:len(current_gt_ips)]
        weight_sum = sum(current_weights) if sum(current_weights) > 0 else 1.0
        norm_weights = [w / weight_sum for w in current_weights]
        
        for i, g_ip in enumerate(current_gt_ips):
            weight = norm_weights[i]
            true_leaves = set(gt.ppath[g_ip].get("affected_nodes", []))
            pred_leaves = set()
            
            if g_ip in pred.ppath and isinstance(pred.ppath[g_ip], dict):
                pred_leaves = set(pred.ppath[g_ip].get("affected_nodes", []))
            
            if not true_leaves and not pred_leaves:
                p, r, f = 1.0, 1.0, 1.0
            else:
                inter = true_leaves.intersection(pred_leaves)
                p = len(inter) / len(pred_leaves) if pred_leaves else 0.0
                r = len(inter) / len(true_leaves) if true_leaves else 0.0
                f = 2 * (p * r) / (p + r) if (p + r) > 0 else 0.0
                
            case_path_prec += weight * p
            case_path_rec += weight * r
            case_path_f1 += weight * f
        
        # 惩罚项
        hallucinated_roots = set(pred.ppath.keys()) - set(current_gt_ips)
        if hallucinated_roots:
            penalty = len(hallucinated_roots) * 0.1 
            case_path_f1 = max(0.0, case_path_f1 - penalty)
            case_path_prec = max(0.0, case_path_prec - penalty)

        return {"f1": case_path_f1, "prec": case_path_prec, "rec": case_path_rec, "is_valid": True}

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
        # 获取 IPs
        label_file = os.path.join(dir_name, "label.json")
        labels = DataIOHandler.load_json(label_file) or []
        labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
        
        gt_ips = []
        for label in labels_sorted[:3]:
            for node in label.get("abnormal_node", []):
                if "ip" in node and node["ip"] not in gt_ips:
                    gt_ips.append(node["ip"])
                    
        # 获取 Topology Path
        path_file = os.path.join(dir_name, "label_propath.json")
        path_data = DataIOHandler.load_json(path_file) or {}
        gt_ppath = {}
        if isinstance(path_data, list):
            for item in path_data: gt_ppath.update(item)
        else:
            gt_ppath = path_data

        return GroundTruth(ips=gt_ips, ppath=gt_ppath)

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

        original_dir = "/home/sbp/lixinyang/pingmesh/data/pingmesh_original"
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
                # 新增 top2, top4 的聚合字段
                "sum_top1": 0, "sum_top2": 0, "sum_top3": 0, "sum_top4": 0, "sum_top5": 0, 
                "sum_expected_steps": 0.0, "sum_min_cost": 0.0, "sum_max_cost": 0.0, 
                "valid_path_cases": 0, "sum_path_f1": 0.0, "sum_path_prec": 0.0, "sum_path_rec": 0.0,
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
            topo_res = self.evaluator.evaluate_topology(gt, pred)

            is_silent = self.io.is_silent_case(dir_name)
            cat = "silent" if is_silent else "normal"

            case_log = {
                "name": dir_name,
                "is_silent": is_silent,
                "pred_ips_dedup": rank_res["pred_ips_dedup"],
                "gt_ips": gt.ips,
                "expected_steps": round(rank_res["expected_steps"], 2),
                "top1_hit": rank_res["top1_hit"],
                "propagation_path": pred.ppath,
                "path_f1": round(topo_res["f1"], 4) if topo_res["is_valid"] else None,
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
                
                metrics[target_cat]["sum_expected_steps"] += rank_res["expected_steps"]
                metrics[target_cat]["sum_min_cost"] += rank_res["min_cost"]
                metrics[target_cat]["sum_max_cost"] += rank_res["max_cost"]

                if topo_res["is_valid"]:
                    metrics[target_cat]["valid_path_cases"] += 1
                    metrics[target_cat]["sum_path_f1"] += topo_res["f1"]
                    metrics[target_cat]["sum_path_prec"] += topo_res["prec"]
                    metrics[target_cat]["sum_path_rec"] += topo_res["rec"]

                if rank_res["is_failed"]: 
                    metrics[target_cat]["failure_cases"].append(case_log)
                else: 
                    metrics[target_cat]["success_cases"].append(case_log)

        result_summary = {}
        for c in categories:
            m = metrics[c]
            actual_eval_cases = len(m["failure_cases"]) + len(m["success_cases"])
            
            if actual_eval_cases == 0:
                result_summary[c] = {"status": f"No {c} cases found."}
                continue

            # 计算百分比
            top1_acc_percent = (m["sum_top1"] / actual_eval_cases) * 100
            top2_acc_percent = (m["sum_top2"] / actual_eval_cases) * 100
            top3_acc_percent = (m["sum_top3"] / actual_eval_cases) * 100
            top4_acc_percent = (m["sum_top4"] / actual_eval_cases) * 100
            top5_acc_percent = (m["sum_top5"] / actual_eval_cases) * 100
            avg_expected_steps = m["sum_expected_steps"] / actual_eval_cases
            
            # 计算归一化得分
            avg_min_cost = m["sum_min_cost"] / actual_eval_cases
            avg_max_cost = m["sum_max_cost"] / actual_eval_cases
            if avg_max_cost > avg_min_cost:
                norm_score = 1 - (avg_expected_steps - avg_min_cost) / (avg_max_cost - avg_min_cost)
            else:
                norm_score = 1.0 if avg_expected_steps <= avg_min_cost else 0.0

            vpc = m["valid_path_cases"]

            result_summary[c] = {
                "ranking_metrics": {
                    "Total Evaluated Cases": actual_eval_cases,
                    "Top-1 Acc (%)": round(top1_acc_percent, 2),
                    "Top-2 Acc (%)": round(top2_acc_percent, 2),
                    "Top-3 Acc (%)": round(top3_acc_percent, 2),
                    "Top-4 Acc (%)": round(top4_acc_percent, 2),
                    "Top-5 Acc (%)": round(top5_acc_percent, 2),
                    "期望排查步长": round(avg_expected_steps, 2),
                    "归一化排查得分": round(max(0.0, norm_score), 4)  
                },
                "path_topology_metrics": {
                    "valid_eval_cases": vpc,
                    "weighted_path_f1_score": round(m["sum_path_f1"] / vpc if vpc > 0 else 0.0, 4),
                    "weighted_path_precision": round(m["sum_path_prec"] / vpc if vpc > 0 else 0.0, 4),
                    "weighted_path_recall": round(m["sum_path_rec"] / vpc if vpc > 0 else 0.0, 4)
                },
                "failed_cases_count": len(m["failure_cases"]),
                "success_cases_count": len(m["success_cases"]),
                "_raw_failures": m["failure_cases"],
                "_raw_successes": m["success_cases"]
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

        d_res = self._evaluate_stage(res_data, "draft_response", "draft_prompt")
        # 仅当数据中存在非空 refine 结果时才评估，避免基线输出全 0
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
            "draft_evaluation": extract_pure_metrics(d_res),
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
    file_path = "/home/sbp/lixinyang/pingmesh/data/res/1778218041/res.json"
    
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