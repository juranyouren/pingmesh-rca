
import json

def read_node(file_path):
    """
    从指定 JSON 文件中读取节点数据，并提取、统计关键信息。
    
    参数:
        file_path (str): JSON 文件的路径
        
    返回:
        dict: 包含处理后节点数据的字典
    """
    # 存储处理后的数据
    processed_nodes = {}
    
    try:
        # 读取 JSON 文件
        with open(file_path, 'r', encoding='utf-8') as file:
            raw_data = json.load(file)
            
        # 遍历所有节点
        for node_name, node_info in raw_data.items():
            # 提取所需字段并统计 alarm 和 log 的数量
            processed_nodes[node_name] = {
                "ip": node_info.get("mgmt_ip"),
                "devicetype": node_info.get("devicetype"),
                "linked_from": node_info.get("linked_from", []),
                "linked_to": node_info.get("linked_to", []),
                "alarm_num": len(node_info.get("alarms", [])),
                "log_num": len(node_info.get("logs", []))
            }
            
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
    except json.JSONDecodeError:
        print(f"错误：文件 {file_path} 不是有效的 JSON 格式")
    except Exception as e:
        print(f"发生未知错误: {e}")
        
    return processed_nodes

# ==========================================
# 使用示例：
# 假设您的数据保存在名为 'nodes_data.json' 的文件中
# ==========================================
if __name__ == "__main__":
    
    result = read_node('/home/sbp/lixinyang/pingmesh/data/nodes/1760594400000/merged_pingmesh-1231999173-全链路.json')
    output_filename="out.json"
    with open(output_filename, 'w', encoding='utf-8') as out_file:
        # json.dump 将字典对象写入文件
        # ensure_ascii=False 保证中文字符正常显示
        # indent=4 让输出的 JSON 文件具有良好的缩进排版，方便人眼阅读
        json.dump(result, out_file, ensure_ascii=False, indent=4)
    pass
