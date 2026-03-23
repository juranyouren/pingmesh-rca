import json
import os

class Collector:
    def __init__(self, input_path, output_path):
        """
        初始化 Collector 类
        :param input_path: 输入文件目录
        :param output_path: 输出文件目录
        """
        self.input_path = input_path
        self.output_path = output_path
        self.count = 0      # 记录异常节点导致跳过的数量
        self.all_num = 0    # 记录处理的文件总数

    def process_network_nodes(self, file_path):
        """
        处理单个网络节点文件，提取并清洗数据
        :param file_path: JSON 文件路径
        :return: (name_map, timestamp) 成功时返回结果元组，失败时返回 (None, None)
        """
        # 1. 从文件中加载数据
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
            return None, None,None,None

        full_link = raw_data.get("full_link", {})
        alarm_content=raw_data.get("alarm_content",{})
        csn=alarm_content.get('csn',0)
        alarm_content=full_link.get("task_info",{})
        alarm_content["csn"]=csn
        alarm_content["label"]=full_link.get("rootcause_analysis",{})
        
        # 2. 初始化以 device_name 为键的字典
        name_map = {}
        ip_to_name = {}

        task_info = full_link.get("task_info", {})
        timestamp = task_info.get("alarm_time")
        if not timestamp:
            return None, None,None,None

        # 3. 遍历拓扑结构提取节点基础信息
        topo_value = full_link.get("task_topo", {}).get("value", [])
        for path in topo_value:
            for segment in path:
                for node in segment.get("nodes", []):
                    d_name = node.get("name")
                    d_ip = node.get("mgmt_ip")
                    
                    if d_name and d_name not in name_map:
                        name_map[d_name] = {
                            "role": node.get("role"),
                            "mgmt_ip": d_ip,
                            "name": d_name,
                            "node_sign": node.get("node_sign"),
                            "type": node.get("type"),
                            "devicetype": node.get("devicetype"),
                            "linked_from": set(),
                            "linked_to": set(),
                            "verified_hops_to": set(),
                            "alarms": [],
                            "logs": []
                        }
                        if d_ip:
                            ip_to_name[d_ip] = d_name

                # 提取物理链路关系 (Links)
                for link in segment.get("links", []):
                    src_ip = link.get("src_ip")
                    dst_ip = link.get("dst_ip")
                    
                    # 关联到对应的 device_name
                    src_name = ip_to_name.get(src_ip)
                    if src_name:
                        name_map[src_name]["linked_to"].add(dst_ip)
                    
                    dst_name = ip_to_name.get(dst_ip)
                    if dst_name:
                        name_map[dst_name]["linked_from"].add(src_ip)

        # 关联 cross
        cross = full_link.get("cross", [])
        for c in cross:
            try:
                if c["device_name"] in name_map:
                    name_map[c["device_name"]]["cross"] = c["cross"]
            except KeyError:
                pass

        # 关联 rootcause_analysis
        rcs = full_link.get("rootcause_analysis", [])
        for rc in rcs:
            nd = rc.get("abnormal_node", [])
            try:
                try:
                    nd = nd[0]
                except (IndexError, TypeError):
                    pass
                
                name = nd.get("name")
                if name not in name_map:
                    self.count += 1
                    print(f"rc删除第{self.count}个")
                    print(name)
                    return None, None,None,None
            except Exception as e:
                self.count += 1
                print(f"删除第{self.count}个")
                print("--------")
                print(nd)
                print("---------")
                return None, None,None,None

        # 4. 关联 TraceRoute 路径验证
        task_trace = full_link.get("task_trace", [])
        for trace in task_trace:
            try:
                for hop in trace.get("trace_route_hops", []):
                    f_ip = hop.get("from_ip")
                    t_ip = hop.get("to_ip")
                    f_name = ip_to_name.get(f_ip)
                    if f_name and t_ip:
                        name_map[f_name]["verified_hops_to"].add(t_ip)
            except Exception:
                print(f"TraceRoute解析失败: {file_path}")
                return None, None,None,None

        # 5. 关联 告警 (Alarms)
        for alarm in full_link.get("alarm_list", []):
            a_ip = alarm.get("alarm_ip_ad")
            target_name = ip_to_name.get(a_ip)
            if target_name:
                name_map[target_name]["alarms"].append(alarm)

        # 6. 关联 日志 (Logs)
        for log in full_link.get("log_list", {}).get("list", []):
            l_ip = log.get("alarm_ip_ad")
            target_name = ip_to_name.get(l_ip)
            if target_name:
                name_map[target_name]["logs"].append(log)

        # 7. 数据清洗：将 set 转换为 list 以便 JSON 序列化
        for d_name in name_map:
            name_map[d_name]["linked_from"] = list(name_map[d_name]["linked_from"])
            name_map[d_name]["linked_to"] = list(name_map[d_name]["linked_to"])
            name_map[d_name]["verified_hops_to"] = list(name_map[d_name]["verified_hops_to"])

        return name_map, timestamp,csn,alarm_content

    def run(self):
        """
        执行批量文件处理流程
        """
        if not os.path.exists(self.input_path):
            print(f"输入路径不存在: {self.input_path}")
            return

        # 遍历 input_path 下的所有文件
        for file_name in os.listdir(self.input_path):
            self.all_num += 1
            full_input_path = os.path.join(self.input_path, file_name)
            
            # 确保当前遍历到的是文件而不是子目录
            if not os.path.isfile(full_input_path):
                continue

            # 调用函数处理数据
            name_map, timestamp,csn,alarm_info = self.process_network_nodes(full_input_path)
            
            # 检查是否处理失败或未提取到 timestamp
            if name_map is None or timestamp is None:
                print(f"跳过文件 (读取/解析失败或无timestamp): {file_name}")
                continue

            # 构造输出目录路径: output_path / timestamp
            output_dir = os.path.join(self.output_path, str(timestamp),csn)
            os.makedirs(output_dir, exist_ok=True)
            
            # 构造最终的输出文件路径
            full_output_path = os.path.join(output_dir, file_name)
            alarm_path=os.path.join(output_dir, f"{csn}_info.json")
            
            # 将清洗后的节点数据写入 JSON 文件
            try:
                with open(full_output_path, 'w', encoding='utf-8') as f:
                    json.dump(name_map, f, indent=4, ensure_ascii=False)
                print(f"成功处理并保存: {full_output_path}")
            except Exception as e:
                print(f"写入文件失败 {full_output_path}: {e}")
            
            # 将清洗后的节点数据写入 JSON 文件
            try:
                with open(alarm_path, 'w', encoding='utf-8') as f:
                    json.dump(alarm_info, f, indent=4, ensure_ascii=False)
                print(f"成功处理并保存: {alarm_path}")
            except Exception as e:
                print(f"写入文件失败 {alarm_path}: {e}")

        print(f"--- 任务完成 ---")
        print(f"总计扫描了 {self.all_num} 个文件")
        print(f"因RC异常丢弃了 {self.count} 个解析过程")


# # --- 执行脚本 ---
if __name__ == "__main__":
    INPUT_DIR = "/home/sbp/lixinyang/pingmesh/data/pingmesh_original"
    OUTPUT_DIR = "/home/sbp/lixinyang/pingmesh/data/nodes"
    
    # 实例化并运行
    collector = Collector(input_path=INPUT_DIR, output_path=OUTPUT_DIR)
    collector.run()