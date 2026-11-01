"""确定性检查器。

设计原则：能自动判的绝不交给模型判。每多一条确定性规则，harness 就少一分
「看起来在遵守」的可能。judge 只用于语言质量类判断，见 evaluator/。
"""

from __future__ import annotations

from .markdown import Artifact, items_of, snippet


class Result:
    __slots__ = ("ok", "detail", "skipped")

    def __init__(self, ok: bool, detail: str = "", skipped: bool = False):
        self.ok = ok
        self.detail = detail
        self.skipped = skipped

    def __repr__(self):
        return f"Result(ok={self.ok}, skipped={self.skipped}, detail={self.detail!r})"


def _contains_any(haystack: str, needles) -> bool:
    low = haystack.lower()
    return any(n.lower() in low for n in needles)


def check_require_section(art: Artifact, params: dict) -> Result:
    aliases = params.get("sections", [])
    min_items = int(params.get("min_items", 1))
    need = params.get("item_requires_any", [])

    sec = art.find_section(aliases)
    if sec is None:
        return Result(False, f"缺少段落 `## {aliases[0]}`（也接受：{' / '.join(aliases[1:]) or '无'}）")

    its = items_of(sec)
    if len(its) < min_items:
        return Result(False, f"段落「{sec['name']}」只有 {len(its)} 条，要求 ≥{min_items} 条")

    if need:
        bad = [i for i in its if not _contains_any(i, need)]
        if bad:
            return Result(
                False,
                f"「{sec['name']}」有 {len(bad)} 条缺少要件（需含 {' / '.join(need)}），"
                f"例如：{snippet(bad[0])}",
            )

    return Result(True, f"「{sec['name']}」{len(its)} 条，符合")


def check_forbid_pattern_without_reason(art: Artifact, params: dict) -> Result:
    patterns = params.get("patterns", [])
    markers = params.get("reason_markers", [])

    hits = []
    for lineno, line in enumerate(art.lines, 1):
        if not line.strip():
            continue
        for p in patterns:
            if p.lower() in line.lower():
                if markers and _contains_any(line, markers):
                    break  # 有理由，放行
                hits.append((lineno, p, line.strip()))
                break

    if hits:
        lineno, p, line = hits[0]
        more = f"，另有 {len(hits) - 1} 处" if len(hits) > 1 else ""
        return Result(False, f"第 {lineno} 行用「{p}」当理由{more}：{snippet(line, 50)}")
    return Result(True, "未发现以惯例代替推理")


def check_require_when_pattern(art: Artifact, params: dict) -> Result:
    trigger = params.get("trigger", [])
    req_sec = params.get("require_section", [])
    req_pat = params.get("require_pattern", [])

    if trigger and not art.has(trigger):
        return Result(True, "未触发", skipped=True)

    missing = []
    if req_sec and art.find_section(req_sec) is None:
        missing.append(f"段落 `## {req_sec[0]}`")
    if req_pat and not art.has(req_pat):
        missing.append(f"文字「{req_pat[0]}」")

    if missing:
        hit = next((t for t in trigger if t.lower() in art.text.lower()), trigger[0])
        return Result(False, f"出现「{hit}」但缺少 {' 与 '.join(missing)}")

    return Result(True, "已触发且满足要求")


def check_require_pattern(art: Artifact, params: dict) -> Result:
    pats = params.get("patterns", [])
    if not pats:
        return Result(True, "无要求", skipped=True)
    if art.has(pats):
        return Result(True, "已包含")
    return Result(False, f"缺少必需内容：{' / '.join(pats)}")


CHECKS = {
    "require_section": check_require_section,
    "forbid_pattern_without_reason": check_forbid_pattern_without_reason,
    "require_when_pattern": check_require_when_pattern,
    "require_pattern": check_require_pattern,
}


class Finding:
    __slots__ = ("rule", "value", "severity", "statement", "fix", "ok", "detail", "skipped")

    def __init__(self, rule: dict, result: Result):
        self.rule = rule["id"]
        self.value = rule.get("_value_name", "")
        self.severity = rule.get("severity", "warning")
        self.statement = rule.get("statement", "")
        self.fix = rule.get("fix", "")
        self.ok = result.ok
        self.detail = result.detail
        self.skipped = result.skipped

    @property
    def blocking_fail(self) -> bool:
        return (not self.ok) and self.severity == "blocking"

    def as_dict(self):
        return {
            "rule": self.rule,
            "value": self.value,
            "severity": self.severity,
            "ok": self.ok,
            "skipped": self.skipped,
            "detail": self.detail,
        }


def run(rules, art: Artifact) -> list[Finding]:
    out = []
    for r in rules:
        fn = CHECKS[r["check"]]
        try:
            res = fn(art, r.get("params", {}))
        except Exception as e:  # 检查器自身出错不能静默通过
            res = Result(False, f"检查器异常：{type(e).__name__}: {e}")
        out.append(Finding(r, res))
    return out
