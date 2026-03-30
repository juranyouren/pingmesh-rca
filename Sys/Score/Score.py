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
        """
        res_data = self.load_res_data()
        total_cases = len(res_data)
        
        total_expected_cost = 0.0
        total_min_possible_cost = 0.0  # 理想状态下的累计成本
        total_max_possible_cost = 0.0  # 最差状态下的累计成本
        perfect_hits = 0 
        
        failure_cases = []
        MISSING_PENALTY = 3 
        probs = [0.54, 0.27, 0.18] # 对应 gt_ips 的权重
        
        for rd in res_data:
            name=rd.get("dir")
            response=rd.get("response")
            gt_ips = self.get_groundtruth_ips(name)
            if not gt_ips:
                continue
                
            pred_result = self.extract_ips_and_ppath_from_response(response)
            ppath = pred_result.get("propagation_path")
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

            total_expected_cost += case_expected_cost
            total_min_possible_cost += case_min_cost
            total_max_possible_cost += case_max_cost

            if pred_ips and gt_ips and pred_ips[0] == gt_ips[0]:
                perfect_hits += 1
                
            if pred_ips and gt_ips and gt_ips[0] not in pred_ips:
                failure_cases.append({
                    "name": name,
                    "pred_ips": pred_ips,
                    "gt_ips": gt_ips,
                    "cost": round(case_expected_cost, 2),
                    "propagation_path": ppath,
                    "pmt":rd["prompt"],
                    "response":rd["response"]
                })

        # 计算平均值
        avg_expected_cost = total_expected_cost / total_cases if total_cases > 0 else 0
        avg_min_cost = total_min_possible_cost / total_cases if total_cases > 0 else 0
        avg_max_cost = total_max_possible_cost / total_cases if total_cases > 0 else 0

        # 归一化计算 (0.0 - 1.0)
        # 分母防 0 处理：如果 max 和 min 一样（通常不会），得分给 1
        if avg_max_cost > avg_min_cost:
            normalized_score = 1 - (avg_expected_cost - avg_min_cost) / (avg_max_cost - avg_min_cost)
        else:
            normalized_score = 1.0 if avg_expected_cost <= avg_min_cost else 0.0

        summary = {
            "ranking_metrics": {
                "avg_expected_cost": round(avg_expected_cost, 4),
                "normalized_rank_score": round(max(0, normalized_score), 4), # 确保不为负数
                "perfect_top1_hit_rate": round(perfect_hits / total_cases, 4) if total_cases > 0 else 0
            },
            "total_cases": total_cases,
            "failed_cases_count": len(failure_cases)
        }
        summary_file_path = os.path.join(self.failure_dir, f"sum.json")
        with open(summary_file_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=4, ensure_ascii=False)
        if failure_cases:
            os.makedirs(self.failure_dir, exist_ok=True)
            failure_file_path = os.path.join(self.failure_dir, f"ranking_failures.json")
            with open(failure_file_path, 'w', encoding='utf-8') as f:
                json.dump(failure_cases, f, indent=4, ensure_ascii=False)
            print(f"已将 {len(failure_cases)} 个排序失败案例保存至: {failure_file_path}")

        return summary
# ================= 使用示例 =================
if __name__ == "__main__":
    scorer = Score(res_file_path="/home/sbp/lixinyang/pingmesh/data/res/1774686355/res.json")
    overall_summary = scorer.calculate_metrics()

    print("======= 整体评估结果 =======")
    print(json.dumps(overall_summary, indent=4, ensure_ascii=False))
    pass