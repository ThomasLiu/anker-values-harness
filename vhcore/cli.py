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


class InputError(RuntimeError):
    """输入文件本身有问题（编码、路径），不是配置错。"""


def _force_utf8_stdio():
    """把 stdout/stderr 钉死成 UTF-8。

    Windows 上 stdout 被重定向（管道、CI、agent 抓输出）时用的是本地代码页，
    英文环境的 cp437/ascii 编码不出中文，print 会直接抛 UnicodeEncodeError
    把整个命令干掉。控制台场景本来就是 UTF-8，重设无害。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _read_text(path: Path) -> str:
    """读产出文件，容忍 BOM 与 GBK。

    中文 Windows 的编辑器默认存 GB18030 是常态，硬解 UTF-8 会让 lint
    吐一坨栈。降级顺序：UTF-8(含 BOM) → GB18030 → 报错说人话。
    """
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("gb18030")
    except UnicodeDecodeError as e:
        raise InputError(
            f"无法解码 {path}（既不是 UTF-8 也不是 GBK）：{e.reason}。"
            "请把文件另存为 UTF-8。"
        ) from e
    print(f"提示：{path} 是 GBK 编码，已按 GB18030 读取；建议另存为 UTF-8。", file=sys.stderr)
    return text


def _load(args):
    root = Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None
    return cfgmod.load(root)


def _print_findings(stage: str, path: str, findings, out=None):
    out = out or sys.stdout
    blocking = [f for f in findings if f.blocking_fail]
    warns = [f for f in findings if not f.ok and not f.skipped and f.severity != "blocking"]
    print(f"\n{stage}  {path}", file=out)
    print("-" * 60, file=out)
    for f in findings:
        if f.skipped:
            continue
        if f.ok:
            print(f"  ok    {f.rule}  {f.detail}", file=out)
        else:
            tag = "blocking" if f.severity == "blocking" else "warning"
            print(f"  FAIL  [{tag}] {f.rule}", file=out)
            print(f"        {f.detail}", file=out)
            if f.fix:
                print(f"        fix: {f.fix}", file=out)
    print("-" * 60, file=out)
    print(f"结果：{len(blocking)} blocking 失败，{len(warns)} warning", file=out)
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
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"已写入 {args.out}（{len(text.splitlines())} 行）", file=sys.stderr)
    else:
        print(text)
    return 0


def _run_lint(cfg, stage, path, log=True, task=None):
    art = Artifact(_read_text(Path(path)), str(path))
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
    if path.is_dir():
        print(f"这是一个目录，不是产出文件：{path}", file=sys.stderr)
        return 2
    findings = _run_lint(cfg, args.stage, path, log=not args.no_log, task=args.task)
    # --json 是给机器读的，人读的报告必须让路到 stderr，否则 stdout 不是合法 JSON
    blocking = _print_findings(
        args.stage, str(path), findings, out=sys.stderr if args.json else None
    )

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], ensure_ascii=False, indent=2))

    return 1 if blocking else 0


def cmd_lint_all(args):
    cfg = _load(args)
    path = Path(args.file)
    if not path.is_file():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 2
    worst = 0
    for sid in cfg.stages:
        findings = _run_lint(cfg, sid, path, log=not args.no_log)
        if _print_findings(sid, str(path), findings):
            worst = 1
    return worst


VALUE_LABELS = (
    ("first_principles", "第一性"),
    ("extremeness", "求极致"),
    ("co_growth", "共成长"),
)


def _print_critic(rep):
    c = rep["critic"]
    if not c["runs"]:
        print("\ncritic 评分：暂无。跑完评审后用 `vh critique <file> --record <score.json>` 回收。")
        return
    print(f"\ncritic 评分（{c['runs']} 份）：")
    for key, label in VALUE_LABELS:
        v = c["means"].get(key)
        print(f"  {label:6s} {v if v is not None else '—'} / 3")
    rate = c["silent_downgrade_rate"]
    if rate is not None:
        print(f"  静默降级 {rate * 100:.0f}%")
    for v, n in c["verdicts"].items():
        print(f"  {v}：{n} 份")


def cmd_report(args):
    cfg = _load(args)
    if args.export:
        n = tel.export(cfg.root, Path(args.export), include_all=args.all)
        print(f"已导出 {n} 条记录 -> {args.export}")
        return 0

    src = Path(args.source).expanduser() if args.source else None
    rep = tel.report(cfg.root, source=src, rules=cfg.rules())
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    if src:
        print(f"数据源：{src}")
    print(f"总 lint 次数：{rep['runs']}")
    if rep["runs"]:
        print("\n各阶段通过率：")
        for sid, st in rep["by_stage"].items():
            fa = rep["by_artifact"].get(sid, {})
            print(
                f"  {sid:12s} "
                f"首次 {fa.get('first_passed', 0):2d}/{fa.get('first_runs', 0):2d} "
                f"{fa.get('first_pass_rate', 0) * 100:5.1f}%   "
                f"最终 {fa.get('passed', 0):2d}/{fa.get('artifacts', 0):2d} "
                f"{fa.get('final_pass_rate', 0) * 100:5.1f}%   "
                f"返工 {fa.get('rework', 0)} 份"
            )
        print("\n最常被拦的规则：")
        for row in rep["rule_fails"][:8]:
            print(f"  {row['fails']:3d} 次  {row['rule']}")

        health = rep.get("rule_health") or []
        if health:
            print("\n规则健康（触发 = 被真正评估过，跳过 = 触发条件没命中）：")
            print("  规则                         级别      触发  失败  跳过   失败率")
            for h in health:
                if not h["runs"]:
                    rate = "从未触发"
                else:
                    rate = f"{h['fail_rate'] * 100:.0f}%"
                print(
                    f"  {h['rule']:<28s} {h['severity']:<8s} {h['runs']:>4d} "
                    f"{h['fails']:>5d} {h['skipped']:>5d}   {rate}"
                )
        if rep["recent_failures"]:
            print("\n最近失败：")
            for r in rep["recent_failures"]:
                print(
                    f"  {r['ts']}  {r['stage']:12s} {r['artifact']}  "
                    f"-> {', '.join(r['blocking'])}"
                )
    else:
        print("（还没有数据。跑一次 `vh lint` 就会开始记录。）")

    _print_critic(rep)
    return 0


def cmd_critique(args):
    cfg = _load(args)
    from .render import render_critic, render_rubric

    if not Path(args.file).exists():
        print(f"文件不存在：{args.file}", file=sys.stderr)
        return 2

    # 回收模式：critic 已经在独立上下文里跑完了，这里只把结果写进遥测
    if args.record:
        try:
            score = json.loads(_read_text(Path(args.record)))
        except json.JSONDecodeError as e:
            print(f"评分文件不是合法 JSON：{e}", file=sys.stderr)
            return 2
        rec = tel.record_critic(cfg.root, args.file, score)
        print(
            f"已记录 {args.file}\n"
            f"  第一性 {rec.get('first_principles')} / 求极致 {rec.get('extremeness')} "
            f"/ 共成长 {rec.get('co_growth')}  静默降级={rec.get('silent_downgrade')}"
        )
        return 0

    body = _read_text(Path(args.file))
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


def cmd_promote(args):
    """把一次真实逃逸沉淀成回归用例。

    只接受「确实被这条规则拦下」的产出。拦不住的产出进 bench 只会制造
    假安全感——selftest 全绿，但什么都没验证。
    """
    cfg = _load(args)
    src = Path(args.file)
    if not src.exists():
        print(f"文件不存在：{src}", file=sys.stderr)
        return 2

    rule = cfg.rule(args.rule)
    stage = args.stage or rule["stage"][0]

    findings = _run_lint(cfg, stage, src, log=False)
    mine = [f for f in findings if f.rule == rule["id"]]
    if not mine:
        print(f"拒绝：{rule['id']} 不在 {stage} 阶段。", file=sys.stderr)
        return 2
    if mine[0].ok or mine[0].skipped:
        state = "跳过（触发条件没命中）" if mine[0].skipped else "通过"
        print(
            f"拒绝沉淀：{rule['id']} 在 {stage} 阶段对 {src} 是「{state}」，没拦住。\n"
            f"拦不住的产出进 bench 只会制造假安全感。",
            file=sys.stderr,
        )
        return 1

    dest_dir = cfg.root / "bench" / "negative"
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = f"{stage}-{rule['id'].replace('.', '-')}"
    dest = dest_dir / f"{base}.md"
    n = 2
    while dest.exists():
        dest = dest_dir / f"{base}-{n}.md"
        n += 1
    dest.write_text(_read_text(src), encoding="utf-8", newline="\n")

    cases = cfg.root / "bench" / "cases.toml"
    before = cases.read_text(encoding="utf-8")
    with cases.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n# 由 vh promote 沉淀，来源：{src.name}\n"
            f"[[case]]\n"
            f'name = "neg/{dest.stem}"\n'
            f'stage = "{stage}"\n'
            f'file = "bench/negative/{dest.name}"\n'
            f'expect = "fail"\n'
            f'expect_rules = ["{rule["id"]}"]\n'
        )
    print(f"已沉淀 -> bench/negative/{dest.name}")

    rc = cmd_selftest(args)
    if rc != 0:
        cases.write_text(before, encoding="utf-8")
        dest.unlink()
        print("新用例没通过 selftest，已回滚。", file=sys.stderr)
    return rc


def main(argv=None):
    _force_utf8_stdio()
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
    s.add_argument("--from", dest="source", help="从归档文件读取，如 eval/telemetry/r2.jsonl")
    s.add_argument("--export", help="把当前 telemetry 归档到指定路径")
    s.add_argument("--all", action="store_true", help="归档时保留临时目录的记录（默认剔除）")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("critique", help="渲染独立 critic 的评审 prompt，或回收评分")
    s.add_argument("file")
    s.add_argument("--value", help="附加某个价值观的 rubric")
    s.add_argument("--record", help="critic 返回的评分 JSON 文件，写入遥测后返回")
    s.set_defaults(func=cmd_critique)

    s = sub.add_parser("selftest", help="跑基准样本，验证检查器本身有效")
    s.set_defaults(func=cmd_selftest)

    s = sub.add_parser("promote", help="把一次真实逃逸沉淀为回归用例")
    s.add_argument("file")
    s.add_argument("rule", help="应该拦住它的规则 id，如 ex.redteam")
    s.add_argument("--stage", help="默认取规则声明的第一个阶段")
    s.set_defaults(func=cmd_promote)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except cfgmod.ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2
    except InputError as e:
        print(f"输入错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
