import glob
import json
import random
import os,sys
import copy
import pandas as pd
sys.path.append("/home/sbp/lixinyang/pingmesh/topo_simplify")
from utils.public_functions import load_json,save_json

class Modifier:
    def __init__(self, alarm_content_path):
        """
        初始化 Modifier 类
        :param json_file: 包含节点数据的 JSON 文件路径
        """
        self.alarm_content_path = alarm_content_path
        self.alarm_content=load_json(alarm_content_path)

        self.alarm_content.pop("all_tag")

        self.json_file=os.path.dirname(alarm_content_path)
        self.json_file=os.path.join(self.json_file,f"merged_pingmesh-{self.alarm_content['csn']}-全链路.json")
        self.nodes = load_json(self.json_file)
        self.destip=self.alarm_content["dst_tunnel_ip"]
        self.srcip=self.alarm_content["src_tunnel_ip"]
        self.info={}

        # print("_________________________________")
        # print(self.nodes)
        self.compress_node_events()
        # 生成以 IP 为索引的节点字典
        self.ipindexed_nodes = {}
        if self.nodes:
            self._generate_ipindexed_nodes()
        else:
            print("node empty")
        #self.read_topo()
        #self.calculate_path_counts(self.srcip,self.destip)

    @staticmethod
    def default_alarm_compressor(alarms):
        """
        进阶告警压缩方法：按 name, ip, desc_summary 去重，
        保留首次发生时间，并统计该告警在当前时间窗口内的触发总次数 (count)。
        """
        if not alarms:
            return []
        
        alarm_dict = {}
        
        for alarm in alarms:
            name = alarm.get("alarm_name")
            level = alarm.get("alarm_level")
            ip = alarm.get("alarm_ip_ad")
            time_str = alarm.get("confirm_time")
            # 截取前100个字符作为摘要，如果原文字段不存在则返回空字符串
            desc_summary = alarm.get("alarm_object_key", "")[:100] + "..."
            
            unique_key = (name, ip, desc_summary)
            
            if unique_key not in alarm_dict:
                # 首次出现，记录基础信息并初始化计数器为 1
                alarm_dict[unique_key] = {
                    "name": name,
                    "level": level,
                    "ip": ip,
                    "time": time_str,  # 记录首次告警的时间
                    "desc_summary": desc_summary,
                    "count": 1
                }
            else:
                # 如果已经存在，说明是重复告警，仅增加计数
                alarm_dict[unique_key]["count"] += 1
                
        # 将字典的值提取为列表返回
        return list(alarm_dict.values())

    @staticmethod
    def default_log_compressor(logs):
        """
        默认的日志压缩方法：只保留日志名称、时间和CID核心描述，并按照 name 和 desc 进行去重。
        保留的是该类日志首次出现的时间。
        """
        if not logs:
            return []
        
        simplified_logs = []
        seen_keys = set()  # 用于存储已经处理过的 (name, desc) 组合
        
        for log in logs:
            name = log.get("alarm_name")
            desc = log.get("alarm_description")
            time_str = log.get("alarm_time_str")
            
            # 使用元组作为唯一键，因为元组是不可变类型，可以被哈希并放入 set 中
            unique_key = (name, desc)
            
            # 如果这个组合还没有被记录过
            if unique_key not in seen_keys:
                seen_keys.add(unique_key)  # 标记为已见
                
                simplified = {
                    "name": name,
                    "time": time_str,
                    "desc": desc
                }
                simplified_logs.append(simplified)
                
        return simplified_logs

    def compress_node_events(self, alarm_processor=None, log_processor=None, in_place=True, threshold=5):
        """
        对所有 node 的告警和日志进行压缩，并确保最终数量不超过阈值。
        
        :param alarm_processor: 自定义的告警处理函数
        :param log_processor: 自定义的日志处理函数
        :param in_place: 是否直接修改原数据
        :param threshold: 最大保留条数，默认为 5
        """
        # 确定处理器
        process_alarms = alarm_processor if alarm_processor else self.default_alarm_compressor
        process_logs = log_processor if log_processor else self.default_log_compressor

        # 决定目标对象
        target_nodes = self.nodes if in_place else copy.deepcopy(self.nodes)

        for node_id, node_data in target_nodes.items():
            # 压缩并截断 Alarms
            if "alarms" in node_data and isinstance(node_data["alarms"], list):
                compressed_alarms = process_alarms(node_data["alarms"])
                # 核心修改：如果长度超过 threshold，则截取前 threshold 个
                node_data["alarms"] = compressed_alarms[:threshold]
            
            # 压缩并截断 Logs
            if "logs" in node_data and isinstance(node_data["logs"], list):
                compressed_logs = process_logs(node_data["logs"])
                # 核心修改：同上
                node_data["logs"] = compressed_logs[:threshold]

        return None if in_place else target_nodes

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

    def topo_simplify(self, k,method=4):
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
        #nodes_to_keep = set(random.sample(all_node_names, k))
        nodes_to_keep=set(self.get_top_k_jaccard_ips(k,method))
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
            #neighbors = self.ipindexed_nodes.get(current_node, {}).get("linked_to", [])

            # 获取两个列表并合并
            raw_neighbors = self.ipindexed_nodes.get(current_node, {}).get("linked_to", [])
            verified_neighbors = self.ipindexed_nodes.get(current_node, {}).get("verified_hops_to", [])
            
            # 使用 set 去重，确保每个邻居节点只遍历一次
            neighbors = set(raw_neighbors) | set(verified_neighbors)

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

    def get_top_k_jaccard_ips(self, k=10,method=0):
        """
        输出并返回排名前 k 的节点 IP（基于类杰卡德指数）
        :param k: 需要输出的节点数量，默认为 10
        :return: 排名前 k 的 IP 列表
        """
        # 如果还没计算过杰卡德指数，自动调用计算方法
        if not hasattr(self, 'sorted_jaccard_nodes') or not self.sorted_jaccard_nodes:
            print("未找到排序好的杰卡德节点数据，正在自动计算...")
            self.calculate_jaccard_index(method)
            
        if not self.sorted_jaccard_nodes:
            print("节点数据为空，无法输出排名。")
            return []

        # 获取前 k 个节点（如果总数不足 k，切片会自动处理）
        top_k_nodes = self.sorted_jaccard_nodes[:k]
        top_k_ips = [node['ip'] for node in top_k_nodes]
        top_k_names=[node['original_name'] for node in top_k_nodes]

        # 格式化输出结果
        print(f"\n--- Top {len(top_k_ips)} 类杰卡德指数核心节点 ---")
        for i, node in enumerate(top_k_nodes):
            # 处理无穷大的显示格式
            j_score = float('inf') if node['jaccard_index'] == float('inf') else f"{node['jaccard_index']:.4f}"
            print(f"Rank {i+1:<2}: IP = {node['ip']:<15} | Jaccard = {j_score:<8} | p_x_y = {node['p_x_y']:<4} | p_y_x = {node['p_y_x']}")
        print("-" * 50)

        return top_k_names

    def calculate_jaccard_index(self, method: int = 0) -> list:
        """
        计算类杰卡德指数并排序。
        :param method: 0=基础版, 1=归一化版, 2=基于总度的变种
        """
        if not hasattr(self, 'ipindexed_nodes') or not self.ipindexed_nodes:
            print("拓扑数据为空，无法计算杰卡德指数。")
            return []

        jaccard_scores = []
        max_cross=1
        for ip, node_data in self.ipindexed_nodes.items():
            if float(node_data.get('cross', 0))>max_cross:
                max_cross=float(node_data.get('cross', 0))
        for ip, node_data in self.ipindexed_nodes.items():
            cross = float(node_data.get('cross', 0))
            in_degree = len(node_data.get('linked_from', []))
            out_degree = len(node_data.get('linked_to', []))
            total_degree = float(in_degree + out_degree)
            
            #paths=node_data.get('paths', 0)
            paths=1

            alarm_count=len(node_data.get("alarms"))
            log_count=len(node_data.get("logs"))

            if total_degree == 0 and method == 2:
                 p_x_y, p_y_x = 0.0, 0.0
            else:
                if method == 0:
                    p_x_y, p_y_x = cross, total_degree
                elif method == 1:
                    total = cross + total_degree
                    p_x_y = cross / total if total > 0 else 0
                    p_y_x = total_degree / total if total > 0 else 0
                elif method == 2:
                    p_x_y = cross / total_degree
                    p_y_x = (total_degree - cross) / total_degree
                elif method == 3:
                    p_x_y=cross
                    p_y_x=paths/self.info["path_count"]
                else:
                    p_x_y, p_y_x = 0.0, 0.0


            # 计算调和平均数 H
            sum_p = p_x_y + p_y_x
            h = (2.0 * p_x_y * p_y_x) / sum_p if sum_p > 0 else 0.0
            
            # 计算类杰卡德指数 J
            denominator = 2.0 - h
            j_index = float('inf') if abs(denominator) < 1e-6 else h / denominator
            
            if method ==4:
                j_index=alarm_count+log_count
            jaccard_scores.append({
                "ip": ip,
                "original_name": node_data.get("original_name", ip),
                "jaccard_index": j_index,
                "p_x_y":p_x_y,
                "p_y_x":p_y_x
            })
            
        # 注意：如果是评估模式，不要直接覆盖 self.sorted_jaccard_nodes
        sorted_nodes = sorted(jaccard_scores, key=lambda x: x['jaccard_index'], reverse=True)
        self.sorted_jaccard_nodes=sorted_nodes
        return sorted_nodes

    def evaluate_jaccard_methods(self, methods_to_evaluate: list = None):
        """
        动态评估 K 种 Jaccard 计算方法。
        :param methods_to_evaluate: 需要评估的方法编号列表，例如 [0, 1, 2, 3]。
                                    如果不传，默认评估 0 到 3。
        """
        import pandas as pd
        
        # 0. 默认评估范围
        if methods_to_evaluate is None:
            methods_to_evaluate = [0, 1, 2, 3] # 后续增加方法只需在此或调用处添加编号

        if not hasattr(self, 'alarm_content') or 'label' not in self.alarm_content:
            print("未找到 label 数据，无法进行评估。")
            return
            
        # 1. 提取真实异常节点的 IP (按 ranking 排序)
        sorted_labels = sorted(self.alarm_content['label'], key=lambda x: x['ranking'])
        true_anomalies = [item['abnormal_node'][0]['ip'] for item in sorted_labels]
        
        # 2. 辅助函数：查找排名
        def find_rank(predicted_list, target_ip):
            for index, node in enumerate(predicted_list):
                if node['ip'] == target_ip:
                    return index + 1
            return "未命中"
            
        # 3. 循环计算并收集结果
        table_data = []
        for m_id in methods_to_evaluate:
            # 动态调用计算方法
            results = self.calculate_jaccard_index(method=m_id)
            
            # 定义方法显示名称
            method_display_name = f"Method {m_id}"
            if m_id == 3: method_display_name += " (K总算法)"
            
            row_data = {"算法名称": method_display_name}
            
            # 评估每个真实异常的排名情况
            for i, true_ip in enumerate(true_anomalies):
                rank = find_rank(results, true_ip)
                row_data[f"真Rank {i+1} 预测排名"] = rank
                
            # 计算 Top-N 命中率和精度指标
            top_5_ips = [node['ip'] for node in results[:5]]
            hits_in_top_5 = sum(1 for ip in true_anomalies if ip in top_5_ips)
            row_data["Top-5 命中数"] = f"{hits_in_top_5}/{len(true_anomalies)}"
            
            # 计算 MRR
            mrr = 0.0
            for ip in true_anomalies:
                r = find_rank(results, ip)
                if isinstance(r, int):
                    mrr += 1.0 / r
            row_data["MRR 指标"] = round(mrr / len(true_anomalies), 4) if true_anomalies else 0

            table_data.append(row_data)
        df = pd.DataFrame(table_data)
        if table_data:
            df = pd.DataFrame(table_data)
            print("\n" + "="*35 + f" 算法效果横向评测 (K={len(methods_to_evaluate)}) " + "="*35)
            print(df.to_markdown(index=False, tablefmt="grid"))
            print("="*100 + "\n")
            return df
        return df

    def calculate_path_counts(self, src_ip, dest_ip):
        # 1. 预处理：构建正向图和反向图 (同时完成去重)
        forward_graph = {}
        reverse_graph = {node: [] for node in self.ipindexed_nodes}
        
        for node, data in self.ipindexed_nodes.items():
            raw_linked = data.get("linked_to", [])
            raw_verified = data.get("verified_hops_to", [])
            # 去重并过滤掉不在图中的野节点
            neighbors = {n for n in (raw_linked + raw_verified) if n in self.ipindexed_nodes}
            forward_graph[node] = list(neighbors)
            
            # 填充反向图
            for neighbor in neighbors:
                reverse_graph[neighbor].append(node)

        # 2. 记忆化搜索：计算从 p 到 dest 的路径数
        memo_to_dest = {}
        visited_to = set() # 用于防环
        
        def count_to_dest(node):
            if node == dest_ip: return 1
            if node in memo_to_dest: return memo_to_dest[node]
            if node in visited_to: return 0 # 遇到环，认为该环不产生新的简单路径
            
            visited_to.add(node)
            total_paths = 0
            for neighbor in forward_graph.get(node, []):
                total_paths += count_to_dest(neighbor)
                
            visited_to.remove(node)
            memo_to_dest[node] = total_paths
            return total_paths

        # 3. 记忆化搜索：计算从 src 到 p 的路径数
        memo_from_src = {}
        visited_from = set() # 用于防环
        
        def count_from_src(node):
            if node == src_ip: return 1
            if node in memo_from_src: return memo_from_src[node]
            if node in visited_from: return 0 # 遇到环
            
            visited_from.add(node)
            total_paths = 0
            for prev_node in reverse_graph.get(node, []):
                total_paths += count_from_src(prev_node)
                
            visited_from.remove(node)
            memo_from_src[node] = total_paths
            return total_paths

        # 4. 汇总结果，找出所有在 src 到 dest 路径上的点 p
        result = {}
        for p in self.ipindexed_nodes:
            paths_src_to_p = count_from_src(p)
            paths_p_to_dest = count_to_dest(p)
            
            # # 只有当 p 既能从 src 到达，又能到达 dest 时，它才是有效中间节点
            # if paths_src_to_p > 0 and paths_p_to_dest > 0:
            #     result[p] = {
            #         "from_src": paths_src_to_p,
            #         "to_dest": paths_p_to_dest,
            #         # 可选：经过 p 的 src->dest 的总路径数 (注意：仅在无环 DAG 中绝对准确)
            #         "total_through_p": paths_src_to_p * paths_p_to_dest 
            #     }
            self.ipindexed_nodes[p]['from_src']=paths_src_to_p
            self.ipindexed_nodes[p]['to_dest']=paths_p_to_dest
            self.ipindexed_nodes[p]['paths']=paths_src_to_p * paths_p_to_dest 
                
        return result

    def run(self,k=10):
        self.topo_simplify(k)
        save_json(self.nodes,os.path.join(os.path.dirname(self.alarm_content_path),"nodes.json"))
        save_json(self.alarm_content.pop("label"),os.path.join(os.path.dirname(self.alarm_content_path),"label.json"))
        save_json(self.alarm_content,os.path.join(os.path.dirname(self.alarm_content_path),"info.json"))

