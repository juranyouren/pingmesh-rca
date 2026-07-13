#!/usr/bin/env python3
"""Quantify alarm/log volume on the Top-K highest-volume devices.

The script deliberately does not read ``label.json``. Devices are ranked by
``alarm_count + log_count``. Outputs are anonymized by default and contain
counts only (never alarm descriptions).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Sys.utils.alarm_utils import event_name
from Sys.utils.case_utils import find_full_link_file, get_device_ip, load_case_nodes


METRICS = (
    "alarm_count",
    "log_count",
    "event_count",
    "distinct_event_type_count",
    "description_chars",
    "estimated_tokens",
)


def _description_chars(events: Iterable[Any]) -> int:
    total = 0
    for event in events:
        if isinstance(event, dict):
            description = event.get("description", event.get("desc", event.get("message", "")))
            total += len(str(description)) if description is not None else 0
        elif isinstance(event, str):
            total += len(event)
    return total


def device_evidence_stats(node: dict[str, Any], chars_per_token: float = 4.0) -> dict[str, int]:
    """Return count-only evidence statistics for one device."""
    alarms = node.get("alarms", []) if isinstance(node.get("alarms", []), list) else []
    logs = node.get("logs", []) if isinstance(node.get("logs", []), list) else []
    events = alarms + logs
    names = {name for name in (event_name(event) for event in events) if name}
    chars = _description_chars(events)
    return {
        "alarm_count": len(alarms),
        "log_count": len(logs),
        "event_count": len(events),
        "distinct_event_type_count": len(names),
        "description_chars": chars,
        "estimated_tokens": math.ceil(chars / chars_per_token) if chars else 0,
    }


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, matching the common NumPy definition."""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        return {key: 0 for key in ("n", "sum", "mean", "median", "p90", "p95", "p99", "max")}
    return {
        "n": len(values),
        "sum": sum(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def event_bucket(count: int) -> str:
    if count == 0:
        return "0"
    if count < 10:
        return "1-9"
    if count < 50:
        return "10-49"
    if count < 100:
        return "50-99"
    if count < 500:
        return "100-499"
    return "500+"


def rank_nodes_by_event_volume(nodes: Sequence[dict[str, Any]], top_k: int) -> list[str]:
    """Rank devices by alarm+log count with deterministic tie breaking.

    Alarm count, log count, and finally device IP/name are used only when total
    event counts tie. Duplicate device identifiers are retained once.
    """
    ranked: list[tuple[int, int, int, str]] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        device_id = get_device_ip(node)
        if device_id == "unknown" or device_id in seen:
            continue
        seen.add(device_id)
        stats = device_evidence_stats(node)
        ranked.append((stats["event_count"], stats["alarm_count"], stats["log_count"], device_id))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    return [device_id for _events, _alarms, _logs, device_id in ranked[:top_k]]


def discover_cases(data_root: Path) -> list[Path]:
    cases: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" in filenames and find_full_link_file(dirpath, filenames):
            cases.append(Path(dirpath))
    return sorted(cases, key=lambda path: str(path))


def collect_rows(
    data_root: Path,
    top_k: int,
    chars_per_token: float,
    anonymize: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    device_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for case_index, case_dir in enumerate(discover_cases(data_root), 1):
        raw_case_id = case_dir.name
        case_id = f"case_{case_index:06d}" if anonymize else raw_case_id
        try:
            nodes = load_case_nodes(str(case_dir))
            focused_ips = rank_nodes_by_event_volume(nodes, top_k)
            focus_rank = {ip: rank for rank, ip in enumerate(focused_ips, 1)}
            current_rows: list[dict[str, Any]] = []
            for device_index, node in enumerate(nodes, 1):
                if not isinstance(node, dict):
                    continue
                ip = get_device_ip(node)
                if ip == "unknown":
                    continue
                stats = device_evidence_stats(node, chars_per_token)
                row = {
                    "case_id": case_id,
                    "device_id": f"{case_id}_device_{device_index:06d}" if anonymize else ip,
                    "role": str(node.get("role", "unknown") or "unknown"),
                    "is_focused": ip in focus_rank,
                    "focus_rank": focus_rank.get(ip, ""),
                    **stats,
                    "event_volume_bucket": event_bucket(stats["event_count"]),
                }
                current_rows.append(row)
            device_rows.extend(current_rows)

            focused = [row for row in current_rows if row["is_focused"]]
            summary_row: dict[str, Any] = {
                "case_id": case_id,
                "all_device_count": len(current_rows),
                "focused_device_count": len(focused),
                "device_reduction_ratio": _reduction(len(focused), len(current_rows)),
            }
            for metric in METRICS:
                all_total = sum(row[metric] for row in current_rows)
                focused_total = sum(row[metric] for row in focused)
                summary_row[f"all_{metric}"] = all_total
                summary_row[f"focused_{metric}"] = focused_total
                summary_row[f"{metric}_reduction_ratio"] = _reduction(focused_total, all_total)
            case_rows.append(summary_row)
        except Exception as exc:  # keep a bad case from invalidating the dataset report
            errors.append({"case_id": case_id, "error": f"{type(exc).__name__}: {exc}"})
    return device_rows, case_rows, errors


def _reduction(selected: int | float, total: int | float) -> float:
    return 1.0 - selected / total if total else 0.0


def aggregate_report(
    device_rows: list[dict[str, Any]], case_rows: list[dict[str, Any]], config: dict[str, Any], errors: list[dict[str, str]]
) -> dict[str, Any]:
    focused = [row for row in device_rows if row["is_focused"]]
    all_devices = device_rows
    report: dict[str, Any] = {
        "config": config,
        "dataset": {
            "case_count": len(case_rows),
            "all_device_count": len(all_devices),
            "focused_device_count": len(focused),
            "failed_case_count": len(errors),
        },
        "focused_device_statistics": {},
        "all_device_statistics": {},
        "per_case_focused_total_statistics": {},
        "per_case_all_total_statistics": {},
        "by_role": {},
        "by_focus_rank": {},
        "focused_event_volume_buckets": {},
        "case_compression_statistics": {},
        "errors": errors,
    }
    large_threshold = int(config.get("large_event_threshold", 10))
    focused_with_events = sum(row["event_count"] > 0 for row in focused)
    focused_large = sum(row["event_count"] >= large_threshold for row in focused)
    focused_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in focused:
        focused_by_case[row["case_id"]].append(row)
    report["claim_support"] = {
        "large_event_threshold": large_threshold,
        "focused_devices_with_events": focused_with_events,
        "focused_devices_with_events_ratio": focused_with_events / len(focused) if focused else 0.0,
        "focused_devices_at_or_above_threshold": focused_large,
        "focused_devices_at_or_above_threshold_ratio": focused_large / len(focused) if focused else 0.0,
        "cases_where_every_focused_device_has_events": sum(
            bool(rows) and all(row["event_count"] > 0 for row in rows) for rows in focused_by_case.values()
        ),
        "cases_where_every_focused_device_meets_threshold": sum(
            bool(rows) and all(row["event_count"] >= large_threshold for row in rows)
            for rows in focused_by_case.values()
        ),
    }
    for metric in METRICS:
        report["focused_device_statistics"][metric] = summarize([row[metric] for row in focused])
        report["all_device_statistics"][metric] = summarize([row[metric] for row in all_devices])
        report["per_case_focused_total_statistics"][metric] = summarize(
            [row[f"focused_{metric}"] for row in case_rows]
        )
        report["per_case_all_total_statistics"][metric] = summarize([row[f"all_{metric}"] for row in case_rows])
        report["case_compression_statistics"][f"{metric}_reduction_ratio"] = summarize(
            [row[f"{metric}_reduction_ratio"] for row in case_rows]
        )
    report["case_compression_statistics"]["device_reduction_ratio"] = summarize(
        [row["device_reduction_ratio"] for row in case_rows]
    )

    for field, output_key in (("role", "by_role"), ("focus_rank", "by_focus_rank")):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in focused:
            groups[str(row[field])].append(row)
        report[output_key] = {
            key: {metric: summarize([row[metric] for row in rows]) for metric in METRICS}
            for key, rows in sorted(groups.items())
        }
    buckets: dict[str, int] = defaultdict(int)
    for row in focused:
        buckets[row["event_volume_bucket"]] += 1
    report["focused_event_volume_buckets"] = {
        bucket: buckets[bucket] for bucket in ("0", "1-9", "10-49", "50-99", "100-499", "500+")
    }
    return report


def _fmt(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def markdown_summary(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    focused = report["focused_device_statistics"]
    case_focus = report["per_case_focused_total_statistics"]
    compression = report["case_compression_statistics"]
    support = report["claim_support"]
    lines = [
        "# 聚焦设备告警/日志量统计",
        "",
        "## 数据与口径",
        "",
        f"共统计 {dataset['case_count']:,} 个 case、{dataset['all_device_count']:,} 个全链路设备；"
        f"按 alarm 数与 log 数之和降序选出 {dataset['focused_device_count']:,} 个 Top-K 高事件量设备。",
        "告警与日志逐条计数；事件类型按 name/alarm_name 去重；估算 token = 描述字符数 / "
        f"{report['config']['chars_per_token']:g}（向上取整）。结果不读取 label.json，且默认匿名化。",
        "",
        "## 聚焦设备：每设备证据量",
        "",
        f"有事件的聚焦设备占 {support['focused_devices_with_events_ratio']:.1%}；若将“大量”操作化定义为至少 "
        f"{support['large_event_threshold']} 条事件，达标设备占 {support['focused_devices_at_or_above_threshold_ratio']:.1%}。",
        "",
        "| 指标 | 均值 | 中位数 | P90 | P95 | P99 | 最大值 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "alarm_count": "alarm 数",
        "log_count": "log 数",
        "event_count": "总事件数",
        "distinct_event_type_count": "去重事件类型数",
        "description_chars": "描述字符数",
        "estimated_tokens": "估算 token 数",
    }
    for metric in METRICS:
        stats = focused[metric]
        lines.append(
            f"| {labels[metric]} | {_fmt(stats['mean'])} | {_fmt(stats['median'])} | {_fmt(stats['p90'])} | "
            f"{_fmt(stats['p95'])} | {_fmt(stats['p99'])} | {_fmt(stats['max'])} |"
        )
    lines.extend(
        [
            "",
            "## 每 case 的 Top-K 聚焦设备合计",
            "",
            "| 指标 | 均值 | 中位数 | P90 | P95 | P99 | 最大值 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in METRICS:
        stats = case_focus[metric]
        lines.append(
            f"| {labels[metric]} | {_fmt(stats['mean'])} | {_fmt(stats['median'])} | {_fmt(stats['p90'])} | "
            f"{_fmt(stats['p95'])} | {_fmt(stats['p99'])} | {_fmt(stats['max'])} |"
        )
    device_reduction = compression["device_reduction_ratio"]
    event_reduction = compression["event_count_reduction_ratio"]
    lines.extend(
        [
            "",
            "## 全链路到 Top-K 的压缩效果",
            "",
            f"按 case 计算，设备数减少比例中位数为 {device_reduction['median']:.1%}（P90 {device_reduction['p90']:.1%}）；"
            f"事件数减少比例中位数为 {event_reduction['median']:.1%}（P90 {event_reduction['p90']:.1%}）。",
            "",
            "## 结论与可引用表述",
            "",
        ]
    )
    if dataset["focused_device_count"] and support["focused_devices_at_or_above_threshold_ratio"] == 1.0:
        lines.append(
            f"> 在 {dataset['case_count']:,} 个生产网络案例中，每个事件量 Top-{report['config']['top_k']} 设备均包含至少 "
            f"{support['large_event_threshold']} 条告警/日志；每设备中位数为 "
            f"{focused['event_count']['median']:.1f} 条，P95 为 {focused['event_count']['p95']:.1f} 条。"
        )
    elif support["focused_devices_with_events_ratio"] > 0:
        lines.append(
            f"> 在 {dataset['case_count']:,} 个生产网络案例中，{support['focused_devices_with_events_ratio']:.1%} 的聚焦设备"
            f"包含告警/日志，每设备中位数为 {focused['event_count']['median']:.1f} 条，"
            f"P95 为 {focused['event_count']['p95']:.1f} 条。数据不支持“每一个设备都有大量告警”的绝对表述。"
        )
    else:
        lines.append(
            "> 当前输入数据的聚焦设备均无 alarm/log 记录，不能据此支撑“每一个受影响设备都有大量告警日志信息”。"
        )
    lines.append("")
    if dataset["failed_case_count"]:
        lines.append(f"> 注意：另有 {dataset['failed_case_count']} 个 case 处理失败，详见 JSON 的 errors 字段。")
        lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def timestamped_output_dir(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return Path("data/res") / f"focus_device_evidence_{timestamp}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计告警与日志总数最多的 Top-K 设备")
    parser.add_argument(
        "data_root",
        type=Path,
        nargs="?",
        default=Path("data/node/nodes_max_labeled"),
        help="node case 数据根目录（默认: data/node/nodes_max_labeled）",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录；默认在 data/res 下按当前时间戳生成",
    )
    parser.add_argument("-k", "--top-k", type=int, default=5)
    parser.add_argument("--chars-per-token", type=float, default=4.0)
    parser.add_argument("--large-event-threshold", type=int, default=10, help="将“大量”定义为至少多少条事件")
    parser.add_argument("--no-anonymize", action="store_true", help="输出原始 case/device 标识（谨慎使用）")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or timestamped_output_dir()
    if args.top_k < 1:
        raise SystemExit("--top-k 必须大于 0")
    if args.chars_per_token <= 0:
        raise SystemExit("--chars-per-token 必须大于 0")
    if args.large_event_threshold < 1:
        raise SystemExit("--large-event-threshold 必须大于 0")
    if not args.data_root.is_dir():
        raise SystemExit(f"数据目录不存在: {args.data_root}")

    config = {
        "top_k": args.top_k,
        "selection": "alarm_count_plus_log_count_desc",
        "chars_per_token": args.chars_per_token,
        "anonymized": not args.no_anonymize,
        "large_event_threshold": args.large_event_threshold,
    }
    device_rows, case_rows, errors = collect_rows(
        args.data_root,
        args.top_k,
        args.chars_per_token,
        not args.no_anonymize,
    )
    report = aggregate_report(device_rows, case_rows, config, errors)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "device_statistics.csv", device_rows)
    write_csv(output_dir / "case_statistics.csv", case_rows)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(markdown_summary(report), encoding="utf-8")
    print(
        f"完成: {report['dataset']['case_count']} cases, "
        f"{report['dataset']['focused_device_count']} focused devices -> {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
