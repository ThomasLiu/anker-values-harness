#!/usr/bin/env python3
"""PostToolUse hook：agent 写完一个 markdown 文件后，自动跑一遍价值观 lint。

默认**不启用**。要启用就把 `.claude/settings.example.json` 的内容合并进
`.claude/settings.json`。原因见 README：每次写入都触发，轻任务上纯属噪音。

退出码 2 = 把 lint 结果回灌给 agent。PostToolUse 拦不住已经发生的写入，
只能让 agent 看见「你刚写的这份东西没通过」，然后自己去返工。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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

    proc = subprocess.run(
        [sys.executable, str(ROOT / "vh.py"), "lint-all", str(path), "--no-log"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode == 0:
        return 0

    sys.stderr.write(f"[vh] {path.name} 没通过价值观 lint，返工后再交付：\n{proc.stdout[-2000:]}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