# --- 测试用例 ---
if __name__ == "__main__":
    
    # input_json = "/home/sbp/lixinyang/pingmesh/data/nodes/1760594400000/1231999173/1231999173_info.json"
    
    # modifier = Modifier(input_json)
    # modifier.get_top_k_jaccard_ips(method=4)
    # modifier.evaluate_jaccard_methods([0,1,2,3,4])
    #modifier.run()
    base_data_dir = "/home/sbp/lixinyang/pingmesh/data/nodes/"
    
    # 2. 递归查找所有以 _info.json 结尾的告警文件
    search_pattern = os.path.join(base_data_dir, "**", "**","*_info.json")
    test_files = glob.glob(search_pattern, recursive=True)
    
    if not test_files:
        print(f"在 {base_data_dir} 下没有找到任何 *_info.json 文件，请检查路径。")
        sys.exit(1)
    test_files=list(set(test_files))
    print(f"🔍 共找到 {len(test_files)} 个测试用例，开始批量跑测...\n")

    for idx, file_path in enumerate(test_files, 1):
        case_name = os.path.basename(os.path.dirname(file_path)) # 用父文件夹名（如1231999173）作为 case 名
        print(f"▶ [{idx}/{len(test_files)}] 正在处理用例: {case_name}")
        try:
            # 实例化对象
            modifier = Modifier(file_path)
            modifier.run()

                
        except Exception as e:
            print(f"❌ 处理用例 {case_name} 时发生异常: {e}")



        
