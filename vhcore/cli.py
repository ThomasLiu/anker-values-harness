"""vh 命令行。"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from . import checks as checksmod
from . import config as cfgmod
from . import telemetry as tel
from .markdown import Artifact
from .render import render_prompt


def _load(args):
    root = Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None
    return cfgmod.load(root)


def _print_findings(stage: str, path: str, findings):
    blocking = [f for f in findings if f.blocking_fail]
    warns = [f for f in findings if not f.ok and not f.skipped and f.severity != "blocking"]
    print(f"\n{stage}  {path}")
    print("-" * 60)
    for f in findings:
        if f.skipped:
            continue
        if f.ok:
            print(f"  ok    {f.rule}  {f.detail}")
        else:
            tag = "blocking" if f.severity == "blocking" else "warning"
            print(f"  FAIL  [{tag}] {f.rule}")
            print(f"        {f.detail}")
            if f.fix:
                print(f"        fix: {f.fix}")
    print("-" * 60)
    print(f"结果：{len(blocking)} blocking 失败，{len(warns)} warning")
    return blocking


def cmd_stages(args):
    cfg = _load(args)
    print(f"{cfg.name}  (v{cfg.version})")
    print(f"仲裁优先级：{' > '.join(cfg.precedence)}\n")
    for sid, st in cfg.stages.items():
        rules = cfg.rules(sid)
        nb = sum(1 for r in rules if r.get("severity") == "blocking")
        print(f"{sid:12s} {st['title']:6s} {len(rules):2d} 条规则（{nb} blocking）  {st.get('goal','')}")
    return 0


def cmd_prompt(args):
    cfg = _load(args)
    text = render_prompt(cfg, args.stage, task=args.task, brief=args.brief)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}（{len(text.splitlines())} 行）", file=sys.stderr)
    else:
        print(text)
    return 0


def _run_lint(cfg, stage, path, log=True, task=None):
    art = Artifact(Path(path).read_text(encoding="utf-8"), str(path))
    findings = checksmod.run(cfg.rules(stage), art)
    if log:
        tel.record(cfg.root, stage, str(path), findings, task=task)
    return findings


def cmd_lint(args):
    cfg = _load(args)
    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2
    findings = _run_lint(cfg, args.stage, path, log=not args.no_log, task=args.task)
    blocking = _print_findings(args.stage, str(path), findings)

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], ensure_ascii=False, indent=2))

    return 1 if blocking else 0


def cmd_lint_all(args):
    cfg = _load(args)
    path = Path(args.file)
    worst = 0
    for sid in cfg.stages:
        findings = _run_lint(cfg, sid, path, log=not args.no_log)
        if _print_findings(sid, str(path), findings):
            worst = 1
    return worst


def cmd_report(args):
    cfg = _load(args)
    rep = tel.report(cfg.root)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    print(f"总 lint 次数：{rep['runs']}")
    if not rep["runs"]:
        print("（还没有数据。跑一次 `vh lint` 就会开始记录。）")
        return 0
    print("\n各阶段通过率：")
    for sid, st in rep["by_stage"].items():
        print(f"  {sid:12s} {st['passed']}/{st['runs']}  {st['pass_rate']*100:5.1f}%")
    print("\n最常被拦的规则：")
    for row in rep["rule_fails"][:8]:
        print(f"  {row['fails']:3d} 次  {row['rule']}")
    if rep["recent_failures"]:
        print("\n最近失败：")
        for r in rep["recent_failures"]:
            print(f"  {r['ts']}  {r['stage']:12s} {r['artifact']}  -> {', '.join(r['blocking'])}")
    return 0


def cmd_critique(args):
    cfg = _load(args)
    from .render import render_critic, render_rubric

    if not Path(args.file).exists():
        print(f"文件不存在：{args.file}", file=sys.stderr)
        return 2
    body = Path(args.file).read_text(encoding="utf-8")
    print(render_critic(cfg, cfg.root))
    print("\n---\n")
    print("# 待评产出\n")
    print(body)
    if args.value:
        rb = render_rubric(cfg.root, args.value)
        if rb:
            print("\n---\n")
            print(rb)
    return 0


def cmd_selftest(args):
    cfg = _load(args)
    cases_path = cfg.root / "bench" / "cases.toml"
    if not cases_path.exists():
        print(f"缺少 {cases_path}", file=sys.stderr)
        return 2
    with cases_path.open("rb") as fh:
        data = tomllib.load(fh)
    cases = data.get("case", [])

    ok = 0
    failures = []
    for c in cases:
        path = cfg.root / c["file"]
        if not path.exists():
            failures.append((c["name"], "文件不存在"))
            print(f"  MISS  {c['name']}  {path}")
            continue
        findings = _run_lint(cfg, c["stage"], path, log=False)
        failed_rules = {f.rule for f in findings if not f.ok and not f.skipped}
        blocking = {f.rule for f in findings if f.blocking_fail}

        if c["expect"] == "pass":
            if blocking:
                failures.append((c["name"], f"预期通过但被拦：{', '.join(sorted(blocking))}"))
                print(f"  FAIL  {c['name']}  预期通过，实际被拦 {sorted(blocking)}")
            else:
                ok += 1
                print(f"  ok    {c['name']}  通过")
        else:
            want = set(c.get("expect_rules", []))
            missing = want - failed_rules
            if missing:
                failures.append((c["name"], f"预期 {sorted(missing)} 报错但未报"))
                print(f"  FAIL  {c['name']}  预期拦 {sorted(missing)}，实际拦 {sorted(failed_rules)}")
            else:
                ok += 1
                print(f"  ok    {c['name']}  正确拦下 {sorted(want)}")

    print(f"\nselftest：{ok}/{len(cases)} 通过")
    if failures:
        print("\n失败明细：")
        for name, why in failures:
            print(f"  - {name}: {why}")
        return 1
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="vh",
        description="把价值观编译成 agent 可执行的 gate / rubric / telemetry",
    )
    p.add_argument("--root", help="harness 根目录（默认向上查找 values.toml）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stages", help="列出阶段与规则数量")
    s.set_defaults(func=cmd_stages)

    s = sub.add_parser("prompt", help="渲染某阶段的 gate prompt")
    s.add_argument("stage")
    s.add_argument("--task", help="把任务描述嵌进 prompt")
    s.add_argument("--brief", action="store_true", help="只注入 blocking 规则（轻任务用）")
    s.add_argument("--out", help="写入文件而不是打印")
    s.set_defaults(func=cmd_prompt)

    s = sub.add_parser("lint", help="对产出跑某阶段的确定性检查")
    s.add_argument("stage")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-log", action="store_true")
    s.add_argument("--task", help="记录到遥测的任务描述")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("lint-all", help="对产出跑全部阶段检查")
    s.add_argument("file")
    s.add_argument("--no-log", action="store_true")
    s.set_defaults(func=cmd_lint_all)

    s = sub.add_parser("report", help="看价值观漂移指标")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("critique", help="渲染独立 critic 的评审 prompt")
    s.add_argument("file")
    s.add_argument("--value", help="附加某个价值观的 rubric")
    s.set_defaults(func=cmd_critique)

    s = sub.add_parser("selftest", help="跑基准样本，验证检查器本身有效")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except cfgmod.ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
