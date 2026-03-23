import json,os

count=0
def process_network_nodes(file_path):
    global count
    # 1. 从文件中加载数据
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return None

    full_link = raw_data.get("full_link", {})
    
    # 2. 初始化以 device_name 为键的字典
    # 使用 name_map 记录 device_name -> data
    # 使用 ip_to_name 记录 ip -> device_name，方便后续根据 IP 关联告警和日志
    name_map = {}
    ip_to_name = {}

    timestamp=full_link["task_info"]["alarm_time"]

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

    
    # add 关联cross
    cross=full_link.get("cross",[])
    for c in cross:
        try:
            name_map[c["device_name"]]["cross"]=c["cross"]
        except:
            pass
            # count+=1
            # print(c["device_name"])
            # print(f"cr删除第{count}个")
            # return None,None
    
    rcs=full_link.get("rootcause_analysis",[])
    for rc in rcs:
        nd=rc.get("abnormal_node",[])
        try:
            try:
                nd=nd[0]
            except:
                pass
            name=nd["name"]
            if name not in name_map:
                count+=1
                print(f"rc删除第{count}个")
                print(name)
                return None,None
        except:
            count+=1
            print(f"删除第{count}个")
            print("--------")
            print(nd)
            print("---------")
            return None,None
            

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
        except:
            print(file_path)

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

    return name_map,timestamp

# # --- 执行脚本 ---
# input_file = 'test_in.json' # 替换为你的文件名
# result_dict = process_network_nodes(input_file)

# if result_dict:
#     # 打印其中一个设备查看结构
#     first_device = list(result_dict.keys())[0]
#     print(f"设备 '{first_device}' 的聚类数据如下：")
#     print(json.dumps(result_dict[first_device], indent=4, ensure_ascii=False))

#     # 如果想保存结果到新文件
#     # with open('clustered_result.json', 'w', encoding='utf-8') as f:
#     #     json.dump(result_dict, f, indent=4, ensure_ascii=False)
input_path = "/home/sbp/lixinyang/pingmesh/data/pingmesh_original"
output_path = "/home/sbp/lixinyang/pingmesh/data/nodes"
all_num=0
# 遍历 input_path 下的所有文件
for file_name in os.listdir(input_path):
    all_num+=1
    # 1. 拼接完整的输入文件路径
    full_input_path = os.path.join(input_path, file_name)
    
    # 确保当前遍历到的是文件而不是子目录
    if not os.path.isfile(full_input_path):
        continue

    # 2. 调用函数处理数据
    result = process_network_nodes(full_input_path)
    
    # 如果函数返回 None（例如文件读取失败），则跳过当前文件
    if result is None:
        print(f"跳过文件 (读取或解析失败): {file_name}")
        continue
        
    name_map, timestamp = result
    
    # 确保成功获取到了 timestamp
    if not timestamp:
        print(f"跳过文件 (未提取到 timestamp): {file_name}")
        continue

    # 3. 构造输出目录路径: output_path / timestamp
    # 转换为字符串，防止 timestamp 是整型
    output_dir = os.path.join(output_path, str(timestamp))
    
    # 4. 如果该 timestamp 文件夹不存在，则自动创建
    os.makedirs(output_dir, exist_ok=True)
    
    # 5. 构造最终的输出文件路径
    full_output_path = os.path.join(output_dir, file_name)
    
    # 6. 将清洗后的节点数据写入 JSON 文件
    try:
        with open(full_output_path, 'w', encoding='utf-8') as f:
            json.dump(name_map, f, indent=4, ensure_ascii=False)
        print(f"成功处理并保存: {full_output_path}")
    except Exception as e:
        print(f"写入文件失败 {full_output_path}: {e}")

print(f"处理了{all_num}个文件")