# if __name__ == "__main__":

    
#     # 1. 设置包含所有测试用例的根目录
#     # 请根据实际情况修改为你存放数据的上一级或根目录
#     base_data_dir = "/home/sbp/lixinyang/pingmesh/data/nodes/"
    
#     # 2. 递归查找所有以 _info.json 结尾的告警文件
#     search_pattern = os.path.join(base_data_dir, "**", "**","*_info.json")
#     test_files = glob.glob(search_pattern, recursive=True)
    
#     if not test_files:
#         print(f"在 {base_data_dir} 下没有找到任何 *_info.json 文件，请检查路径。")
#         sys.exit(1)
        
#     print(f"🔍 共找到 {len(test_files)} 个测试用例，开始批量跑测...\n")
    
#     all_results = []
#     failed_cases = []

#     # 3. 遍历执行每个测试用例
#     for idx, file_path in enumerate(test_files, 1):
#         case_name = os.path.basename(os.path.dirname(file_path)) # 用父文件夹名（如1231999173）作为 case 名
#         print(f"▶ [{idx}/{len(test_files)}] 正在处理用例: {case_name}")
        
#         try:
#             # 实例化对象
#             modifier = Modifier(file_path)
            
#             # 评估算法 (默认跑测 0, 1, 2, 3 四个方法)
#             df_result = modifier.evaluate_jaccard_methods()
            
