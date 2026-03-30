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
    # 替换为你想要读取的文件夹路径，例如 'D:/my_python_project' 或 './' (当前目录)
    folder_to_read = '/home/sbp/lixinyang/pingmesh/SkillBank/skills'  
    
    # 合并后生成的文件名
    file_to_save = 'combined_all_code.txt' 
    
    combine_py_files(folder_to_read, file_to_save)