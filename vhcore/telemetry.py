"""遥测：没有指标就没有价值观。

每次 lint 都是一条数据点。默认写入 <root>/.vh/telemetry.jsonl。
critic 评分也写在这里，用 kind 字段区分——lint 是过程指标，critic 是结果指标。

`.vh/` 不进版本库（运行时数据），实验数据用 `vh report --export` 归档到
eval/telemetry/，那份进库。否则 clone 下来跑 report 是空的，所有数字不可复现。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


def home(root: Path) -> Path:
    return Path(os.environ.get("VH_HOME", root / ".vh")).expanduser()


def _file(root: Path) -> Path:
    return home(root) / "telemetry.jsonl"


def _now() -> str:
    # 用 datetime 而不是 time.strftime("%z")：Windows 的 C 运行库对 %z 支持
    # 不一致，最坏情况下会原样吐出字面量 "%z"，把时间戳写坏。
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _append(root: Path, rec: dict):
    d = home(root)
    d.mkdir(parents=True, exist_ok=True)
    with _file(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def record(root: Path, stage: str, artifact_path: str, findings, task: str | None = None):
    failed = [f.rule for f in findings if not f.ok and not f.skipped]
    blocking = [f.rule for f in findings if f.blocking_fail]
    rec = {
        "ts": _now(),
        "kind": "lint",
        "stage": stage,
        "artifact": artifact_path,
        "task": (task or "")[:200],
        "passed": not blocking,
        "failed": failed,
        "blocking": blocking,
        "warnings": [f.rule for f in findings if not f.ok and f.severity != "blocking"],
    }
    _append(root, rec)
    return rec


CRITIC_KEYS = ("first_principles", "extremeness", "co_growth")


def record_critic(root: Path, artifact_path: str, score: dict):
    """回收一份 critic 评分。

    critic 必须在独立上下文里跑，这里只负责记录，不负责打分。
    分数结构见 evaluator/critic.md：三个维度各 0-3，外加 silent_downgrade。
    """
    rec = {
        "ts": _now(),
        "kind": "critic",
        "artifact": artifact_path,
        "silent_downgrade": bool(score.get("silent_downgrade", False)),
        "verdict": score.get("verdict", ""),
        "top_fix": score.get("top_fix", ""),
    }
    for k in CRITIC_KEYS:
        node = score.get(k)
        rec[k] = node.get("score") if isinstance(node, dict) else node
    _append(root, rec)
    return rec


def load_all(root: Path, source: Path | None = None) -> list[dict]:
    p = Path(source).expanduser() if source else _file(root)
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


def export(root: Path, dest: Path) -> int:
    """把当前 telemetry 归档到 dest，返回归档后的记录条数。"""
    src = _file(root)
    dest = Path(dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        dest.write_text("", encoding="utf-8")
        return 0
    shutil.copyfile(src, dest)
    return len(load_all(root, dest))


def _critic_summary(recs: list[dict]) -> dict:
    if not recs:
        return {"runs": 0, "means": {}, "silent_downgrade_rate": None, "verdicts": {}}
    means = {}
    for k in CRITIC_KEYS:
        vals = [r[k] for r in recs if isinstance(r.get(k), (int, float))]
        means[k] = round(sum(vals) / len(vals), 2) if vals else None
    sd = sum(1 for r in recs if r.get("silent_downgrade"))
    verdicts: dict[str, int] = {}
    for r in recs:
        v = r.get("verdict") or "未判定"
        verdicts[v] = verdicts.get(v, 0) + 1
    return {
        "runs": len(recs),
        "means": means,
        "silent_downgrade_rate": round(sd / len(recs), 3),
        "verdicts": verdicts,
    }


def report(root: Path, source: Path | None = None) -> dict:
    recs = load_all(root, source)
    lint_recs = [r for r in recs if r.get("kind", "lint") == "lint"]
    critic_recs = [r for r in recs if r.get("kind") == "critic"]

    by_stage: dict[str, dict] = {}
    rule_stats: dict[str, dict] = {}
    for r in lint_recs:
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
        "runs": len(lint_recs),
        "source": str(source) if source else None,
        "by_stage": by_stage,
        "rule_fails": [{"rule": k, "fails": v["fails"]} for k, v in ranked],
        "recent_failures": [r for r in lint_recs if not r["passed"]][-5:],
        "critic": _critic_summary(critic_recs),
    }
