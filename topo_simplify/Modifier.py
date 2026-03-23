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

    def get_top_k_jaccard_ips(self, k=10):
        """
        输出并返回排名前 k 的节点 IP（基于类杰卡德指数）
        :param k: 需要输出的节点数量，默认为 10
        :return: 排名前 k 的 IP 列表
        """
        # 如果还没计算过杰卡德指数，自动调用计算方法
        if not hasattr(self, 'sorted_jaccard_nodes') or not self.sorted_jaccard_nodes:
            print("未找到排序好的杰卡德节点数据，正在自动计算...")
            self.calculate_jaccard_index()
            
        if not self.sorted_jaccard_nodes:
            print("节点数据为空，无法输出排名。")
            return []

        # 获取前 k 个节点（如果总数不足 k，切片会自动处理）
        top_k_nodes = self.sorted_jaccard_nodes[:k]
        top_k_ips = [node['ip'] for node in top_k_nodes]

        # 格式化输出结果
        print(f"\n--- Top {len(top_k_ips)} 类杰卡德指数核心节点 ---")
        for i, node in enumerate(top_k_nodes):
            # 处理无穷大的显示格式
            j_score = float('inf') if node['jaccard_index'] == float('inf') else f"{node['jaccard_index']:.4f}"
            print(f"Rank {i+1:<2}: IP = {node['ip']:<15} | Jaccard = {j_score:<8} | Cross = {node['support_cross']:<4} | Degree = {node['confidence_degree']}")
        print("-" * 50)

        return top_k_ips

    def calculate_jaccard_index1(self):
        """
        计算类杰卡德指数，并按照该指数降序排序，存入成员变量 self.sorted_jaccard_nodes
        - 支持度 P(X|Y) = cross
        - 置信度 P(Y|X) = 入度 + 出度
        - 调和平均数 H = 2 * P(X|Y) * P(Y|X) / (P(X|Y) + P(Y|X))
        - 类杰卡德指数 J = H / (2 - H)
        """
        if not self.ipindexed_nodes:
            print("拓扑数据为空，无法计算杰卡德指数。")
            return []

        jaccard_scores = []

        for ip, node_data in self.ipindexed_nodes.items():
            # 1. 获取支持度 P(X|Y) (假设数据中包含 'cross' 字段，若无则默认为 0)
            p_x_y = float(node_data.get('cross', 0))
            
            # 2. 获取置信度 P(Y|X) (入度 + 出度)
            in_degree = len(node_data.get('linked_from', []))
            out_degree = len(node_data.get('linked_to', []))
            p_y_x = float(in_degree + out_degree)

            #归一化
            p_x_y_1=float(p_x_y/(p_x_y+p_y_x))
            p_y_x_1=float(p_y_x/(p_x_y+p_y_x))
            p_x_y=p_x_y_1
            p_y_x=p_y_x_1
            
            # 3. 计算调和平均数 H
            if p_x_y + p_y_x > 0:
                h = (2.0 * p_x_y * p_y_x) / (p_x_y + p_y_x)
            else:
                h = 0.0
                
            # 4. 计算类杰卡德指数 J = H / (2 - H)
            denominator = 2.0 - h
            
            # 增加安全检查：防止分母为 0
            if abs(denominator) < 1e-6:
                j_index = float('inf')  # 如果 H 正好等于 2，指数趋于无穷大
            else:
                j_index = h / denominator
                
            jaccard_scores.append({
                "ip": ip,
                "original_name": node_data.get("original_name", ip),
                "support_cross": p_x_y,
                "confidence_degree": p_y_x,
                "harmonic_mean": h,
                "jaccard_index": j_index
            })
            
        # 5. 按照类杰卡德指数降序排序 (从高到低)
        self.sorted_jaccard_nodes = sorted(jaccard_scores, key=lambda x: x['jaccard_index'], reverse=True)
        
        print(f"✅ 类杰卡德指数计算完成，已对 {len(self.sorted_jaccard_nodes)} 个节点进行排序。")
        return self.sorted_jaccard_nodes

    def calculate_jaccard_index0(self):
        """
        计算类杰卡德指数，并按照该指数降序排序，存入成员变量 self.sorted_jaccard_nodes
        - 支持度 P(X|Y) = cross
        - 置信度 P(Y|X) = 入度 + 出度
        - 调和平均数 H = 2 * P(X|Y) * P(Y|X) / (P(X|Y) + P(Y|X))
        - 类杰卡德指数 J = H / (2 - H)
        """
        if not self.ipindexed_nodes:
            print("拓扑数据为空，无法计算杰卡德指数。")
            return []

        jaccard_scores = []

        for ip, node_data in self.ipindexed_nodes.items():
            # 1. 获取支持度 P(X|Y) (假设数据中包含 'cross' 字段，若无则默认为 0)
            p_x_y = float(node_data.get('cross', 0))
            
            # 2. 获取置信度 P(Y|X) (入度 + 出度)
            in_degree = len(node_data.get('linked_from', []))
            out_degree = len(node_data.get('linked_to', []))
            p_y_x = float(in_degree + out_degree)

            
            # 3. 计算调和平均数 H
            if p_x_y + p_y_x > 0:
                h = (2.0 * p_x_y * p_y_x) / (p_x_y + p_y_x)
            else:
                h = 0.0
                
            # 4. 计算类杰卡德指数 J = H / (2 - H)
            denominator = 2.0 - h
            
            # 增加安全检查：防止分母为 0
            if abs(denominator) < 1e-6:
                j_index = float('inf')  # 如果 H 正好等于 2，指数趋于无穷大
            else:
                j_index = h / denominator
                
            jaccard_scores.append({
                "ip": ip,
                "original_name": node_data.get("original_name", ip),
                "support_cross": p_x_y,
                "confidence_degree": p_y_x,
                "harmonic_mean": h,
                "jaccard_index": j_index
            })
            
        # 5. 按照类杰卡德指数降序排序 (从高到低)
        self.sorted_jaccard_nodes = sorted(jaccard_scores, key=lambda x: x['jaccard_index'], reverse=True)
        
        print(f"✅ 类杰卡德指数计算完成，已对 {len(self.sorted_jaccard_nodes)} 个节点进行排序。")
        return self.sorted_jaccard_nodes

    def calculate_jaccard_index2(self):
        """
        计算类杰卡德指数，并按照该指数降序排序，存入成员变量 self.sorted_jaccard_nodes
        - 支持度 P(X|Y) = cross / (入度 + 出度)
        - 置信度 P(Y|X) = (入度 + 出度 - cross) / (入度 + 出度)
        - 调和平均数 H = 2 * P(X|Y) * P(Y|X) / (P(X|Y) + P(Y|X))
        - 类杰卡德指数 J = H / (2 - H)
        """
        if not hasattr(self, 'ipindexed_nodes') or not self.ipindexed_nodes:
            print("拓扑数据为空，无法计算杰卡德指数。")
            return []

        jaccard_scores = []

        for ip, node_data in self.ipindexed_nodes.items():
            # 获取基础数据
            cross = float(node_data.get('cross', 0))
            in_degree = len(node_data.get('linked_from', []))
            out_degree = len(node_data.get('linked_to', []))
            
            # 分母：入度 + 出度
            total_degree = float(in_degree + out_degree)

            # 防止除以 0 的情况：如果是孤立节点，指标默认为 0
            if total_degree == 0:
                p_x_y = 0.0
                p_y_x = 0.0
            else:
                # 1. 计算支持度 P(X|Y)
                p_x_y = cross / total_degree
                
                # 2. 计算置信度 P(Y|X)
                p_y_x = (total_degree - cross) / total_degree
            
            # 3. 计算调和平均数 H
            sum_p = p_x_y + p_y_x
            if sum_p > 0:
                h = (2.0 * p_x_y * p_y_x) / sum_p
            else:
                h = 0.0
                
            # 4. 计算类杰卡德指数 J = H / (2 - H)
            denominator = 2.0 - h
            
            # 增加安全检查：防止分母为 0
            if abs(denominator) < 1e-6:
                j_index = float('inf')  # 如果 H 极其接近 2，指数趋于无穷大
            else:
                j_index = h / denominator
                
            jaccard_scores.append({
                "ip": ip,
                "original_name": node_data.get("original_name", ip),
                "support_p_x_y": p_x_y,
                "confidence_p_y_x": p_y_x,
                "harmonic_mean": h,
                "jaccard_index": j_index
            })
            
        # 5. 按照类杰卡德指数降序排序 (从高到低)
        self.sorted_jaccard_nodes = sorted(jaccard_scores, key=lambda x: x['jaccard_index'], reverse=True)
        
        print(f"✅ 类杰卡德指数计算完成，已对 {len(self.sorted_jaccard_nodes)} 个节点进行排序。")
        return self.sorted_jaccard_nodes
        
# --- 测试用例 ---
if __name__ == "__main__":
    
    input_json = "/home/sbp/lixinyang/pingmesh/data/nodes/1760612340000/1233059059/1233059059_info.json"
    
    modifier = Modifier(input_json)
    modifier.read_topo()# 假设保留 10 个节点
    modifier.get_top_k_jaccard_ips()
