#!/usr/bin/env python3
"""values-harness CLI 入口。

三种调用方式等价，随便挑一个能用的：

    python vh.py stages       全平台（推荐，Windows 上就用这个）
    ./vh stages               POSIX（macOS / Linux，有执行位）
    .\\vh stages               Windows cmd / PowerShell（走 vh.cmd）

零依赖，但需要 Python 3.11+——TOML 解析用的是标准库 tomllib，3.11 才进标准库。
"""

import os
import sys

if sys.version_info < (3, 11):
    sys.exit(
        "需要 Python 3.11+，当前是 %d.%d。\n"
        "原因是 TOML 解析依赖标准库 tomllib（3.11 起才有）。"
        % (sys.version_info.major, sys.version_info.minor)
    )

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vhcore.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
