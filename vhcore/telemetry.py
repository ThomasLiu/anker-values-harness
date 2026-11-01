"""遥测：没有指标就没有价值观。

每次 lint 都是一条数据点。默认写入 <root>/.vh/telemetry.jsonl。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def home(root: Path) -> Path:
    return Path(os.environ.get("VH_HOME", root / ".vh")).expanduser()


def _file(root: Path) -> Path:
    return home(root) / "telemetry.jsonl"


def record(root: Path, stage: str, artifact_path: str, findings, task: str | None = None):
    d = home(root)
    d.mkdir(parents=True, exist_ok=True)
    failed = [f.rule for f in findings if not f.ok and not f.skipped]
    blocking = [f.rule for f in findings if f.blocking_fail]
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "stage": stage,
        "artifact": artifact_path,
        "task": (task or "")[:200],
        "passed": not blocking,
        "failed": failed,
        "blocking": blocking,
        "warnings": [f.rule for f in findings if not f.ok and f.severity != "blocking"],
    }
    with _file(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_all(root: Path) -> list[dict]:
    p = _file(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def report(root: Path) -> dict:
    recs = load_all(root)
    by_stage: dict[str, dict] = {}
    rule_stats: dict[str, dict] = {}
    for r in recs:
        st = by_stage.setdefault(r["stage"], {"runs": 0, "passed": 0})
        st["runs"] += 1
        if r["passed"]:
            st["passed"] += 1
        for rid in r.get("failed", []):
            s = rule_stats.setdefault(rid, {"fails": 0})
            s["fails"] += 1
    for st in by_stage.values():
        st["pass_rate"] = round(st["passed"] / st["runs"], 3) if st["runs"] else 0.0
    ranked = sorted(rule_stats.items(), key=lambda kv: -kv[1]["fails"])
    return {
        "runs": len(recs),
        "by_stage": by_stage,
        "rule_fails": [{"rule": k, "fails": v["fails"]} for k, v in ranked],
        "recent_failures": [r for r in recs if not r["passed"]][-5:],
    }
