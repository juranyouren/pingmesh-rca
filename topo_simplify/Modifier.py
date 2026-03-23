import json
import random
import os
import copy

class Modifier:
    def __init__(self, info_path):
        """
        初始化 Modifier 类
        :param json_file: 包含节点数据的 JSON 文件路径
        """
        self.info_path = info_path
        self.alarm_content=self._load_alarm_content()
        self.json_file=os.path.dirname(info_path)
        self.json_file=os.path.join(self.json_file,f"merged_pingmesh-{self.alarm_content['csn']}-全链路.json")
        self.nodes = self._load_nodes()
        self.destip=self.alarm_content["dst_tunnel_ip"]
        self.srcip=self.alarm_content["src_tunnel_ip"]

        # 生成以 IP 为索引的节点字典
        self.ipindexed_nodes = {}
        if self.nodes:
            self._generate_ipindexed_nodes()
    def _load_nodes(self):
        """内部方法：从 JSON 文件读取节点数据"""
        if not os.path.exists(self.json_file):
            print(f"文件不存在: {self.json_file}")
            return {}
            
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取文件失败 {self.json_file}: {e}")
            return {}

    def _load_alarm_content(self):
        """内部方法：从 JSON 文件读取告警数据"""
        if not os.path.exists(self.info_path):
            print(f"文件不存在: {self.info_path}")
            return {}
            
        try:
            with open(self.info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取文件失败 {self.info_path}: {e}")
            return {}

    def _generate_ipindexed_nodes(self):
        """
        内部方法：将以 name 索引的 nodes 转换为以 ip 索引的 ipindexed_nodes。
        同时将关联的边（linked_to, linked_from）中的 name 替换为 ip。
        """
        # 1. 建立 name 到 ip 的映射表
        name_to_ip = {}
        for name, data in self.nodes.items():
            # 假设节点数据中包含 'ip' 字段，如果没有则回退使用 name 本身
            node_ip = data.get("mgmt_ip", name) 
            name_to_ip[name] = node_ip

        # 2. 构建 ipindexed_nodes
        for name, data in self.nodes.items():
            node_ip = name_to_ip[name]
            
            # 使用深拷贝避免修改原始 nodes 数据
            node_copy = copy.deepcopy(data)
            node_copy["original_name"] = name  # 保留原始名称备用
            
            

            self.ipindexed_nodes[node_ip] = node_copy

    def topo_simplify(self, k):
        """
        拓扑简化：随机剪枝，保留 k 个节点
        :param k: 剪枝后保留的节点数量阈值
        """
        if not self.nodes:
            print("节点数据为空，无法进行剪枝。")
            return

        current_count = len(self.nodes)
        if k >= current_count:
            print(f"设定的阈值 k ({k}) 大于等于当前节点数 ({current_count})，无需剪枝。")
            return

        # 1. 随机选择要保留的 k 个节点
        all_node_names = list(self.nodes.keys())
        nodes_to_keep = set(random.sample(all_node_names, k))
        nodes_to_delete = set(all_node_names) - nodes_to_keep

        # 2. 从字典中删除不需要的节点
        for node_name in nodes_to_delete:
            del self.nodes[node_name]

        # 3. 清理剩余节点中的关联边（去除指向被删节点的连接）
        for node_name, node_data in self.nodes.items():
            # 使用列表推导式过滤掉已经被删除的节点
            node_data["linked_from"] = [n for n in node_data.get("linked_from", []) if n in nodes_to_keep]
            node_data["linked_to"] = [n for n in node_data.get("linked_to", []) if n in nodes_to_keep]
            node_data["verified_hops_to"] = [n for n in node_data.get("verified_hops_to", []) if n in nodes_to_keep]

        print(f"随机剪枝完成：原节点数 {current_count} -> 现保留节点数 {len(self.nodes)}。")

    def save_to_file(self, output_file):
        """
        将修改后的 nodes 保存到新的 JSON 文件
        :param output_file: 输出文件路径
        """
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.nodes, f, indent=4, ensure_ascii=False)
            print(f"简化后的拓扑已成功保存至: {output_file}")
        except Exception as e:
            print(f"保存文件失败 {output_file}: {e}")

    def read_topo(self):
        """
        分析拓扑结构：计算 srcip 和 destip 之间的路径数，以及未在路径上的节点数
        """
        if not self.srcip or not self.destip:
            print("未指定 srcip 或 destip，无法进行拓扑分析。")
            return
            
        if self.srcip not in self.ipindexed_nodes or self.destip not in self.ipindexed_nodes:
            print(f"源节点 {self.srcip} 或目的节点 {self.destip} 不存在于拓扑数据中。")
            return

        all_paths = []
        visited = set()

        # 使用 DFS (深度优先搜索) 查找所有简单路径
        def dfs(current_node, current_path):
            if current_node == self.destip:
                all_paths.append(list(current_path))
                return

            visited.add(current_node)
            
            # 遍历当前节点指向的下一跳
            neighbors = self.ipindexed_nodes.get(current_node, {}).get("linked_to", [])
            for neighbor in neighbors:
                if neighbor not in visited and neighbor in self.ipindexed_nodes:
                    current_path.append(neighbor)
                    dfs(neighbor, current_path)
                    current_path.pop()  # 回溯
                    
            visited.remove(current_node)

        # 从源节点开始搜索
        dfs(self.srcip, [self.srcip])

        # 获取所有在路径上的节点集合
        nodes_on_paths = set()
        for path in all_paths:
            nodes_on_paths.update(path)

        # 找出不在任何路径上的节点
        all_node_names = set(self.ipindexed_nodes.keys())
        nodes_not_on_path = all_node_names - nodes_on_paths

        # 1. 有几个点没在他们的路径上
        not_on_path_count = len(nodes_not_on_path)
        # 2. 他们之间有几条路径
        path_count = len(all_paths)

        # 输出结果
        print(f"--- 拓扑分析报告 ---")
        print(f"一共有{len(self.nodes)}个节点")
        print(f"起点: {self.srcip}  ->  终点: {self.destip}")
        print(f"1. 没在路径上的节点数量: {not_on_path_count} 个")
        print(f"2. 两个节点之间的路径总数: {path_count} 条")
        print(f"--------------------")

        # 将结果存入 info 成员中
        self.info = {
            "path_count": path_count,
            "not_on_path_count": not_on_path_count,
            "nodes_not_on_path": list(nodes_not_on_path),
            "all_paths": all_paths
        }
# --- 测试用例 ---
if __name__ == "__main__":
    
    input_json = "/home/sbp/lixinyang/pingmesh/data/nodes/1761434460000/714078514/714078514_info.json"
    
    modifier = Modifier(input_json)
    modifier.read_topo()# 假设保留 10 个节点
