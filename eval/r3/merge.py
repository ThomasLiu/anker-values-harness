"""把仓库外跑出来的产出与遥测回收进仓库。

做三件事：
  1. 把 lab 里的三份 .md 复制到 eval/r3/runs/<scenario>/<COND>/
  2. 把每个 run 自己 .vh/telemetry.jsonl 里的记录改写 artifact 路径后合并
  3. 给每条记录补 scenario / condition 两个字段，否则没法按条件组切分

为什么不直接让 agent 往仓库里写：第一版就是这么做的，结果 BASE 组的产出里
出现了「红队自查 / 影响范围 / 取舍声明 / 技术债」——裸跑 agent 不会自发写出
harness 的必答段名，它去翻了仓库。实验目录必须在仓库外。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "r3"
RUNS = OUT / "runs"
LAB = Path("/Users/thomas/Projects/vh-r3-lab")
TEL = ROOT / ".vh" / "telemetry.jsonl"

STAGES = ["pre_task", "pre_deliver", "post_task"]


def main():
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if TEL.exists():
        TEL.unlink()

    merged: list[dict] = []
    copied = 0
    for m in manifest:
        sid, cond = m["scenario"], m["condition"]
        lab_dir = Path(m["lab_dir"])
        repo_dir = ROOT / m["repo_dir"]
        repo_dir.mkdir(parents=True, exist_ok=True)

        for st in STAGES:
            src = lab_dir / f"{st}.md"
            if not src.exists():
                print(f"  MISS {sid}/{cond}/{st}.md", file=sys.stderr)
                continue
            shutil.copyfile(src, repo_dir / f"{st}.md")
            copied += 1

        recs = []
        tel_file = lab_dir / ".vh" / "telemetry.jsonl"
        if tel_file.exists():
            for line in tel_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        for r in recs:
            name = Path(str(r.get("artifact", ""))).name
            r["artifact"] = str((repo_dir / name).relative_to(ROOT))
            r["scenario"] = sid
            r["condition"] = cond
            merged.append(r)
        print(f"  {sid}/{cond:5s}  docs={len([s for s in STAGES if (lab_dir/f'{s}.md').exists()])}  lint={len(recs)}")

    TEL.parent.mkdir(parents=True, exist_ok=True)
    TEL.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged),
        encoding="utf-8",
    )
    print(f"\n已回收 {copied} 份产出 -> {RUNS.relative_to(ROOT)}")
    print(f"已合并 {len(merged)} 条 lint 记录 -> {TEL.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
