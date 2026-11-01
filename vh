#!/usr/bin/env python3
"""values-harness CLI 入口。零依赖，直接 ./vh 即可运行。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vhcore.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
