"""遥测：没有指标就没有价值观。

每次 lint 都是一条数据点。默认写入 <root>/.vh/telemetry.jsonl。
critic 评分也写在这里，用 kind 字段区分——lint 是过程指标，critic 是结果指标。

`.vh/` 不进版本库（运行时数据），实验数据用 `vh report --export` 归档到
eval/telemetry/，那份进库。否则 clone 下来跑 report 是空的，所有数字不可复现。
"""

from __future__ import annotations

import json
import os
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


def _next_trial(root: Path, stage: str, artifact: str) -> int:
    """同一份产出在同一阶段的第几次 lint。

    返工次数是这套 harness 最主要的副作用指标——没有它就算不出「返工有多磨」，
    也没法把「同一份文件改 6 次才过」和「6 份不同的文件各过各的」区分开。

    代价是每次追加都重读整个 jsonl。几十条的规模下可以接受；上千条时改成
    维护一个计数文件，见 docs/AUDIT.md 的技术债。
    """
    n = sum(
        1
        for r in load_all(root)
        if r.get("stage") == stage and r.get("artifact") == artifact
    )
    return n + 1


def record(root: Path, stage: str, artifact_path: str, findings, task: str | None = None):
    failed = [f.rule for f in findings if not f.ok and not f.skipped]
    blocking = [f.rule for f in findings if f.blocking_fail]
    rec = {
        "ts": _now(),
        "kind": "lint",
        "stage": stage,
        "artifact": artifact_path,
        "trial": _next_trial(root, stage, artifact_path),
        "task": (task or "")[:200],
        "passed": not blocking,
        "failed": failed,
        "blocking": blocking,
        "warnings": [f.rule for f in findings if not f.ok and f.severity != "blocking"],
        # skipped 必须落盘：一条规则「查过且通过」和「压根没触发」是两件事，
        # 不区分就分不清它太松还是太窄。
        "skipped": [f.rule for f in findings if f.skipped],
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


# 临时目录里的记录是探针文件，不是业务产出。归档时默认剔掉——它们会把
# 通过率拉向「测试脚本随手写的那份」，而那份不代表任何真实任务。
EPHEMERAL_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")


def _ephemeral(path: str) -> bool:
    low = path.replace("\\", "/").lower()
    if any(low.startswith(p) for p in EPHEMERAL_PREFIXES):
        return True
    # Windows 的临时目录挂在用户目录下，只能靠中段匹配
    return "/temp/" in low or "/tmp/" in low


def export(root: Path, dest: Path, include_all: bool = False) -> int:
    """把当前 telemetry 归档到 dest，返回归档后的记录条数。

    默认剔除临时目录的记录；`include_all=True` 保留全部（排查用）。
    不直接 copyfile 是因为归档文件要进版本库，脏数据会被当成实验数据引用。
    """
    dest = Path(dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    recs = load_all(root)
    if not include_all:
        recs = [r for r in recs if not _ephemeral(r.get("artifact", ""))]
    dest.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
        encoding="utf-8",
    )
    return len(recs)


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


def _final_by_artifact(lint_recs: list[dict]) -> dict:
    """按 (阶段, 产出) 取最后一次，算「最终交付合格率」。

    按 lint 次数算会把返工次数算成样本量：一份文件失败 6 次再通过，在旧口径
    下贡献 5 个失败样本，通过率被压掉十几个点。两个口径回答两个不同问题——
    按文件问「交付合不合格」，按次数问「返工有多磨」——都要留，删任一个都会
    制造新盲区。
    """
    counts: dict[tuple, int] = {}
    failed_any: set[tuple] = set()
    last: dict[tuple, dict] = {}
    for r in lint_recs:
        key = (r["stage"], r["artifact"])
        counts[key] = counts.get(key, 0) + 1
        if not r.get("passed", True):
            failed_any.add(key)
        last[key] = r

    out: dict[str, dict] = {}

    def blank():
        return {"artifacts": 0, "passed": 0, "rework": 0, "first_runs": 0, "first_passed": 0}

    for key, r in last.items():
        st = out.setdefault(key[0], blank())
        st["artifacts"] += 1
        if r["passed"]:
            st["passed"] += 1
        # 返工 = 被拦下过至少一次。用「lint 次数 > 1」判会把手动重复校验也算成返工——
        # 实测里就有 agent 通过后又跑了一遍确认，那不是返工，是谨慎。
        if key in failed_any:
            st["rework"] += 1

    # 首次通过率：trial=1 那次的通过情况。这才是「一次做对」的能力，
    # 最终通过率在「所有产出都修到过」的实验里恒为 100%，没有区分度。
    for r in lint_recs:
        if r.get("trial", 1) != 1:
            continue
        st = out.setdefault(r["stage"], blank())
        st["first_runs"] += 1
        if r["passed"]:
            st["first_passed"] += 1

    for st in out.values():
        st["final_pass_rate"] = (
            round(st["passed"] / st["artifacts"], 3) if st["artifacts"] else 0.0
        )
        st["first_pass_rate"] = (
            round(st["first_passed"] / st["first_runs"], 3) if st["first_runs"] else 0.0
        )
    return out


def _rule_health(lint_recs: list[dict], rules: list[dict]) -> list[dict]:
    """每条规则的触发情况：被评估几次、失败几次、跳过几次。

    零失败的规则有两种，含义完全不同：
      - 太松：每次都触发，每次都通过 → 该加强判据
      - 太窄：从来没触发过（skipped）→ 该扩触发词，或者删掉
    不区分这两者，看 report 就只会得到「这条规则没问题」这个错误结论。

    「触发」的判定：记录里该阶段生效、且不在 skipped 列表里。
    老记录没有 skipped 字段，按「全部触发」处理——那时的行为确实如此。
    """
    stats: dict[str, dict] = {}
    stages: dict[str, set] = {}
    for r in rules:
        rid = r["id"]
        stats[rid] = {
            "rule": rid,
            "severity": r.get("severity", "warning"),
            "runs": 0,
            "fails": 0,
            "skipped": 0,
            "fail_rate": None,
        }
        stages[rid] = set(r.get("stage", []))

    for rec in lint_recs:
        stage = rec.get("stage")
        skipped = set(rec.get("skipped", []))
        failed = set(rec.get("failed", []))
        for rid, s in stats.items():
            if stage not in stages[rid]:
                continue
            if rid in skipped:
                s["skipped"] += 1
                continue
            s["runs"] += 1
            if rid in failed:
                s["fails"] += 1

    for s in stats.values():
        if s["runs"]:
            s["fail_rate"] = round(s["fails"] / s["runs"], 3)

    # 从未触发的排最前——它们是这张表里唯一需要立刻处理的一类
    return sorted(stats.values(), key=lambda s: (s["runs"], -s["skipped"], s["rule"]))


def report(root: Path, source: Path | None = None, rules: list[dict] | None = None) -> dict:
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
        "by_artifact": _final_by_artifact(lint_recs),
        "rule_fails": [{"rule": k, "fails": v["fails"]} for k, v in ranked],
        "rule_health": _rule_health(lint_recs, rules or []),
        "recent_failures": [r for r in lint_recs if not r["passed"]][-5:],
        "critic": _critic_summary(critic_recs),
    }