#             # 如果成功返回了评估数据表格，保存起来
#             if df_result is not None:
#                 # 在表格最前面加一列标识当前是哪个用例
#                 df_result.insert(0, 'TestCase', case_name)
#                 all_results.append(df_result)
                
#         except Exception as e:
#             print(f"❌ 处理用例 {case_name} 时发生异常: {e}")
#             failed_cases.append((case_name, str(e)))

#     # 4. 汇总与统计
#     print("\n" + "="*50)
#     print("🎉 批量测试完成！")
#     print(f"成功: {len(all_results)} 个 | 失败: {len(failed_cases)} 个")
#     print("="*50)
    
#     if all_results:
#         # 拼接所有的结果
#         final_df = pd.concat(all_results, ignore_index=True)
        
#         # 将所有明细保存到本地，方便后续复盘
#         output_csv = "batch_test_results.csv"
#         final_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
#         print(f"\n💾 详细测试结果已保存至: {output_csv}")
        
#         # --- 核心亮点：计算全局平均 MRR ---
#         if "MRR 指标" in final_df.columns:
#             print("\n" + "🌟 全局算法性能汇总 (Average MRR) 🌟")
#             # 按算法名称分组，计算 MRR 的平均值并降序排列
#             summary_df = final_df.groupby("算法名称")["MRR 指标"].mean().reset_index()
#             summary_df = summary_df.sort_values(by="MRR 指标", ascending=False)
            
#             print(summary_df.to_markdown(index=False, tablefmt="grid"))
            
#     if failed_cases:
#         print("\n⚠️ 失败用例列表:")
#         for case, err in failed_cases:
#             print(f" - {case}: {err}")