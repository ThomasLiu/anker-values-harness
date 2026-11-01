"""B3 critic 校准：语料准备。

设计要点：不做「正例 vs 反例平均分」这种模糊比较——反例只违反一条结构规则，
内容本身可能是合格的，平均分本来就该接近。真正能证伪 critic 的，是它能不能
在**具体维度**上复现 rubric 已经写明的判据：

    pre_deliver-rd-no-blast   对外动作没写影响范围 → 求极致 = 0（critic.md 明写不给部分分）
    pre_task-rd-hedge         假设写成「大概/应该」   → 第一性 ≤ 1
    post_task-rd-empty        只有感想没有资产        → 共成长 = 0

如果 critic 在这些位置上仍然给 2 分，说明它没有执行自己的 rubric，分数不可引用。
这比「正例 2.5、反例 2.3」这种结论有用得多——后者只能说明区分度低，前者说明它瞎了。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "calib"
REVIEW = OUT / "review"

# 正例：三条价值观都应 ≥2（rubric 里「合格」及以上）
POSITIVES = [
    "bench/positive/pre_task-rd-thermal.md",
    "bench/positive/pre_task-nonrd-cell-second-source.md",
    "bench/positive/pre_deliver-rd-recall.md",
    "bench/positive/pre_deliver-nonrd-pricing.md",
    "bench/positive/post_task-rd-recall-review.md",
    "bench/positive/post_task-nonrd-promo-review.md",
]

# 反例：每条都给出「哪一维该低分」以及判据出处
NEGATIVES = [
    (
        "bench/negative/pre_deliver-rd-no-blast.md",
        "extremeness",
        1,
        "soundcore 固件全量推送属不可逆对外动作，全文没有影响范围。critic.md：这类产出求极致 0 分，不给部分分",
    ),
    (
        "bench/negative/pre_deliver-rd-weak-redteam.md",
        "extremeness",
        1,
        "红队自查只写 2 条且都是无害表述。critic.md：红队列的是免责声明 → 1 分",
    ),
    (
        "bench/negative/pre_deliver-rd-single-option.md",
        "first_principles",
        1,
        "召回方案只给一个选项没有对照。critic.md：只有一条路没有对照 → 最多 1 分",
    ),
    (
        "bench/negative/pre_task-rd-hedge.md",
        "first_principles",
        1,
        "假设写成「大概/应该」。critic.md：假设不可证伪 → 1 分",
    ),
    (
        "bench/negative/post_task-rd-empty.md",
        "co_growth",
        1,
        "复盘只有感受与打算，没有可加载资产。critic.md：只有感想没有可加载的东西 → 0 分",
    ),
    (
        "bench/negative/pre_deliver-rd-silent-downgrade.md",
        "silent_downgrade",
        None,
        "砍掉云端存储但没写取舍声明。critic.md：附加检查判 silent_downgrade = true",
    ),
]


def _applicable(path: str) -> list[str]:
    """按产出类型给出「应当被评」的维度。

    critic v2 里三条价值观不是每份产出都适用：拆解卡不要求沉淀，复盘不要求红队。
    期望值必须跟着类型走，否则测的就不是 critic 的准确性，而是「它有没有按错尺子打分」。
    """
    name = Path(path).name
    if name.startswith("pre_task"):
        return ["first_principles"]
    if name.startswith("pre_deliver"):
        return ["first_principles", "extremeness"]
    return ["co_growth", "first_principles"]


def main():
    if REVIEW.exists():
        shutil.rmtree(REVIEW)
    REVIEW.mkdir(parents=True)

    items = []
    for rel in POSITIVES:
        items.append(
            {
                "path": rel,
                "kind": "pos",
                "expect": {d: 2 for d in _applicable(rel)},
                "why": "适用维度都应 ≥2",
            }
        )
    for rel, dim, ceil, why in NEGATIVES:
        items.append({"path": rel, "kind": "neg", "expect": {dim: ceil}, "why": why})

    mapping = []
    for it in items:
        src = ROOT / it["path"]
        if not src.exists():
            print(f"缺文件：{it['path']}", file=sys.stderr)
            return 2
        hid = hashlib.sha1(it["path"].encode()).hexdigest()[:12]
        dest = REVIEW / f"{hid}.md"
        shutil.copyfile(src, dest)
        prompt = REVIEW / f"{hid}.prompt.md"
        with prompt.open("w", encoding="utf-8") as fh:
            subprocess.run(
                [sys.executable, str(ROOT / "vh.py"), "critique", str(dest)],
                stdout=fh,
                check=True,
            )
        mapping.append(
            {
                "id": hid,
                "path": it["path"],
                "kind": it["kind"],
                "expect": it["expect"],
                "why": it["why"],
                "prompt": str(prompt.relative_to(ROOT)),
                "score": str((REVIEW / f"{hid}.score.json").relative_to(ROOT)),
            }
        )

    (OUT / "map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(mapping)} 份校准语料 -> {REVIEW.relative_to(ROOT)}")
    for m in mapping:
        exp = m["expect"] or {"三条": "≥2"}
        print(f"  {m['id']}  [{m['kind']}] {m['path']:52s} 期望 {exp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
