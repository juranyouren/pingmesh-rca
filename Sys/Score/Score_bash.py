import json
import os
import re
from collections import defaultdict
import time

class Score:
    def __init__(self, res_file_path="res.json"):
        """
        初始化Score类
        :param res_file_path: 包含llm结果的json文件路径
        """
        self.res_file_path = res_file_path
        self.failure_dir=os.path.dirname(self.res_file_path)
        # 匹配IPv4地址的正则表达式
        self.ip_pattern = re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')

    def get_groundtruth_propath(self, name):
        """
        从 label.json 中读取真实的传播路径 (gt_propath)
        *注意*: 这里假设 label.json 中有 direct_path 或 propagation_path 字段，您需要根据实际结构微调。
        """
        label_file_path = os.path.join(name, "label_propath.json")
        if not os.path.exists(label_file_path):
            return ""
        res={}
        with open(label_file_path, 'r', encoding='utf-8') as f:
            labels = json.load(f)
        if isinstance(labels, list) and len(labels) > 0:
            for i in labels:
                res.update(i)
        else:
            res=labels

        return res

    def load_res_data(self):
        """
        从res.json读取数据
        假设格式为: [{"name": "case1", "response": "llm output..."}, ...]
        """
        if not os.path.exists(self.res_file_path):
            raise FileNotFoundError(f"找不到文件: {self.res_file_path}")
        
        with open(self.res_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_groundtruth_ips(self, name):
        """
        根据name，在name/label.json的文件中读取label，提取前三个设备的ip作为groundtruth
        """
        label_file_path = os.path.join(name, "label.json")
        if not os.path.exists(label_file_path):
            print(f"警告: 找不到标签文件 {label_file_path}")
            return []

        with open(label_file_path, 'r', encoding='utf-8') as f:
            labels = json.load(f)

        # 根据 ranking 排序，确保提取的是前三个
        labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
        
        groundtruth_ips = []
        # 只取排名前3的设备
        for label in labels_sorted[:3]:
            abnormal_nodes = label.get("abnormal_node", [])
            for node in abnormal_nodes:
                if "ip" in node:
                    groundtruth_ips.append(node["ip"])
        
        # 去重并保持原有顺序
        seen = set()
        unique_groundtruth_ips = [ip for ip in groundtruth_ips if not (ip in seen or seen.add(ip))]
        return unique_groundtruth_ips

    def extract_ips_and_ppath_from_response(self, response_text):
        """
        在response中提取出特定格式的ip和propagation_path，例如：
        最后，综合所有信息，受影响的传播路径在物理拓扑中的交集设备是LEAF设备29.104.183.15。
        </think>
        ```json
            {
                "ip": "29.104.183.15",
                "propagation_path": "26.88.130.9 > 29.104.160.168 (Leaf) > 29.104.183.15 (Leaf)"
            }
        ```
        注意不要匹配到其他json了，匹配最后一个json是不错的策略
        """
        if not response_text:
            return {"ip": None, "propagation_path": None}

        # 策略 1：匹配所有的 ```json ... ``` 块，提取最后一个
        json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL | re.IGNORECASE)
        json_blocks = json_pattern.findall(response_text)
        
        if json_blocks:
            last_json_str = json_blocks[-1]
            try:
                # 尝试解析标准 JSON
                data = json.loads(last_json_str)
                return {
                    "ip": data.get("ip"),
                    "propagation_path": data.get("propagation_path")
                }
            except json.JSONDecodeError:
                pass # 如果解析失败（例如大模型生成的 JSON 破损），则进入降级策略

        # 策略 2：降级策略（Fallback）
        # 如果大模型没有输出 ```json 包裹，或者 JSON 格式有语法错误导致解析失败，直接用正则硬提取
        ip_pattern = re.compile(r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"')
        ppath_pattern = re.compile(r'"propagation_path"\s*:\s*"([^"]+)"')
        
        ips = ip_pattern.findall(response_text)
        ppaths = ppath_pattern.findall(response_text)
        
        return {
            "ip": ips if ips else None,
            "propagation_path": ppaths[-1] if ppaths else None
        }
    
    def calculate_metrics(self):
        """
        基于概率排序的期望排查成本评测逻辑 (Expected Search Cost) 并进行归一化。
        新增：gt[0]的 Top-1/2/3 命中率，以及 gt[0], gt[1], gt[2] 的平均排名。
        """
        res_data = self.load_res_data()
        total_cases = len(res_data)
        
        total_expected_cost = 0.0
        total_min_possible_cost = 0.0  # 理想状态下的累计成本
        total_max_possible_cost = 0.0  # 最差状态下的累计成本
        perfect_hits = 0 
        
        # ---- 新增 ppath 拓扑评分统计 ----
        valid_path_cases = 0
        total_path_f1 = 0.0
        total_path_prec = 0.0
        total_path_rec = 0.0


        # ---- 新增指标统计初始化 ----
        hits_top1 = 0
        hits_top2 = 0
        hits_top3 = 0
        
        # 记录 gt[0], gt[1], gt[2] 出现的总次数和累计排名
        gt_counts = {0: 0, 1: 0, 2: 0}
        gt_ranks_sum = {0: 0.0, 1: 0.0, 2: 0.0}
        # ----------------------------

        failure_cases = []
        MISSING_PENALTY = 10 
        probs = [0.54, 0.27, 0.18] # 对应 gt_ips 的权重
        
        for rd in res_data:
            name=rd.get("dir")
            response=rd.get("response")
            gt_ips = self.get_groundtruth_ips(name)
            gt_ppath=self.get_groundtruth_propath(name)
            if not gt_ips:
                continue
                
            pred_result = self.extract_ips_and_ppath_from_response(response)
            ppath_raw = pred_result.get("propagation_path")
            pred_raw = pred_result.get("ip")
            
            if not isinstance(pred_raw, list):
                pred_raw = [pred_raw] if pred_raw else []
                
            pred_ips = []
            for ip in pred_raw:
                if ip not in pred_ips:
                    pred_ips.append(ip)

            case_expected_cost = 0.0
            case_min_cost = 0.0
            case_max_cost = 0.0
            
            # 确定当前预测列表的长度，用于计算惩罚上限
            pred_len = len(pred_ips)

            for i, gt_ip in enumerate(gt_ips):
                # 防止 gt_ips 长度超过 probs 定义范围
                prob = probs[i] if i < len(probs) else 0.0
                
                # 1. 计算实际成本
                if gt_ip in pred_ips:
                    steps_to_find = pred_ips.index(gt_ip) + 1
                else:
                    steps_to_find = pred_len + MISSING_PENALTY
                case_expected_cost += prob * steps_to_find
                
                # 2. 计算理想成本 (假设它就在它该在的位置)
                case_min_cost += prob * (i + 1)
                
                # 3. 计算最差成本 (假设完全没预测到)
                case_max_cost += prob * (pred_len + MISSING_PENALTY)
                
                # ---- 新增：记录 gt[0], gt[1], gt[2] 的排名 ----
                if i < 3:
                    gt_counts[i] += 1
                    gt_ranks_sum[i] += steps_to_find # 未命中时采用和成本一样的惩罚排名
                
            # ================= 2. gt_ppath 影响面拓扑评分逻辑 =================
            case_path_f1 = 0.0
            case_path_prec = 0.0
            case_path_rec = 0.0
            
            # 尝试将预测的 ppath 解析为字典
            pred_ppath_dict = {}
            if isinstance(ppath_raw, str):
                try:
                    pred_ppath_dict = json.loads(ppath_raw)
                except json.JSONDecodeError:
                    pass
            elif isinstance(ppath_raw, dict):
                pred_ppath_dict = ppath_raw
                
            # 只有在 gt_ppath 存在且为字典的情况下才进行拓扑评分
            if isinstance(gt_ppath, dict) and gt_ppath:
                valid_path_cases += 1
                
                # 当前用例的权重归一化（防止 gt 节点数不足3个时总分达不到 1.0）
                current_gt_ips = list(gt_ppath.keys())[:3]
                current_weights = probs[:len(current_gt_ips)]
                weight_sum = sum(current_weights) if sum(current_weights) > 0 else 1.0
                norm_weights = [w / weight_sum for w in current_weights]
                
                for i, g_ip in enumerate(current_gt_ips):
                    weight = norm_weights[i]
                    true_leaves = set(gt_ppath[g_ip].get("affected_nodes", []))
                    
                    pred_leaves = set()
                    if g_ip in pred_ppath_dict and isinstance(pred_ppath_dict[g_ip], dict):
                        pred_leaves = set(pred_ppath_dict[g_ip].get("affected_nodes", []))
                    
                    # 子树 Precision & Recall 计算
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
                
                # 惩罚项：预测了不存在于 GT 中的幻觉根节点 IP
                hallucinated_roots = set(pred_ppath_dict.keys()) - set(current_gt_ips)
                if hallucinated_roots:
                    penalty = len(hallucinated_roots) * 0.1 # 每个捏造的 IP 扣除 0.1 分
                    case_path_f1 = max(0.0, case_path_f1 - penalty)
                    case_path_prec = max(0.0, case_path_prec - penalty)
                
                total_path_f1 += case_path_f1
                total_path_prec += case_path_prec
                total_path_rec += case_path_rec
            else:
                print(name)
            total_expected_cost += case_expected_cost
            total_min_possible_cost += case_min_cost
            total_max_possible_cost += case_max_cost

            # 原有 Top 1 命中逻辑
            if pred_ips and gt_ips and pred_ips[0] == gt_ips[0]:
                perfect_hits += 1
            
            # ---- 新增：gt[0] 的 Top1/2/3 命中统计 ----
            if gt_ips:
                gt_primary = gt_ips[0]
                if gt_primary in pred_ips:
                    idx = pred_ips.index(gt_primary)
                    if idx < 1: hits_top1 += 1
                    if idx < 2: hits_top2 += 1
                    if idx < 3: hits_top3 += 1
            # ----------------------------------------
                
            if pred_ips and gt_ips and gt_ips[0] not in pred_ips or case_expected_cost>6:
                failure_cases.append({
                    "name": name,
                    "pred_ips": pred_ips,
                    "gt_ips": gt_ips,
                    "cost": round(case_expected_cost, 2),
                    "propagation_path": ppath_raw,
                    "path_f1": round(case_path_f1, 4) if (isinstance(gt_ppath, dict) and gt_ppath) else None,
                    "pmt":rd["prompt"],
                    "response":rd["response"]
                })

        # 计算平均值
        avg_expected_cost = total_expected_cost / total_cases if total_cases > 0 else 0
        avg_min_cost = total_min_possible_cost / total_cases if total_cases > 0 else 0
        avg_max_cost = total_max_possible_cost / total_cases if total_cases > 0 else 0

        # 归一化计算 (0.0 - 1.0)
        if avg_max_cost > avg_min_cost:
            normalized_score = 1 - (avg_expected_cost - avg_min_cost) / (avg_max_cost - avg_min_cost)
        else:
            normalized_score = 1.0 if avg_expected_cost <= avg_min_cost else 0.0

        # ---- 新增：计算 Top-K 命中率和平均排名 ----
        hr_top1 = hits_top1 / total_cases if total_cases > 0 else 0
        hr_top2 = hits_top2 / total_cases if total_cases > 0 else 0
        hr_top3 = hits_top3 / total_cases if total_cases > 0 else 0
        
        mr_gt0 = gt_ranks_sum[0] / gt_counts[0] if gt_counts[0] > 0 else 0
        mr_gt1 = gt_ranks_sum[1] / gt_counts[1] if gt_counts[1] > 0 else 0
        mr_gt2 = gt_ranks_sum[2] / gt_counts[2] if gt_counts[2] > 0 else 0
        # ------------------------------------------
        avg_path_f1 = total_path_f1 / valid_path_cases if valid_path_cases > 0 else 0.0
        avg_path_prec = total_path_prec / valid_path_cases if valid_path_cases > 0 else 0.0
        avg_path_rec = total_path_rec / valid_path_cases if valid_path_cases > 0 else 0.0

        summary = {
            "ranking_metrics": {
                "avg_expected_cost": round(avg_expected_cost, 4),
                "normalized_rank_score": round(max(0, normalized_score), 4),
                "perfect_top1_hit_rate": round(perfect_hits / total_cases, 4) if total_cases > 0 else 0,
                
                # 写入新增指标
                "hit_rate_top1_gt0": round(hr_top1, 4),    # 和 perfect_top1_hit_rate 结果一致
                "hit_rate_top2_gt0": round(hr_top2, 4),
                "hit_rate_top3_gt0": round(hr_top3, 4),
                "mean_rank_gt0": round(mr_gt0, 4),
                "mean_rank_gt1": round(mr_gt1, 4),
                "mean_rank_gt2": round(mr_gt2, 4)
            },
            "path_topology_metrics": {
                "valid_eval_cases": valid_path_cases,
                "weighted_path_f1_score": round(avg_path_f1, 4),
                "weighted_path_precision": round(avg_path_prec, 4),
                "weighted_path_recall": round(avg_path_rec, 4)
            },
            "total_cases": total_cases,
            "failed_cases_count": len(failure_cases)
        }
        
        # 确保目录存在（建议把目录创建提前到存 sum.json 前，防止报错）
        os.makedirs(self.failure_dir, exist_ok=True)
        
        summary_file_path = os.path.join(self.failure_dir, f"sum.json")
        with open(summary_file_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
            
        if failure_cases:
            failure_file_path = os.path.join(self.failure_dir, f"ranking_failures.json")
            with open(failure_file_path, 'w', encoding='utf-8') as f:
                json.dump(failure_cases, f, indent=4, ensure_ascii=False)
            print(f"已将 {len(failure_cases)} 个排序失败案例保存至: {failure_file_path}")

        return summary

# ================= 使用示例 =================
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="对 LLM 推理结果进行评分并提取失败 Case")
    parser.add_argument("--res_path", type=str, required=True, help="inference 阶段生成的 res.json 的绝对路径")
    args = parser.parse_args()

    # 检查文件是否存在
    if not os.path.exists(args.res_path):
        print(f"[错误] 找不到推理结果文件: {args.res_path}")
        sys.exit(1)

    scorer = Score(res_file_path=args.res_path)
    overall_summary = scorer.calculate_metrics()

    print("======= 整体评估结果 =======")
    print(json.dumps(overall_summary, indent=4, ensure_ascii=False))