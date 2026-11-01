#!/usr/bin/env python3
"""PostToolUse hook：agent 写完一份产出后，按它声明的阶段自动跑 lint。

默认**不启用**。要启用就把 `.claude/settings.example.json` 的内容合并进
`.claude/settings.json`。原因见 README：每次写入都触发，轻任务上纯属噪音。

阶段从产出里的标记读，不猜：
    <!-- vh:stage=pre_deliver -->

没有标记就跳过。**不要用 lint-all 代替**——一份 pre_task 拆解卡永远过不了
pre_deliver 的规则，那样每次写入都会误报，hook 两天内就会被关掉。

退出码 2 = 把 lint 结果回灌给 agent。PostToolUse 拦不住已经发生的写入，
只能让 agent 看见「你刚写的这份东西没通过」，然后自己去返工。
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE_RE = re.compile(r"<!--\s*vh:stage=([a-z_]+)\s*-->")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    target = (payload.get("tool_input") or {}).get("file_path") or ""
    # 只查 markdown：代码文件本来就不在这个 harness 的判定范围内
    if not target.endswith(".md"):
        return 0
    path = Path(target)
    if not path.is_file():
        return 0

    head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    m = STAGE_RE.search(head)
    if not m:
        return 0
    stage = m.group(1)

    proc = subprocess.run(
        [sys.executable, str(ROOT / "vh.py"), "lint", stage, str(path), "--no-log"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode == 0:
        return 0

    sys.stderr.write(
        f"[vh] {path.name} 没通过 {stage} 阶段的 lint，返工后再交付：\n{proc.stdout[-2000:]}\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
