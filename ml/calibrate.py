"""Fit monotonic visual severity calibration from expert labels; no invented field measurements."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def fit(rows):
    grouped = {}
    for row in rows:
        x, y = float(row["raw_score"]), float(row["expert_score"])
        if not (0 <= x <= 100 and 0 <= y <= 100):
            raise ValueError("Scores must be in [0,100]")
        grouped.setdefault(x, []).append(y)
    if len(grouped) < 2:
        raise ValueError("Need at least two distinct screening scores")
    blocks = []
    for x, ys in sorted(grouped.items()):
        blocks.append({"xs": [x], "total": sum(ys), "count": len(ys)})
        while len(blocks) > 1 and blocks[-2]["total"]/blocks[-2]["count"] > blocks[-1]["total"]/blocks[-1]["count"]:
            b, a = blocks.pop(), blocks.pop()
            blocks.append({"xs": a["xs"]+b["xs"], "total": a["total"]+b["total"], "count": a["count"]+b["count"]})
    return [[x, block["total"]/block["count"]] for block in blocks for x in block["xs"]]


def interpolate(knots, x):
    if x <= knots[0][0]:
        return knots[0][1]
    for (a, b), (c, d) in zip(knots, knots[1:]):
        if a <= x <= c:
            return b+(x-a)/(c-a)*(d-b)
    return knots[-1][1]


def calibrate(path, version, provenance, model_sha256):
    if len(model_sha256) != 64 or any(c not in '0123456789abcdef' for c in model_sha256):
        raise ValueError("Provide the deployed model's lowercase SHA-256 digest")
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    train, test = [r for r in rows if r["split"] == "train"], [r for r in rows if r["split"] == "test"]
    if len(train) < 20 or len(test) < 10:
        raise ValueError("Need at least 20 calibration and 10 held-out expert ratings; more are recommended")
    if {r["route_group"] for r in train} & {r["route_group"] for r in test}:
        raise ValueError("Calibration route leakage")
    if any(r["split"] not in {"train", "test"} for r in rows):
        raise ValueError("Unsupported split")
    if any(not (0 <= float(r[k]) <= 100) for r in rows for k in ("raw_score", "expert_score")):
        raise ValueError("Invalid scores")
    knots = fit(train)
    mae = sum(abs(interpolate(knots, float(r["raw_score"]))-float(r["expert_score"])) for r in test)/len(test)
    return {"version": version, "target": "expert_visual_severity_0_100", "knots": knots,
            "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "provenance": provenance,
            "model_sha256": model_sha256, "scoring_policy": "visual-screening-v1",
            "heldout_mae": mae, "train_count": len(train), "test_count": len(test),
            "limitations": "Expert visual ratings only; not measured depth, area or certified PCI"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--model-sha256", required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(calibrate(args.csv, args.version, args.provenance, args.model_sha256), indent=2))

