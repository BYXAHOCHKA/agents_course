import csv
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read_logs(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def interval(scores):
    values = np.asarray(scores, dtype=float)
    samples = np.random.default_rng(42).choice(values, (10000, len(values)), replace=True)
    return np.quantile(samples.mean(axis=1), [0.025, 0.975]).tolist()


def write_csv(path, rows):
    with Path(path).open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze_selection():
    logs = read_logs("logs/selection.jsonl")
    queries = json.loads(Path("data/queries.json").read_text())
    rows = []
    for n in [5, 20, 50, 100]:
        for variant in ["A", "B"]:
            selected = [r for r in logs if r["n"] == n and r["variant"] == variant]
            lookup = {(r["query_id"], r["repeat"]): r for r in selected}
            assert len(lookup) == len(selected), "Дубли попыток в логах"
            scores = [
                sum(lookup.get((q["id"], repeat), {}).get("success", False)
                    for repeat in range(3)) / 3
                for q in queries
            ]
            low, high = interval(scores)
            tokens = [r["input_tokens"] for r in selected if r.get("input_tokens") is not None]
            rows.append({
                "n": n, "variant": variant, "expected": 90,
                "logged": len(selected), "correct": sum(r["success"] for r in selected),
                "accuracy": float(np.mean(scores)), "ci_low": low, "ci_high": high,
                "recall_at_5": sum(r["recall_at_5"] for r in selected) / 90,
                "mean_input_tokens": float(np.mean(tokens)) if tokens else None,
                "token_usage_known": len(tokens),
            })
    write_csv("results/selection.csv", rows)
    fig, ax = plt.subplots(figsize=(6, 3.4))
    for variant in ["A", "B"]:
        group = [r for r in rows if r["variant"] == variant]
        y = np.array([r["accuracy"] for r in group])
        errors = [y - [r["ci_low"] for r in group], [r["ci_high"] for r in group] - y]
        ax.errorbar([r["n"] for r in group], y, yerr=errors, marker="o", capsize=4, label=variant)
    ax.set(xlabel="N", ylabel="Accuracy", ylim=(-0.03, 1.03), xticks=[5, 20, 50, 100])
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig("results/accuracy.png", dpi=180)
    plt.close(fig)
    return rows


def analyze_loops():
    logs = read_logs("logs/loops.jsonl")
    tasks = json.loads(Path("data/loop_tasks.json").read_text())
    rows = []
    for condition in ["empty", "guard", "hint"]:
        selected = [r for r in logs if r["condition"] == condition]
        lookup = {(r["task_id"], r["repeat"]): r for r in selected}
        assert len(lookup) == len(selected), "Дубли эпизодов в логах"
        episodes = [lookup.get((t["id"], repeat)) for t in tasks for repeat in range(3)]
        steps = [r["steps"] for r in episodes if r is not None]
        tokens = [r["tokens"] for r in episodes if r is not None and r["usage_complete"]]
        count = len(episodes)
        rows.append({
            "condition": condition, "expected": count, "logged": len(selected),
            "loop_rate": sum(bool(r and r["loop"]) for r in episodes) / count,
            "success_rate": sum(bool(r and r["success"]) for r in episodes) / count,
            "mean_steps": float(np.mean(steps)) if steps else None,
            "mean_tokens": float(np.mean(tokens)) if tokens else None,
            "steps_known": len(steps), "token_usage_known": len(tokens),
            "unfinished": sum(r is None or r["status"] in ["error", "step_limit"] for r in episodes),
        })
    write_csv("results/loops.csv", rows)
    return rows


def main():
    Path("results").mkdir(exist_ok=True)
    print(analyze_selection())
    print(analyze_loops())


if __name__ == "__main__":
    main()
