"""第一轮新实验（r3）的统计分析。

输入是归档 `eval/telemetry/r3.jsonl`，输出是终端表 + 可直接贴进 RESULTS 的
markdown。分开算两类指标：

  过程指标（lint）：首次通过率 / 返工份数。BASE 组没有 lint——裸跑没有门禁，
                    这正是条件差异本身，不能当成「数据缺失」。
  结果指标（critic）：三条价值观 0-3 分、合计 /9、静默降级率、结论分布。

刻意不把两类指标合成一个总分：lint 判结构，critic 判质量，合成会掩盖
「结构全过但实质空洞」这个最该被看见的组合。
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ARCHIVE = ROOT / "eval" / "telemetry" / "r3.jsonl"

CONDS = ["BASE", "OPEN", "BLIND"]
STAGES = ["pre_task", "pre_deliver", "post_task"]
KEYS = [("first_principles", "第一性"), ("extremeness", "求极致"), ("co_growth", "共成长")]


def load():
    recs = [json.loads(l) for l in ARCHIVE.read_text(encoding="utf-8").splitlines() if l.strip()]
    return recs


def main():
    recs = load()
    lint = [r for r in recs if r.get("kind", "lint") == "lint"]
    critic = [r for r in recs if r.get("kind") == "critic"]

    print(f"数据源：{ARCHIVE.relative_to(ROOT)}")
    print(f"lint {len(lint)} 条，critic {len(critic)} 条\n")

    # ---- 过程指标 ----
    print("## 一、lint 过程指标（只有 OPEN / BLIND 有门禁）\n")
    print("| 阶段 | 条件 | 产出数 | 首次通过 | 首次通过率 | 返工份数 |")
    print("|---|---|---|---|---|---|")
    for stage in STAGES:
        for cond in CONDS:
            rs = [r for r in lint if r["stage"] == stage and r["condition"] == cond]
            if not rs:
                print(f"| {stage} | {cond} | 0 | — | 无门禁 | — |")
                continue
            arts = {}
            for r in rs:
                a = arts.setdefault(r["artifact"], {"first": None, "failed_any": False})
                if r.get("trial", 1) == 1:
                    a["first"] = r["passed"]
                if not r["passed"]:
                    a["failed_any"] = True
            first_ok = sum(1 for a in arts.values() if a["first"])
            rework = sum(1 for a in arts.values() if a["failed_any"])
            rate = first_ok / len(arts) * 100
            print(f"| {stage} | {cond} | {len(arts)} | {first_ok} | {rate:.0f}% | {rework} |")

    # ---- 结果指标 ----
    print("\n## 二、critic 结果指标（0-3 分，盲评）\n")
    print("| 阶段 | 条件 | n | 第一性 | 求极致 | 共成长 | 合计/9 | 静默降级 | 可交付率 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for stage in STAGES:
        for cond in CONDS:
            rs = [r for r in critic if _stage_of(r) == stage and _cond_of(r) == cond]
            if not rs:
                print(f"| {stage} | {cond} | 0 | — | — | — | — | — | — |")
                continue
            cells = []
            for k, _ in KEYS:
                vals = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
                cells.append(f"{st.mean(vals):.2f}" if vals else "—")
            total = []
            for r in rs:
                v = [r.get(k) for k, _ in KEYS]
                if all(isinstance(x, (int, float)) for x in v):
                    total.append(sum(v))
            sd = sum(1 for r in rs if r.get("silent_downgrade"))
            ok = sum(1 for r in rs if r.get("verdict") == "可交付")
            print(
                f"| {stage} | {cond} | {len(rs)} | {' | '.join(cells)} | "
                f"{st.mean(total):.2f} | {sd}/{len(rs)} | {ok}/{len(rs)} |"
            )

    # ---- 汇总 ----
    print("\n## 三、跨阶段汇总\n")
    print("| 条件 | n | 第一性 | 求极致 | 共成长 | 合计/9 | 静默降级 | 可交付率 |")
    print("|---|---|---|---|---|---|---|---|")
    for cond in CONDS:
        rs = [r for r in critic if _cond_of(r) == cond]
        if not rs:
            continue
        cells = []
        for k, _ in KEYS:
            vals = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
            cells.append(f"{st.mean(vals):.2f}" if vals else "—")
        total = [
            sum(r.get(k) for k, _ in KEYS)
            for r in rs
            if all(isinstance(r.get(k), (int, float)) for k, _ in KEYS)
        ]
        sd = sum(1 for r in rs if r.get("silent_downgrade"))
        ok = sum(1 for r in rs if r.get("verdict") == "可交付")
        print(
            f"| {cond} | {len(rs)} | {' | '.join(cells)} | {st.mean(total):.2f} | "
            f"{sd}/{len(rs)} | {ok}/{len(rs)} |"
        )

    # ---- 打分器区分度 ----
    print("\n## 四、打分器区分度（同一维度所有评分的分布）\n")
    print("| 维度 | n | 均值 | 标准差 | 取值分布 |")
    print("|---|---|---|---|---|")
    for k, label in KEYS:
        vals = [r[k] for r in critic if isinstance(r.get(k), (int, float))]
        dist = {v: vals.count(v) for v in sorted(set(vals))}
        sd = st.pstdev(vals) if len(vals) > 1 else 0.0
        print(
            f"| {label} | {len(vals)} | {st.mean(vals):.2f} | {sd:.2f} | "
            f"{' / '.join(f'{v}分:{n}' for v, n in dist.items())} |"
        )
    return 0


def _cond_of(r):
    if r.get("condition"):
        return r["condition"]
    p = Path(str(r.get("artifact", "")))
    return p.parts[-2] if len(p.parts) >= 2 else "?"


def _stage_of(r):
    p = Path(str(r.get("artifact", "")))
    return p.stem if p.suffix == ".md" else "?"


if __name__ == "__main__":
    sys.exit(main())
