"""B2 第一轮新实验的脚手架。

产出结构（**实验在仓库外跑**，跑完再回收进仓库）：

    /Users/thomas/Projects/vh-r3-lab/<scenario>/<COND>/TASK.md
    /Users/thomas/Projects/vh-r3-lab/<scenario>/<COND>/prompt_*.md    （OPEN / BLIND）
    /Users/thomas/Projects/vh-r3-lab/<scenario>/<COND>/vh             （遥测隔离包装器）
    /Users/thomas/Projects/vh-r3-lab/<scenario>/<COND>/{pre_task,pre_deliver,post_task}.md
    /Users/thomas/Projects/vh-r3-lab/<scenario>/<COND>/.vh/telemetry.jsonl

为什么实验目录在仓库外：子 agent 的工作目录被钉在仓库根，第一版把 run 目录放在
`eval/r3/runs/` 下，BASE 组的产出里直接出现了「红队自查 / 影响范围 / 取舍声明 /
技术债」——这是 harness 的必答段名，裸跑 agent 不会自发写出来。它去翻了仓库。
实验目录搬出仓库 + 明令禁止访问仓库之后，才谈得上「裸跑」。

为什么要按 run 隔离遥测：`_next_trial()` 靠重读 jsonl 数同一个产出的第几次 lint。
12 个 agent 并发写同一个文件会让 trial 号互相覆盖，返工统计整体失真，而且这个
错误写进归档后无法反推。每个 run 一个 VH_HOME，合并时按 run 内顺序拼接。
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "r3"
LAB = Path("/Users/thomas/Projects/vh-r3-lab")

# 4 个场景，研发 / 非研发各 2。选它们的理由：
#   rd-recall        对外动作 + 不可逆（全球公告、监管备案）→ blast-radius 必须触发
#   rd-thermal       出货放行决策，成本与合规对冲
#   nonrd-pricing    备货不可逆，数字密集 → number-provenance 必须触发
#   nonrd-cell-source 供应链切换，现金流与保供对冲
SCENARIOS = ["rd-recall", "rd-thermal", "nonrd-pricing", "nonrd-cell-source"]

CONDITIONS = ["BASE", "OPEN", "BLIND"]

STAGES = ["pre_task", "pre_deliver", "post_task"]

WRAPPER = """#!/bin/sh
# 本 run 专用的 vh 包装器：把遥测钉在本目录的 .vh/，避免多个 agent 并发写同一个文件。
d=$(cd "$(dirname "$0")" && pwd)
VH_HOME="$d/.vh" exec {python} {vh} "$@"
"""


def load_scenarios() -> dict[str, dict]:
    with (ROOT / "scenarios" / "scenarios.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return {s["id"]: s for s in data["scenario"]}


def make_wrapper(path: Path):
    path.write_text(
        WRAPPER.format(python=sys.executable, vh=ROOT / "vh.py"),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_prompt(stage: str, task: str) -> str:
    """直接调用 harness 自己的渲染器，不另写一份 prompt。

    这样 BLIND 组看到的约束与真实部署时 agent 看到的完全一致；
    另写一份就会变成「实验专用 prompt」，测出来的东西不可迁移。
    """
    sys.path.insert(0, str(ROOT))
    from vhcore.config import load
    from vhcore.render import render_prompt

    cfg = load(ROOT)
    return render_prompt(cfg, stage, task=task)


def main():
    scenarios = load_scenarios()
    missing = [s for s in SCENARIOS if s not in scenarios]
    if missing:
        print(f"scenarios.toml 里没有这些场景：{missing}", file=sys.stderr)
        return 2

    manifest = []
    for sid in SCENARIOS:
        sc = scenarios[sid]
        task = sc["task"].strip()
        for cond in CONDITIONS:
            d = LAB / sid / cond
            d.mkdir(parents=True, exist_ok=True)
            (d / "TASK.md").write_text(
                f"# {sc['title']}\n\n"
                f"**领域**：{sc['domain']}　**岗位**：{sc['role']}\n\n"
                f"{task}\n",
                encoding="utf-8",
            )
            make_wrapper(d / "vh")
            if cond != "BASE":
                for st in STAGES:
                    (d / f"prompt_{st}.md").write_text(
                        build_prompt(st, task), encoding="utf-8"
                    )
            manifest.append(
                {
                    "run": f"{sid}/{cond}",
                    "scenario": sid,
                    "condition": cond,
                    "title": sc["title"],
                    "role": sc["role"],
                    "lab_dir": str(d),
                    "repo_dir": str((OUT / "runs" / sid / cond).relative_to(ROOT)),
                }
            )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已建 {len(manifest)} 个 run -> {LAB}")
    for m in manifest:
        print(f"  {m['run']:28s} {m['title']}")
    return 0


if __name__ == "__main__":
    os.umask(0o022)
    sys.exit(main())
