import json
import os
import re
from collections import defaultdict
import time

class Score:
    def __init__(self, res_file_path="res.json",failure_dir="/home/sbp/lixinyang/pingmesh/SkillBank/failure_cases"):
        """
        初始化Score类
        :param res_file_path: 包含llm结果的json文件路径
        """
        self.res_file_path = res_file_path
        self.failure_dir=failure_dir
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
            "ip": ips[-1] if ips else None,
            "propagation_path": ppaths[-1] if ppaths else None
        }

    def calculate_metrics(self):
        """
        计算一系列metric，包括 Precision, Recall, F1, 并且可计算整体平均值。
        新逻辑：pred_ip只有一个，只要存在于gt_ips中，即视为正确命中（Hit）。
        """
        res_data = self.load_res_data()
        
        all_metrics = []
        total_stats = {"TP": 0, "FP": 0, "FN": 0}
        failure_cases=[]

        for name, response in res_data.items():
            # 1. 获取 Ground Truth IPs
            gt_ips = self.get_groundtruth_ips(name)
            
            # 2. 提取 LLM 回答中的 IP 
            # (兼容处理：防止上一步提取方法返回的是列表、字典或空值)
            pred_result = self.extract_ips_and_ppath_from_response(response)
            if isinstance(pred_result, list):
                pred_ip = pred_result[0] if pred_result else None
            elif isinstance(pred_result, dict):
                pred_ip = pred_result.get("ip")
            else:
                pred_ip = pred_result
            
            # 3. 计算单条样本的 TP, FP, FN
            tp = 0
            fp = 0
            fn = 0
            
            # 核心逻辑：只要预测的 IP 不为空，且在 groundtruth 列表中，就算命中
            if pred_ip and pred_ip in gt_ips:
                tp = 1  # 命中目标
            else:
                # 未命中时，区分是误报还是漏报
                if pred_ip:
                    fp = 1  # 预测了一个 IP，但不在正确答案里 (误报)
                fn = 1      # 没能命中正确答案 (漏报)
                label_file_path = os.path.join(name, "label.json")
                raw_label_data = []
                if os.path.exists(label_file_path):
                    with open(label_file_path, 'r', encoding='utf-8') as f:
                        raw_label_data = json.load(f)

                failure_cases.append({
                    "name": name,
                    "response": response,
                    "predicted_ip": pred_ip,
                    "groundtruth_ips": gt_ips
                })
            
            # 记录整体情况
            total_stats["TP"] += tp
            total_stats["FP"] += fp
            total_stats["FN"] += fn
            

        # 4. 计算宏观/微观全局指标
        overall_tp = total_stats["TP"]
        overall_fp = total_stats["FP"]
        overall_fn = total_stats["FN"]
        total_cases = len(res_data)
        
        overall_precision = overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) > 0 else 0.0
        overall_recall = overall_tp / (overall_tp + overall_fn) if (overall_tp + overall_fn) > 0 else 0.0
        overall_f1 = (2 * overall_precision * overall_recall) / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0.0

        summary = {
            "overall_accuracy": overall_tp / total_cases if total_cases > 0 else 0.0, # 修复了原代码：TP/总样本数 是 Accuracy
            "overall_precision": overall_precision, # 真实的全局 Precision
            "overall_recall": overall_recall,
            "overall_f1_score": overall_f1,
            "total_cases": total_cases
        }

        if failure_cases:
            timest=int(time.time())
            os.makedirs(self.failure_dir, exist_ok=True)
            failure_file_path = os.path.join(self.failure_dir, f"{timest}_failed_cases.json")
            with open(failure_file_path, 'w', encoding='utf-8') as f:
                json.dump(failure_cases, f, indent=4, ensure_ascii=False)
            print(f"已将 {len(failure_cases)} 个失败案例保存至: {failure_file_path}")

        return summary

# ================= 使用示例 =================
if __name__ == "__main__":
    scorer = Score(res_file_path="/home/sbp/lixinyang/pingmesh/data/res/1774502446/res.json")
    overall_summary = scorer.calculate_metrics()

    print("======= 整体评估结果 =======")
    print(json.dumps(overall_summary, indent=4, ensure_ascii=False))
    pass