import os
from pathlib import Path

def combine_py_files(source_folder, output_filename):
    """
    读取指定文件夹中所有的 .py 文件并将它们合并到一个文件中。
    
    :param source_folder: 要读取的目标文件夹路径
    :param output_filename: 合并后保存的文件名（包含路径）
    """
    source_path = Path(source_folder)
    output_path = Path(output_filename)
    
    # 统计合并了多少个文件
    count = 0 

    # 以写入模式打开输出文件（如果文件已存在会被覆盖）
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # 使用 rglob('*.py') 递归查找所有 .py 文件，包括子文件夹中的
        for filepath in source_path.rglob('*.py'):
            
            # 避免将刚刚创建的输出文件自己也读取进去
            if filepath.resolve() == output_path.resolve():
                continue

            try:
                # 读取当前的 .py 文件
                with open(filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    
                    # 写入显眼的分割线和文件信息，方便日后查看
                    outfile.write(f"\n\n{'='*60}\n")
                    outfile.write(f"# 原始文件: {filepath.name}\n")
                    outfile.write(f"# 原始路径: {filepath}\n")
                    outfile.write(f"{'='*60}\n\n")
                    
                    # 写入文件内容
                    outfile.write(content)
                    count += 1
                    print(f"成功读取并写入: {filepath.name}")
                    
            except Exception as e:
                print(f"读取文件 {filepath} 时发生错误: {e}")

    print(f"\n处理完成！共合并了 {count} 个 .py 文件。")
    print(f"文件已保存至: {output_path.absolute()}")

# ==========================================
# 在这里修改你的文件夹路径和想要保存的文件名
# ==========================================
if __name__ == "__main__":
    # # 替换为你想要读取的文件夹路径，例如 'D:/my_python_project' 或 './' (当前目录)
    # folder_to_read = '/home/sbp/lixinyang/pingmesh/SkillBank/skills'  
    
    # # 合并后生成的文件名
    # file_to_save = 'combined_all_code.txt' 
    
    # combine_py_files(folder_to_read, file_to_save)
    print("""
好吧，我现在得仔细想想怎么解决这个问题。首先，我需要理解用户的需求是什么。他们想为现有的根因定位系统编写一个新的自动化事实提取插件，用来纠正大模型在特定网络故障场景下的误判。特别是关于拓扑结构的理解，尤其是在多级节点的情况下，各层级设备的相互影响可能没有被正确考虑进去。\n\n那问题来了，这个插件需要做什么呢？根据背景描述，技能类型是“拓扑结构理解”，所以我要设计一个能够分析网络拓扑结构，找出可能导致误判的异常情况的功能。\n\n接下来，我得看看插件开发规范。代码必须包含SKILL_META、执行函数和EXECUTORS。其中，SKILL_META需要有各个字段，包括技能ID、名称、目标错误、执行函数名、触发条件和执行指令。\n\n首先，SKILL_META里的skill_id填的是999，但系统会自动分配，所以可能暂时不用管。skill_name要简明，比如“拓扑结构分析”。target_error是解决大模型在多级节点中的误判问题。python_executor是具体的函数名，比如topology_analysis。触发条件需要考虑什么情况下触发这个插件。这里可能需要检查是否有多个层级，或者是否有关键节点的状态异常。比如，当检测到关键节点状态异常，并且存在多级拓扑结构时触发。所以触发条件可能是OR或AND逻辑，比如检测到关键节点状态异常，同时拓扑层级超过两层。\n\n然后，执行函数的输入是node_list，里面包含各个节点的字典。我需要解析这些节点，找出是否存在多级节点，以及是否有关键节点的状态异常。比如，检查每个节点的层级，统计层级数量是否超过两层，或者是否有节点的状态是异常的。\n\n在函数中，我可能需要遍历node_list，记录每个节点的层级。例如，有些节点可能有parent_id，可以用来构建层级关系。如果有节点的层级超过两层，那么可能存在复杂的拓扑结构，这时候需要特别注意。另外，如果有节点的状态是异常的，比如status是'error'，那么也要记录下来。\n\n接着，我需要判断是否需要触发这个插件。比如，如果存在层级超过两层，并且有节点状态异常，那么就认为可能存在误判，需要进行进一步分析。然后，生成相应的结果，指出哪些节点可能有问题，并给出建议，比如将这些节点排除或者列为嫌疑。\n\n最后，执行指令部分，告诉大模型拿到结果后必须怎么做，比如重新分析这些节点的影响，或者调整推理路径。\n\n那现在，我得把这些逻辑写成Python代码。首先，定义SKILL_META，然后编写函数topology_analysis，接收node_list。在这个函数里，遍历每个节点，记录层级和状态。然后检查是否有层级超过两层，并且有节点异常。如果有，就生成相应的提示信息，否则返回未发现异常。\n\n比如，我可以创建两个变量，max_level来记录最大的层级数，和问题节点列表。然后，遍历每个节点，检查它的level，更新max_level。同时，如果节点的状态是异常的，就加入问题列表。\n\n之后，检查max_level是否大于等于2，并且问题节点列表不为空。如果是，就生成警告信息，指出这些节点可能需要重点检查。否则，返回未发现异常。\n\n这样，整个插件就能在特定条件下触发，帮助大模型更准确地分析网络故障，避免误判。\n\n需要注意的是，函数必须返回一个以【自动化事实X：拓扑结构分析】开头的字符串，如果没有问题则说明未发现异常，如果有问题则给出强烈的建议。\n\n现在，把这些思路整理成代码，确保符合规范，比如函数名和SKILL_META中的python_executor一致，返回值正确等等。\n</think>\n\n```python\nSKILL_META = {\n    \"skill_id\": \"999\",\n    \"skill_name\": \"拓扑结构分析\",\n    \"target_error\": \"纠正大模型在网络故障中对多级节点影响的误判\",\n    \"python_executor\": \"topology_analysis\",\n    \"trigger_conditions\": {\n        \"logic\": \"AND\",\n        \"rules\": [\n            \"node_list contains multiple hierarchical levels\",\n            \"存在关键节点状态异常\"\n        ]\n    },\n    \"execution_instructions\": \"必须重新分析这些节点的影响，并调整推理路径。\"\n}\n\ndef topology_analysis(node_list) -> str:\n    result_lines = []\n    max_level = 0\n    problematic_nodes = []\n    \n    for node in node_list:\n        level = node.get(\"level\", 0)\n        status = node.get(\"status\", \"\")\n        if level > max_level:\n            max_level = level\n        if status.lower() == \"error\":\n            problematic_nodes.append(node[\"id\"])\n    \n    if max_level >= 2 and problematic_nodes:\n        result_lines.append(f\"检测到多层次拓扑结构，最高层级为{max_level}级。\")\n        result_lines.append(\"强烈建议重新分析以下关键节点的影响：\")\n        result_lines.append(\", \".join(problematic_nodes))\n        result_lines.append(\"这些节点的异常可能对整体网络造成连锁反应。\")\n        return \"【自动化事实X：拓扑结构分析】\\n\".join(result_lines)\n    else:\n        return \"【自动化事实X：拓扑结构分析】未发现异常。\"\n\nEXECUTORS = {\n    \"topology_analysis\": topology_analysis\n}\n```
""")