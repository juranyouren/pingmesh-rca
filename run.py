import os
import glob

# 导入你之前编写的三个核心类
from data_process.Collector import Collector
from topo_simplify.Modifier import Modifier
from RootCauseAnalyze.RootCauseAnalyzer import RootCauseAnalyzer

def main():
    # ==========================================
    # 0. 配置路径与参数
    # ==========================================
    # 定义基础路径 (根据你的实际情况调整)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 输入的原始原始数据目录
    INPUT_RAW_DIR = os.path.join(BASE_DIR, "data", "pingmesh_original")
    # Collector 清洗后输出的节点数据目录
    NODES_DIR = os.path.join(BASE_DIR, "data", "nodes")
    # Modifier 简化后输出的拓扑数据目录 (可选，用于落盘检查)
    SIMPLIFIED_DIR = os.path.join(BASE_DIR, "data", "simplified")
    
    # 剪枝后保留的节点数量
    PRUNE_K = 10 
    
    print("=== [阶段 1] 开始执行 Collector 数据清洗 ===")
    # ==========================================
    # 1. 收集与清洗数据 (Collector)
    # ==========================================
    # 实例化并运行 Collector，处理整个文件夹
    collector = Collector(input_path=INPUT_RAW_DIR, output_path=NODES_DIR)
    collector.run()
    
    print("\n=== [阶段 2 & 3] 开始执行拓扑简化与根因分析 ===")
    # ==========================================
    # 2 & 3. 拓扑简化 (Modifier) + 根因分析 (RootCauseAnalyzer)
    # ==========================================
    # 初始化 Analyzer (此处可传入你真实的 LLM client)
    analyzer = RootCauseAnalyzer()

    # Collector 会按 timestamp 创建子文件夹，我们需要遍历 nodes 目录下的所有 json 文件
    # 使用 glob 递归查找所有 json 文件
    search_pattern = os.path.join(NODES_DIR, "**", "*.json")
    cleaned_files = glob.glob(search_pattern, recursive=True)

    cleaned_files = [f for f in cleaned_files if "_simplified" not in f]

    if not cleaned_files:
        print("未找到任何清洗后的节点数据文件，请检查 Collector 是否正常输出。")
        return

    for file_path in cleaned_files:
        print(f"\n>>> 正在处理文件: {file_path}")
        
        # 获取文件所在目录和去除扩展名的基础文件名
        # 例如: file_path = "data/results/1690000/task1.json"
        # dir_name = "data/results/1690000", base_name = "task1"
        dir_name = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # 构造同级目录下的新文件名
        simplified_file_path = os.path.join(dir_name, f"{base_name}_simplified.json")
        res_file_path = os.path.join(dir_name, f"{base_name}_res.txt")
        
        # --- 阶段 2: 拓扑简化 ---
        modifier = Modifier(file_path)
        
        # 如果读取失败，跳过
        if not modifier.nodes:
            continue
            
        # 执行随机剪枝并保存到同级目录
        modifier.topo_simplify(k=PRUNE_K)
        modifier.save_to_file(simplified_file_path)

        # --- 阶段 3: 调用大模型进行根因分析 ---
        print("正在生成 Prompt 并调用 Agent...")
        analysis_result = analyzer.infer_root_cause(modifier.nodes)
        
        # 【新增逻辑】将模型推理文本结果保存为 res_xxx.txt 放在同一个文件夹下
        try:
            with open(res_file_path, "w", encoding="utf-8") as f:
                f.write(analysis_result)
            print(f"推理结果已保存至: {res_file_path}")
        except Exception as e:
            print(f"写入推理结果失败 {res_file_path}: {e}")

        #执行一次就结束
        return

if __name__ == "__main__":
    main()