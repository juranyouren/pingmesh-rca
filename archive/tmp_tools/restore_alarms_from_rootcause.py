"""
将 rootcause_analysis 所有条目中 abnormal_node 的 alarms/syslogs 追加到
full_link.alarm_list 和 full_link.log_list.data。

用法:
  python archive/tmp_tools/restore_alarms_from_rootcause.py /path/to/pingmesh_extend [--write]
"""

import os, json, sys, shutil

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/sbp/lixinyang/pingmesh/data/pingmesh_extend"
DST = SRC + "_restored"
WRITE = "--write" in sys.argv

print(f"源: {SRC}\n输出: {DST}\n")

files = [f for f in os.listdir(SRC) if f.endswith(".json")]
ok = skip = 0
total_added = 0

if WRITE:
    os.makedirs(DST, exist_ok=True)

for fname in sorted(files):
    fpath = os.path.join(SRC, fname)
    try:
        data = json.load(open(fpath, "r", encoding="utf-8"))
    except Exception:
        continue

    fl = data.get("full_link", {})
    rca = fl.get("rootcause_analysis")
    if not isinstance(rca, list) or not rca:
        skip += 1
        continue

    added = 0
    alarm_list = fl.setdefault("alarm_list", [])
    log_data = fl.setdefault("log_list", {}).setdefault("data", [])

    for item in rca:
        if not isinstance(item, dict):
            continue
        for an in item.get("abnormal_node", []):
            if not isinstance(an, dict):
                continue
            for evt in an.get("alarms", []):
                if evt not in alarm_list:
                    alarm_list.append(evt); added += 1
            for evt in an.get("syslogs", []):
                if evt not in log_data:
                    log_data.append(evt); added += 1

    ok += 1; total_added += added

    if WRITE:
        json.dump(data, open(os.path.join(DST, fname), "w", encoding="utf-8"), ensure_ascii=False)

print(f"有 rootcause_analysis: {ok}  跳过: {skip}  新增告警/日志: {total_added}")
if not WRITE:
    print(">> DRY RUN — 加 --write 写入")
else:
    print(f">> 已写入 {DST}")
