#!/usr/bin/env python3
"""POSIX 入口。真正的逻辑在 vh.py——Windows 上直接跑那个，不维护两份。"""

import os
import runpy
import sys

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vh.py")
sys.argv[0] = TARGET
runpy.run_path(TARGET, run_name="__main__")
