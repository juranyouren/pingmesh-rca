import os
import json
import importlib.util
import re

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
def generate_target_path(source_dir):
    # 提取最后一级目录名 (去除末尾可能的斜杠以防出错)
    node_id = os.path.basename(source_dir.rstrip(os.sep))
    filename = f"merged_pingmesh-{node_id}-全链路.json"
    return os.path.join(source_dir, filename)

class SkillExecutor:
    def __init__(self, skills_folder="/home/sbp/lixinyang/pingmesh/SkillBank/skills"):
        self.skill_map = {}          # 存放函数指针: {"evaluate_evidence_weight": <function>}
        self.skill_configs = []
        self.skills_folder=skills_folder      # 存放给大模型看的 JSON 列表
        # 核心：动态加载 Skill 库
        self._load_skills_dynamically(skills_folder)

    def _load_skills_dynamically(self, skills_path):
        if not os.path.exists(skills_path):
            print(f"警告：未找到 Skill 库目录 {skills_path}")
            return

        for filename in os.listdir(skills_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(skills_path, filename)
                
                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    
                    # 1. 提取元数据 (JSON)
                    if hasattr(module, "SKILL_META"):
                        self.skill_configs.append(module.SKILL_META)
                    
                    # 2. 提取并绑定执行函数
                    if hasattr(module, "EXECUTORS"):
                        for executor_name, func in module.EXECUTORS.items():
                            self.skill_map[executor_name] = func
                            
                except Exception as e:
                    print(f"加载插件 {filename} 失败: {e}")
        
        # 可选：按 skill_id 排序，保证输出给大模型的顺序是固定的
        self.skill_configs.sort(key=lambda x: int(x.get("skill_id", 999)))

    def get_skill_conf(self):
        return self.skill_configs

    def get_llm_skill_prompt(self) -> str:
        """调用此方法，自动生成喂给大模型的完整 JSON Skill 字符串"""
        return json.dumps(self.skill_configs, ensure_ascii=False, indent=2)
    
    def get_node_list(self,dirpath):
        nodes = load_json(generate_target_path(dirpath))
        if isinstance(nodes, list):
            return nodes
        elif isinstance(nodes, dict):
            return list(nodes.values())
        return []
    
    def execute(self, executor_name: str,node_path:str) -> str:
        """大模型调用具体函数的入口"""
        skill_func = self.skill_map.get(executor_name)
        if not skill_func:
            return f"【错误】找不到对应的执行脚本: {executor_name}"
        try:
            # 将 node_list 作为参数传给插件，插件无需关心数据是怎么解析的
            return skill_func(self.get_node_list(node_path))
        except Exception as e:
            return f"【系统脚本执行异常 - {executor_name}】: {str(e)}"
    
    def _reload_all_skills(self):
        """清空缓存并重新挂载整个技能目录"""
        self.skill_map.clear()
        self.skill_configs.clear()
        self._load_skills_dynamically(self.skills_folder)

    def manage_skill_from_response(self, response_text: str) -> str:
        """解析大模型的回复，执行技能的增(ADD)、删(DELETE)、改(UPDATE)"""
        
        # 1. 提取 JSON 动作指令
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if not json_match:
            return "【失败】未找到 JSON 格式的动作指令块，操作终止。"
            
        try:
            instruction = json.loads(json_match.group(1))
            action = instruction.get("action", "").upper()
            target_id = str(instruction.get("target_skill_id", "none"))
        except Exception as e:
            return f"【失败】解析 JSON 指令失败: {str(e)}"

        # 2. 提取 Python 代码 (如果是 ADD 或 UPDATE)
        py_code = ""
        if action in ["ADD", "UPDATE"]:
            code_match = re.search(r'```python\s*(.*?)\s*```', response_text, re.DOTALL)
            if not code_match:
                return f"【失败】执行 {action} 操作，但未找到 Python 代码块。"
            py_code = code_match.group(1)
            
            if "SKILL_META" not in py_code or "EXECUTORS" not in py_code:
                return "【失败】提取的代码中缺少 SKILL_META 或 EXECUTORS 核心结构。"

        # 3. 路由到具体的操作函数
        if action == "ADD":
            return self._action_add_skill(py_code)
        elif action == "UPDATE":
            if target_id == "none": return "【失败】UPDATE 操作必须提供 target_skill_id。"
            return self._action_update_skill(target_id, py_code)
        elif action == "DELETE":
            if target_id == "none": return "【失败】DELETE 操作必须提供 target_skill_id。"
            return self._action_delete_skill(target_id)
        else:
            return f"【失败】未知的操作类型: {action}"

    def _action_delete_skill(self, target_id: str) -> str:
        """根据 ID 查找并删除对应的本地 Python 文件"""
        deleted = False
        target_prefix = f"skill_{int(target_id):02d}_"
        
        for filename in os.listdir(self.skills_folder):
            if filename.startswith(target_prefix) and filename.endswith(".py"):
                file_path = os.path.join(self.skills_folder, filename)
                try:
                    os.remove(file_path)
                    deleted = True
                except Exception as e:
                    return f"【失败】删除文件 {filename} 时发生异常: {str(e)}"
                
        if deleted:
            self._reload_all_skills()
            return f"【成功】Skill ID: {target_id} 已成功删除，并完成热更新。"
        return f"【失败】未找到匹配 Skill ID: {target_id} 的文件，无需删除。"

    def _action_update_skill(self, target_id: str, py_code: str) -> str:
        """更新现有的 Skill (本质上是先删除旧文件，再按新逻辑写入同 ID 文件)"""
        # 1. 强制替换代码中的 skill_id，防止大模型写错
        py_code = re.sub(r'("skill_id"\s*:\s*)["\']\w+["\']', rf'\g<1>"{target_id}"', py_code)
        py_code = re.sub(r"('skill_id'\s*:\s*)['\"]\w+['\"]", rf"\g<1>'{target_id}'", py_code)

        # 2. 提取执行器名称用于生成文件名
        executor_match = re.search(r'["\']python_executor["\']\s*:\s*["\']([^"\']+)["\']', py_code)
        executor_name = executor_match.group(1) if executor_match else "updated_executor"
        filename = f"skill_{int(target_id):02d}_{executor_name}.py"
        save_path = os.path.join(self.skills_folder, filename)

        # 3. 删除该 ID 旧版本的所有可能文件
        self._action_delete_skill(target_id) # 内部会执行热更新，但没关系马上会再更新

        # 4. 写入新文件
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(py_code)
            self._reload_all_skills()
            return f"【成功】Skill ID: {target_id} 已成功更新，执行器: {executor_name}。"
        except Exception as e:
            return f"【失败】更新 Skill ID: {target_id} 时写入文件失败: {str(e)}"

    def _action_add_skill(self, py_code: str) -> str:
        """新增 Skill 的逻辑（类似你之前的版本）"""
        existing_ids = []
        for conf in self.skill_configs:
            try:
                existing_ids.append(int(conf.get("skill_id", 0)))
            except ValueError:
                pass
                
        next_id = max(existing_ids) + 1 if existing_ids else 1
        next_id_str = str(next_id)

        # 替换 ID
        py_code = re.sub(r'("skill_id"\s*:\s*)["\']\w+["\']', rf'\g<1>"{next_id_str}"', py_code)
        py_code = re.sub(r"('skill_id'\s*:\s*)['\"]\w+['\"]", rf"\g<1>'{next_id_str}'", py_code)

        # 提取执行器
        executor_match = re.search(r'["\']python_executor["\']\s*:\s*["\']([^"\']+)["\']', py_code)
        executor_name = executor_match.group(1) if executor_match else "auto_generated"
        
        filename = f"skill_{next_id:02d}_{executor_name}.py"
        save_path = os.path.join(self.skills_folder, filename)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(py_code)
            self._reload_all_skills()
            return f"【成功】新技能摄取！分配ID: {next_id_str}, 执行器: {executor_name}。"
        except Exception as e:
            return f"【失败】保存新 Skill 文件时发生异常: {str(e)}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills_path", type=str, required=True, help="由反思阶段生成的 skills.json 文件的路径")
    se=SkillExecutor()
    args = parser.parse_args()
    res_ls=load_json(args.skills_path)
    for res in res_ls:
        print(se.manage_skill_from_response(res))