"""critic 校准的统计。

三个指标，按能证伪 critic 的强度排序：

  1. 定向命中率：期望维度上，critic 给出的分是否落进期望区间。
     这是最硬的指标——它测的是「critic 有没有按它自己写的 rubric 判」。
  2. 结论区分度：正例和反例的 verdict 分布是否分开。v1 在这里是 0（两边都零份可交付）。
  3. 稳定率：同一份产出重复评三次，极差是否 ≤1、结论是否一致。

期望值按产出类型走（拆解卡只评第一性、交付稿评第一性+求极致、复盘评共成长+第一性），
所以统计只比对 expect 里列出的维度，`null`（不适用）不参与。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "calib"
KEYS = [("first_principles", "第一性"), ("extremeness", "求极致"), ("co_growth", "共成长")]
LABEL = dict(KEYS)


def _norm(s: dict) -> dict:
    """把 {score, evidence, gap} 压成裸分数。

    critic 的输出里三个维度是对象，直接比大小会把所有判定算成 False——
    这个 bug 在第一版统计脚本里出现过，18 项维度检查全部误判为未命中。
    """
    out = dict(s)
    for k, _ in KEYS:
        node = out.get(k)
        if isinstance(node, dict):
            out[k] = node.get("score")
    return out


def _fmt(v):
    return "—" if v is None else str(v)


def main():
    mapping = json.loads((OUT / "map.json").read_text(encoding="utf-8"))
    rows = []
    for m in mapping:
        p = ROOT / m["score"]
        if not p.exists():
            print(f"缺评分：{m['score']}", file=sys.stderr)
            return 2
        rows.append((m, _norm(json.loads(p.read_text(encoding="utf-8")))))

    print("## 一、逐份结果\n")
    print("| 文件 | 类型 | 第一性 | 求极致 | 共成长 | 静默降级 | 结论 | 期望 | 判定 |")
    print("|---|---|---|---|---|---|---|---|---|")
    dim_hit = dim_total = 0
    pos_ok = pos_n = 0
    neg_hit = neg_n = 0
    sd_fp = 0

    for m, s in rows:
        cells = [_fmt(s.get(k)) for k, _ in KEYS]
        verdict = s.get("verdict", "")
        sd = bool(s.get("silent_downgrade"))

        if m["kind"] == "pos":
            pos_n += 1
            checks = []
            for d, floor in m["expect"].items():
                v = s.get(d)
                dim_total += 1
                hit = isinstance(v, (int, float)) and v >= floor
                dim_hit += hit
                checks.append(hit)
            ok = all(checks)
            pos_ok += ok
            if sd:
                sd_fp += 1
            expect = " / ".join(f"{LABEL[d]}≥{f}" for d, f in m["expect"].items())
            judge = "命中" if ok else "偏低"
        else:
            neg_n += 1
            dim = next(iter(m["expect"]))
            if dim == "silent_downgrade":
                ok = sd is True
                expect = "静默降级=true"
            else:
                ceil = m["expect"][dim]
                v = s.get(dim)
                ok = isinstance(v, (int, float)) and v <= ceil
                expect = f"{LABEL[dim]} ≤{ceil}"
            neg_hit += ok
            judge = "命中" if ok else "未命中"

        print(
            f"| {Path(m['path']).name} | {m['kind']} | {' | '.join(cells)} | "
            f"{'true' if sd else 'false'} | {verdict} | {expect} | {judge} |"
        )

    print("\n## 二、汇总\n")
    print(f"- **维度命中率（适用维度落进期望）**：{dim_hit}/{dim_total} = {dim_hit/dim_total*100:.0f}%")
    print(f"- **正例全维达标率**：{pos_ok}/{pos_n} = {pos_ok/pos_n*100:.0f}%")
    print(f"- **反例定向命中率**：{neg_hit}/{neg_n} = {neg_hit/neg_n*100:.0f}%")
    print(f"- **静默降级假阳性**：{sd_fp}/{pos_n} 份正例被判 true")

    print("\n## 三、结论区分度\n")
    for kind in ("pos", "neg"):
        vs = [s.get("verdict") for m, s in rows if m["kind"] == kind]
        dist = {v: vs.count(v) for v in sorted(set(vs))}
        print(f"- {kind}：{dist}")
    pos_deliver = sum(1 for m, s in rows if m["kind"] == "pos" and s.get("verdict") == "可交付")
    neg_deliver = sum(1 for m, s in rows if m["kind"] == "neg" and s.get("verdict") == "可交付")
    print(
        f"- **区分度**：正例可交付 {pos_deliver}/{pos_n}，反例可交付 {neg_deliver}/{neg_n}"
        f" → {'有区分' if pos_deliver > neg_deliver else '无区分'}"
    )

    # ---- 稳定率 ----
    print("\n## 四、稳定率（同一份重复评三次）\n")
    print("| 文件 | 类型 | 三次分数 | 各维极差 | 三次结论 | 结论一致 |")
    print("|---|---|---|---|---|---|")
    stable = verdict_stable = n_rep = 0
    for m in mapping:
        runs = []
        for suf in ("", ".r2", ".r3"):
            p = OUT / "review" / f"{m['id']}{suf}.score.json"
            if p.exists():
                runs.append(_norm(json.loads(p.read_text(encoding="utf-8"))))
        if len(runs) < 3:
            continue
        n_rep += 1
        triples = [[r.get(k) for k, _ in KEYS] for r in runs]
        spreads = []
        for i, (k, _) in enumerate(KEYS):
            vals = [t[i] for t in triples if isinstance(t[i], (int, float))]
            spreads.append(max(vals) - min(vals) if len(vals) > 1 else 0)
        stable += all(x <= 1 for x in spreads)
        verdicts = [r.get("verdict") for r in runs]
        verdict_stable += len(set(verdicts)) == 1
        tri = " / ".join("/".join(_fmt(x) for x in t) for t in triples)
        print(
            f"| {Path(m['path']).name} | {m['kind']} | {tri} | {spreads} | "
            f"{'、'.join(verdicts)} | {'是' if len(set(verdicts)) == 1 else '否'} |"
        )
    if n_rep:
        print(f"\n- **分数稳定率（各维极差 ≤1）**：{stable}/{n_rep} = {stable/n_rep*100:.0f}%")
        print(
            f"- **结论稳定率（三次 verdict 一致）**：{verdict_stable}/{n_rep}"
            f" = {verdict_stable/n_rep*100:.0f}%"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
