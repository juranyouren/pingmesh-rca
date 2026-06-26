"""
标注助手
========
读取推理结果 res.json, 如果预测 Top-1 IP 命中了 label.json 中某一条的 abnormal_node,
则只保留命中的那条 (删掉其他), 并将 case 目录复制到 nodes_extend_labeled。
未命中的 case 留在原地供人工标注。

用法:
  python tmp/labeling_helper.py /path/to/nodes_extend /path/to/res.json
  python tmp/labeling_helper.py /path/to/nodes_extend /path/to/res.json --write
  python tmp/labeling_helper.py /path/to/nodes_extend /path/to/res.json --use-skill --write
"""

import os, json, sys, shutil, re


def _parse_top1_ip(response_text):
    if not response_text or not isinstance(response_text, str):
        return None
    m = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(1))
            ips = data.get("ip", [])
            if isinstance(ips, str): ips = [ips]
            if ips: return ips[0]
        except Exception: pass
    m = re.search(r'"ip"\s*:\s*"(\d{1,3}(?:\.\d{1,3}){3})"', response_text)
    if m: return m.group(1)
    m = re.search(r'\b([\da-fA-F:]+(?::[\da-fA-F]+){2,})\b', response_text)
    if m: return m.group(1)
    return None


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f: return json.load(f)


def _save_json(data, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/sbp/lixinyang/pingmesh/data/node/nodes_extend"
    res_path = sys.argv[2] if len(sys.argv) > 2 else ""
    write = "--write" in sys.argv
    use_skill = "--use-skill" in sys.argv

    print(f"数据目录: {src}")
    print(f"res.json: {res_path}")
    print(f"预测来源: {'skill_ips' if use_skill else 'LLM response'}\n")

    if not res_path:
        print("usage: python tmp/labeling_helper.py <nodes_dir> <res.json> [--write]")
        sys.exit(1)

    res_data = _load_json(res_path)

    auto_labeled, need_manual = [], []

    for rd in res_data:
        case_dir = rd.get("dir", "")
        csn = os.path.basename(case_dir)

        # 获取预测 Top-1
        if use_skill:
            skill_ips = rd.get("skill_ips", [])
            pred_top1 = skill_ips[0] if skill_ips else None
        else:
            pred_top1 = _parse_top1_ip(rd.get("response", rd.get("draft_response", "")))

        if not pred_top1:
            need_manual.append({"csn": csn, "case_dir": case_dir, "reason": "无法解析预测 Top-1"})
            continue

        label_path = os.path.join(case_dir, "label.json")
        if not os.path.exists(label_path):
            need_manual.append({"csn": csn, "case_dir": case_dir, "reason": "无 label.json"})
            continue

        labels = _load_json(label_path)
        if not isinstance(labels, list) or not labels:
            need_manual.append({"csn": csn, "case_dir": case_dir, "reason": "label.json 为空"})
            continue

        matched_idx = None
        for i, lb in enumerate(labels):
            for an in lb.get("abnormal_node", []):
                if not isinstance(an, dict): continue
                ip = an.get("ip", an.get("mgmt_ip", ""))
                if ip == pred_top1:
                    matched_idx = i; break
            if matched_idx is not None: break

        if matched_idx is None:
            need_manual.append({"csn": csn, "case_dir": case_dir,
                                "reason": f"预测 {pred_top1} 未命中 label 中任何一条"})
            continue

        auto_labeled.append({"csn": csn, "case_dir": case_dir,
                             "pred_top1": pred_top1, "matched_idx": matched_idx,
                             "labels_before": len(labels)})

    print(f"自动标注: {len(auto_labeled)}")
    print(f"需人工:   {len(need_manual)}\n")

    if auto_labeled:
        print("--- 自动标注 case (前 10) ---")
        for a in auto_labeled[:10]:
            print(f"  {a['csn']}: {a['pred_top1']} (label[{a['matched_idx']}], 删除 {a['labels_before'] - 1} 条)")
        if len(auto_labeled) > 10: print(f"  ... 还有 {len(auto_labeled) - 10} 个")

    if need_manual:
        print("\n--- 需人工标注 ---")
        for m in need_manual[:10]:
            print(f"  {m['csn']}: {m['reason']}")
        if len(need_manual) > 10: print(f"  ... 还有 {len(need_manual) - 10} 个")

    if write and auto_labeled:
        dst = src.rstrip("/").rstrip("\\") + "_labeled"
        os.makedirs(dst, exist_ok=True)
        for a in auto_labeled:
            dst_dir = os.path.join(dst, a["csn"])
            if os.path.exists(dst_dir): shutil.rmtree(dst_dir)
            shutil.copytree(a["case_dir"], dst_dir)
            labels = _load_json(os.path.join(dst_dir, "label.json"))
            kept = labels[a["matched_idx"]]
            kept["ranking"] = 1
            _save_json([kept], os.path.join(dst_dir, "label.json"))

        print(f"\n>> 已写入 {len(auto_labeled)} 个 case -> {dst}")
        print(f">> label.json 已裁剪为命中的 1 条")
        print(f">> {len(need_manual)} 个 case 留在 {src} 待人工标注")
    elif not write:
        print("\n>> DRY RUN -- 加 --write 执行")


if __name__ == "__main__":
    main()
