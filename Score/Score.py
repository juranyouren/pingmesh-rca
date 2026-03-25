import json
import os
import re
from collections import defaultdict

class Score:
    def __init__(self, res_file_path="res.json"):
        """
        初始化Score类
        :param res_file_path: 包含llm结果的json文件路径
        """
        self.res_file_path = res_file_path
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

    def extract_ips_from_response(self, response_text):
        """
        在response中提取出ip
        """
        if not response_text:
            return []
        
        extracted_ips = self.ip_pattern.findall(response_text)
        
        # 去重并保持原有出现的顺序
        seen = set()
        unique_extracted_ips = [ip for ip in extracted_ips if not (ip in seen or seen.add(ip))]
        return unique_extracted_ips

    def calculate_metrics(self):
        """
        计算一系列metric，包括 Precision, Recall, F1, 并且可计算整体平均值
        """
        res_data = self.load_res_data()
        
        all_metrics = []
        total_stats = {"TP": 0, "FP": 0, "FN": 0}

        for name,response in res_data.items():


            
            # 1. 获取 Ground Truth IPs
            gt_ips = self.get_groundtruth_ips(name)
            
            # 2. 提取 LLM 回答中的 IPs
            pred_ips = self.extract_ips_from_response(response)
            
            # 3. 计算单条样本的 TP, FP, FN
            gt_set = set(gt_ips)
            pred_set = set(pred_ips)
            
            tp = len(gt_set.intersection(pred_set))
            fp = len(pred_set - gt_set)
            fn = len(gt_set - pred_set)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            
            # 记录整体情况
            total_stats["TP"] += tp
            total_stats["FP"] += fp
            total_stats["FN"] += fn
            
            case_metric = {
                "name": name,
                "groundtruth_ips": gt_ips,
                "predicted_ips": pred_ips,
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "precision": precision,
                "recall": recall,
                "f1_score": f1
            }
            all_metrics.append(case_metric)

        # 4. 计算宏观/微观全局指标
        overall_tp = total_stats["TP"]
        overall_fp = total_stats["FP"]
        overall_fn = total_stats["FN"]
        
        overall_precision = overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) > 0 else 0.0
        overall_recall = overall_tp / (overall_tp + overall_fn) if (overall_tp + overall_fn) > 0 else 0.0
        overall_f1 = (2 * overall_precision * overall_recall) / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0.0

        summary = {
            "overall_precision": overall_precision,
            "overall_recall": overall_recall,
            "overall_f1_score": overall_f1,
            "total_cases": len(res_data)
        }

        return all_metrics, summary

# ================= 使用示例 =================
if __name__ == "__main__":
    scorer = Score("/home/sbp/lixinyang/pingmesh/data/res.json")
    detailed_metrics, overall_summary = scorer.calculate_metrics()
    
    print("======= 整体评估结果 =======")
    print(json.dumps(overall_summary, indent=4, ensure_ascii=False))
    
    print("\n======= 详细结果 =======")
    for metric in detailed_metrics:
        print(json.dumps(metric, indent=4, ensure_ascii=False))
    pass