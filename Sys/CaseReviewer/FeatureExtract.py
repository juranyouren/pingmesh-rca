import re
import json

class FailedCaseFeatureExtractor:
    def __init__(self, item: dict):
        """
        传入的内容为你在 draft_ranking_failures.json 中的单个 case dict
        """
        self.item = item
        self.pred_ips = item.get("pred_ips", [])
        self.gt_ips = item.get("gt_ips", [])
        self.pmt = item.get("pmt", "")
        
        # 1. 用正则从 pmt 中解析出专家工具打分排行榜 (Rank List)
        self.rank_data = self._parse_ranks(self.pmt)
        # 2. 从 pmt 中提取 Nodes 数据块
        self.nodes_data = self._parse_nodes(self.pmt)

    def _parse_ranks(self, pmt_text: str) -> dict:
        """从 prompt 中提取各个 IP 的得分和角色"""
        rank_dict = {}
        # 匹配格式: Rank X: [IP: 11.x.x.x] | [角色: SPINE] | [Cross: 2] | ... 综合嫌疑度: 8.13 分
        pattern = r"Rank \d+.*?: \[IP: (.*?)\] \| \[角色: (.*?)\] \| \[Cross: (\d+)\].*?综合嫌疑度: ([\d\.]+) 分"
        matches = re.findall(pattern, pmt_text)
        for ip, role, cross, score in matches:
            rank_dict[ip] = {
                "role": role,
                "cross": int(cross),
                "score": float(score)
            }
        return rank_dict

    def _parse_nodes(self, pmt_text: str) -> dict:
        """粗略从 prompt 提取 Nodes 字典以便获取告警集合"""
        try:
            nodes_match = re.search(r"## 3\. Nodes.*?\n(\{.*\})", pmt_text, re.DOTALL)
            if nodes_match:
                return json.loads(nodes_match.group(1))
        except Exception:
            pass
        return {}

    def extract_score_delta_feature(self) -> str:
        """特征 1：分差与等价特征诊断"""
        if not self.pred_ips or not self.gt_ips or not self.rank_data:
            return ""
            
        pred_ip = self.pred_ips[0] # 取大模型最信赖的第一个错判IP
        
        warnings = []
        for gt_ip in self.gt_ips:
            if gt_ip in self.pred_ips: continue # 没漏报的不管
            
            pred_score = self.rank_data.get(pred_ip, {}).get("score", 0)
            gt_score = self.rank_data.get(gt_ip, {}).get("score", 0)
            pred_role = self.rank_data.get(pred_ip, {}).get("role", "UNKNOWN")
            gt_role = self.rank_data.get(gt_ip, {}).get("role", "UNKNOWN")
            
            delta = abs(pred_score - gt_score)
            
            if delta < 0.2 and pred_role == gt_role:
                warnings.append(
                    f"  - ⚡ 【严重等价漏报】：漏报的真实根因 ({gt_ip}) 与误判节点 ({pred_ip}) 分差仅为 {delta:.2f}！"
                    f"且两者角色均为 {gt_role}。大模型被排名序号（Rank）欺骗，犯了单因谬误，忽略了双上联并发故障事实！"
                )
            elif gt_score > pred_score:
                warnings.append(
                    f"  - ❌ 【反逻辑降级】：漏报的真实根因 ({gt_ip}, 得分:{gt_score}) 得分明明高于误判节点 ({pred_ip}, 得分:{pred_score})，大模型完全无视了专家打分！"
                )
                
        if warnings:
            return "【分差特征分析】:\n" + "\n".join(warnings)
        return "【分差特征分析】: 未发现极小分差诱导。"

    def extract_contrastive_alarm_signature(self) -> str:
        """特征 2：对比性告警签名 (提取诱饵告警与盲点告警)"""
        if not self.nodes_data: return ""
        
        # 获取所有预测节点的告警并集
        pred_alarms = set()
        for node_info in self.nodes_data.values():
            if node_info.get("mgmt_ip") in self.pred_ips:
                pred_alarms.update([a.get("name") if isinstance(a, dict) else a for a in node_info.get("alarms", [])])
                pred_alarms.update([l.get("name") if isinstance(l, dict) else l for l in node_info.get("logs", [])])
                
        # 获取所有漏报 GT 的告警并集
        missed_gts = [ip for ip in self.gt_ips if ip not in self.pred_ips]
        gt_alarms = set()
        for node_info in self.nodes_data.values():
            if node_info.get("mgmt_ip") in missed_gts:
                gt_alarms.update([a.get("name") if isinstance(a, dict) else a for a in node_info.get("alarms", [])])
                gt_alarms.update([l.get("name") if isinstance(l, dict) else l for l in node_info.get("logs", [])])

        # 集合减法：独有特征
        blind_spots = gt_alarms - pred_alarms  # 大模型没注意到的盲点告警
        bait_alarms = pred_alarms - gt_alarms  # 骗过大模型的诱饵告警
        common_alarms = gt_alarms & pred_alarms # 共性告警
        
        report = "【对比性告警签名分析】:\n"
        if blind_spots:
            report += f"  - 盲点告警 (真实根因独有，大模型忽略了它): {list(blind_spots)}\n"
        if bait_alarms:
            report += f"  - 诱饵告警 (大模型被这些表面告警骗了): {list(bait_alarms)}\n"
        if common_alarms:
            report += f"  - 共性告警 (导致模型无法区分的重合区): {list(common_alarms)}\n"
            
        return report

    def generate_feature_report(self) -> str:
        """生成供大模型学习的显性数据特征报告"""
        res = "====== Python 数据特征增强报告 (辅助审查) ======\n"
        res += self.extract_score_delta_feature() + "\n\n"
        res += self.extract_contrastive_alarm_signature() + "\n"
        res += "================================================\n"
        return res

# --- 测试一下 ---
# 假设 case_item 是你那个漏掉 .32 的 Failed Case
# extractor = FailedCaseFeatureExtractor(case_item)
# print(extractor.generate_feature_report())