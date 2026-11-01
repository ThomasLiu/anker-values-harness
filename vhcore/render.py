"""把 values.toml 渲染成阶段 prompt。

这是「注入层」。刻意保持短——价值观段落越长，注意力稀释越严重。
只注入当前阶段适用的规则，其余留在文件里按需加载。
"""

from __future__ import annotations

import textwrap

from .config import Config

VALUE_ORDER = ["first-principles", "extremeness", "co-growth"]


def _value_block(cfg: Config) -> str:
    lines = []
    for v in cfg.values:
        if v["id"] == "arbitration":
            continue
        lines.append(f"- **{v['name']}** — {v.get('motto', '')}")
    return "\n".join(lines)


def _rule_block(rules, brief: bool) -> str:
    parts = []
    for i, r in enumerate(rules, 1):
        tag = "blocking" if r.get("severity") == "blocking" else "warning"
        parts.append(f"### {i}. `{r['id']}`  [{tag}]")
        parts.append(f"要求：{r.get('statement', '')}")
        if not brief:
            parts.append(f"为什么：{r.get('why', '')}")
        parts.append(f"怎么改：{r.get('fix', '')}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _skeleton(rules) -> str:
    blocks = []
    for r in rules:
        if r.get("check") != "require_section":
            continue
        p = r.get("params", {})
        secs = p.get("sections", [])
        if not secs:
            continue
        hint = ""
        if p.get("item_requires_any"):
            hint = f"（每条需含 {' / '.join(p['item_requires_any'])}）"
        blocks.append(f"## {secs[0]}\n- …{hint}")
    if not blocks:
        return ""
    return "\n\n".join(blocks)


def render_prompt(
    cfg: Config,
    stage_id: str,
    task: str | None = None,
    brief: bool = False,
) -> str:
    stage = cfg.stage(stage_id)
    rules = cfg.rules(stage_id)
    if brief:
        rules = [r for r in rules if r.get("severity") == "blocking"]

    n_block = sum(1 for r in rules if r.get("severity") == "blocking")
    n_warn = len(rules) - n_block

    out = []
    out.append(f"# 阶段：{stage['title']}（`{stage_id}`）")
    out.append("")
    out.append(f"**本阶段目标**：{stage.get('goal', '')}")
    out.append(f"**本阶段产出**：{stage.get('artifact', '')}")
    if task:
        out.append("")
        out.append("## 当前任务")
        out.append(textwrap.dedent(task).strip())

    out.append("")
    out.append("## 你必须遵守的价值观")
    out.append("")
    out.append(_value_block(cfg))
    out.append("")
    out.append(
        "这些不是氛围词。下面每一条都是会被机器检查的硬性要求，"
        "不满足会被 lint 打回重做。"
    )

    out.append("")
    out.append(f"## 硬性要求（{n_block} 条 blocking，{n_warn} 条 warning）")
    out.append("")
    out.append(_rule_block(rules, brief))

    sk = _skeleton(rules)
    if sk:
        out.append("")
        out.append("## 产出骨架")
        out.append("")
        out.append("直接按这个结构写。缺段会被拦下：")
        out.append("")
        out.append("```markdown")
        out.append(sk)
        out.append("```")

    out.append("")
    out.append("## 冲突仲裁")
    out.append("")
    out.append("三条价值观一定打架。优先级（靠前者优先）：")
    out.append("")
    out.append("```")
    out.append(" > ".join(cfg.precedence))
    out.append("```")
    out.append("")
    out.append("**唯一硬规则：不允许静默降级。** 任何降级、简化、跳过，必须显式写一行：")
    out.append("")
    out.append("```")
    out.append("取舍声明：为了 X 放弃了 Y，因为 Z")
    out.append("```")

    out.append("")
    out.append("## 交付前自检")
    out.append("")
    out.append("```bash")
    out.append(f"vh lint {stage_id} <产出文件>")
    out.append("```")
    out.append("")
    out.append("exit code 0 才算通过。非 0 表示被拦下——按提示补内容后重跑，不要绕过。")

    return "\n".join(out) + "\n"


def render_critic(cfg: Config, root) -> str:
    path = root / "evaluator" / "critic.md"
    if not path.exists():
        return "（缺少 evaluator/critic.md）"
    return path.read_text(encoding="utf-8")


def render_rubric(root, value_id: str) -> str:
    path = root / "rubrics" / f"{value_id}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
