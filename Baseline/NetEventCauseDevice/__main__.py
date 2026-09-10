"""Local train/predict CLI; the common runner can import the same predictor."""

import argparse
import json
from pathlib import Path

from .predictor import METHOD, VERSION, NECConfig, NetEventCauseDevice


def read_cases(path):
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    try:
        obj = json.loads(text)
        return obj.get("incidents", [obj]) if isinstance(obj, dict) else obj
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def main():
    from Baseline.common.io import normalize_incident
    parser = argparse.ArgumentParser(description="NEC ODE reimplementation with fixed-rho adapted prior")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--inputs", required=True, help="Frozen training inputs only, JSONL or JSON list")
    train.add_argument("--validation-inputs")
    train.add_argument("--checkpoint", required=True)
    train.add_argument("--config", help="JSON matching NECConfig")
    train.add_argument("--epochs", type=int)
    train.add_argument("--device", default="cpu")
    predict = commands.add_parser("predict")
    predict.add_argument("--inputs", required=True)
    predict.add_argument("--checkpoint", required=True)
    predict.add_argument("--output", required=True)
    predict.add_argument("--device", default="cpu")
    predict.add_argument("--graph", action="store_true", help="Emit native event graph with root ranking")
    args = parser.parse_args()
    if args.command == "train":
        config = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
        if args.epochs is not None:
            config["epochs"] = args.epochs
        model = NetEventCauseDevice(NECConfig(**config), device=args.device)
        model.fit([normalize_incident(case) for case in read_cases(args.inputs)],
                  validation_cases=([normalize_incident(case) for case in read_cases(args.validation_inputs)]
                                    if args.validation_inputs else None))
        model.save(args.checkpoint)
        print(json.dumps({"status": "ok", "checkpoint": str(Path(args.checkpoint).resolve()),
                          "epochs": model.config.epochs,
                          "last_epoch": model.training_report["history"][-1]}, ensure_ascii=False))
    else:
        model = NetEventCauseDevice.load(args.checkpoint, device=args.device)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        predictions = []
        for case in read_cases(args.inputs):
            try:
                normalized = normalize_incident(case)
                result = model.predict_raw_graph(normalized) if args.graph else model.predict_root(normalized)
            except (KeyError, TypeError, ValueError) as exc:
                result = {"case_id": str(case.get("case_id", "")) if isinstance(case, dict) else "",
                          "method": METHOD, "version": VERSION, "status": "input_ineligible",
                          "root_ranking": [], "diagnostics": {"reason": str(exc)}, "timing": {}}
                if args.graph:
                    result.update(nodes=[], edges=[])
            predictions.append(result)
        output.write_text("".join(json.dumps(p, ensure_ascii=False, allow_nan=False) + "\n"
                                  for p in predictions), encoding="utf-8")
        print(json.dumps({"status": "ok", "cases": len(predictions),
                          "failures": sum(p["status"] != "ok" for p in predictions),
                          "output": str(output.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
