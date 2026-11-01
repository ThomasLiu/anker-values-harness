@echo off
rem Windows 入口：.\vh stages / .\vh lint pre_task 产出.md
rem 逻辑全在 vh.py，这里只负责挑一个可用的 Python 解释器。
setlocal
set "VH_PY=python"
where py >nul 2>nul && set "VH_PY=py -3"
%VH_PY% "%~dp0vh.py" %*
exit /b %errorlevel%
