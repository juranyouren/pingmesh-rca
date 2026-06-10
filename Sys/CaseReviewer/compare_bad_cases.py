import json
import os

def extract_names_from_json(file_path: str) -> set:
    """从 JSON 文件中提取所有的 name 并存入集合"""
    if not os.path.exists(file_path):
        print(f"❌ 找不到文件: {file_path}")
        return set()
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 兼容你的数据可能是 List 或者 Dict 的形式
        names = set()
        if isinstance(data, list):
            for item in data:
                if "name" in item:
                    names.add(item["name"])
        elif isinstance(data, dict):
            for item in data.values():
                if isinstance(item, dict) and "name" in item:
                    names.add(item["name"])
        return names
    except Exception as e:
        print(f"❌ 读取或解析文件 {file_path} 失败: {e}")
        return set()

def compare_failed_cases(file1_path: str, file2_path: str, save_dir: str):
    print(f"正在对比两个失败案例集：\n📁 文件1 (如旧版本): {file1_path}\n📁 文件2 (如新版本): {file2_path}\n")
    
    set1 = extract_names_from_json(file1_path)
    set2 = extract_names_from_json(file2_path)
    
    if not set1 and not set2:
        print("两个文件均无有效数据，终止对比。")
        return

    # === 核心集合运算 ===
    common_cases = set1 & set2         # 交集：顽固案例（两次都错）
    fixed_cases = set1 - set2          # 差集1：文件1有，文件2没有（被成功修复的案例）
    regression_cases = set2 - set1     # 差集2：文件2有，文件1没有（新引入的错误）

    # === 打印统计面板 ===
    print("="*50)
    print("📊 失败案例对比报告")
    print("="*50)
    print(f"总计: 文件1 有 {len(set1)} 个错案, 文件2 有 {len(set2)} 个错案\n")
    
    print(f"💀 【顽固案例 (交集)】: {len(common_cases)} 个 (不管怎么改，这两次它都错了)")
    print(f"✅ 【成功修复 (仅文件1)】: {len(fixed_cases)} 个 (你这次优化成功解决的案例)")
    print(f"⚠️ 【新增退化 (仅文件2)】: {len(regression_cases)} 个 (你这次优化不小心搞坏的案例)")
    print("="*50)

    # === 保存结果以便后续分析 ===
    os.makedirs(save_dir, exist_ok=True)
    
    res_common = os.path.join(save_dir, "stubborn_cases_common.json")
    res_fixed = os.path.join(save_dir, "fixed_cases_only_v1.json")
    res_regression = os.path.join(save_dir, "regression_cases_only_v2.json")
    
    with open(res_common, 'w', encoding='utf-8') as f:
        json.dump(list(common_cases), f, ensure_ascii=False, indent=2)
    with open(res_fixed, 'w', encoding='utf-8') as f:
        json.dump(list(fixed_cases), f, ensure_ascii=False, indent=2)
    with open(res_regression, 'w', encoding='utf-8') as f:
        json.dump(list(regression_cases), f, ensure_ascii=False, indent=2)
        
    print(f"\n📂 对比结果已保存至 {save_dir} 目录：")
    print(f"  - 顽固案例名单 -> stubborn_cases_common.json")
    print(f"  - 成功修复名单 -> fixed_cases_only_v1.json")
    print(f"  - 新增退化名单 -> regression_cases_only_v2.json")

if __name__ == "__main__":
    # 在这里填入你的文件路径
    # 比如：文件1 是没有加告警共现规则时的报错，文件2 是加了规则后的报错
    FILE_V1 = "/home/sbp/lixinyang/pingmesh/data/res/skill1_2/draft_ranking_failures.json"
    FILE_V2 = "/home/sbp/lixinyang/pingmesh/data/res/1776156321/draft_ranking_failures.json"
    
    # 结果输出目录
    SAVE_DIR = "/home/sbp/lixinyang/pingmesh/data/res/comparison_results"
    
    compare_failed_cases(FILE_V1, FILE_V2, SAVE_DIR)