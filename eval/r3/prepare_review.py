"""准备盲评语料。

critic 必须看不到产出的路径——路径里带着 `<scenario>/<COND>/`，等于直接告诉它
哪份是裸跑、哪份是带 harness。所以每份产出复制成一个哈希名文件，prompt 也渲染
到同一目录，评审 agent 只看得到内容和规范，看不到来源。

映射表存在 map.json，回收评分时用它把哈希名换回真实路径。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "r3"
RUNS = OUT / "runs"
REVIEW = OUT / "review"

STAGES = ["pre_task", "pre_deliver", "post_task"]


def main():
    if REVIEW.exists():
        shutil.rmtree(REVIEW)
    REVIEW.mkdir(parents=True)

    mapping = []
    for md in sorted(RUNS.glob("*/*/*.md")):
        sid, cond, stage = md.parts[-3], md.parts[-2], md.stem
        if stage not in STAGES:
            continue
        key = f"{sid}/{cond}/{stage}"
        hid = hashlib.sha1(key.encode()).hexdigest()[:12]
        dest = REVIEW / f"{hid}.md"
        shutil.copyfile(md, dest)
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
                "run": key,
                "scenario": sid,
                "condition": cond,
                "stage": stage,
                "artifact": str(md.relative_to(ROOT)),
                "prompt": str(prompt.relative_to(ROOT)),
                "score": str((REVIEW / f"{hid}.score.json").relative_to(ROOT)),
            }
        )

    (OUT / "map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 {len(mapping)} 份盲评语料 -> {REVIEW.relative_to(ROOT)}")
    for m in mapping:
        print(f"  {m['id']}  {m['run']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
