"""
检查服务器上 temporal_score.py 是否被旧版 pyc 缓存污染。
如果 pyc 中的 temporal_score_devices 仍调用 _read_label_timestamps，
说明缓存是旧的，泄漏仍生效。

运行后删除 pycache 再重跑消融。
"""

import os
import sys
import importlib
import dis

sys.path.insert(0, "/home/sbp/lixinyang/pingmesh")

# ── 1. 直接读 .py 源码 ──
py_path = "SkillBank/skills/temporal_score.py"
with open(py_path, "r", encoding="utf-8") as f:
    py_src = f.read()
py_has_label = "label.json" in py_src or "_read_label_timestamps" in py_src
print(f"temporal_score.py 源码: {'有 label.json 引用 (未修复!)' if py_has_label else '无 label.json 引用 ✓'}")

# ── 2. 检查 pycache ──
skills_dir = os.path.dirname(py_path) or "SkillBank/skills"
pycache = os.path.join(skills_dir, "__pycache__")
print(f"\n__pycache__: {pycache}")
if os.path.isdir(pycache):
    pyc_files = [f for f in os.listdir(pycache) if "temporal" in f.lower()]
    if pyc_files:
        print(f"  发现 temporal pyc: {pyc_files}")
        for pf in pyc_files:
            pp = os.path.join(pycache, pf)
            mtime = os.path.getmtime(pp)
            import datetime
            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            py_mtime = os.path.getmtime(py_path)
            py_mtime_str = datetime.datetime.fromtimestamp(py_mtime).strftime("%Y-%m-%d %H:%M:%S")
            stale = mtime < py_mtime
            print(f"  {pf}: 修改时间={mtime_str}, {'旧于源码 (可能是旧的!)' if stale else '新于源码'}")
    else:
        print("  无 temporal pyc")
else:
    print("  不存在")

# ── 3. 清缓存 ──
import shutil
if os.path.isdir(pycache):
    shutil.rmtree(pycache)
    print(f"\n已删除 __pycache__")
print("\n>>> 请重新运行 run_full_ablation.sh 和 run_inference.sh <<<")
