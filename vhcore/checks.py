"""确定性检查器。

设计原则：能自动判的绝不交给模型判。每多一条确定性规则，harness 就少一分
「看起来在遵守」的可能。judge 只用于语言质量类判断，见 evaluator/。

已知边界（实测得出，不要试图消灭）：
  检查器只判结构，不判质量。一个足够刻意的 agent 能写出形式上合规、
  实质空洞的产出。这套东西防的是无意识的偷懒，不是防恶意。
"""

from __future__ import annotations

import re

from .markdown import Artifact, items_of, snippet

DIGIT = re.compile(r"\d")


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


def _trigger_hit(text: str, triggers, negations=None, window: int = 4) -> str | None:
    """找一个「没被否定的」触发词。

    关键词触发的头号失效方式是词面撞车：`不外发`、`尚未发送`、`无需部署`
    都不是动作。所以命中后要回看前几个字符，命中否定词就跳过这次出现。
    """
    low = text.lower()
    for t in triggers:
        tl = t.lower()
        start = 0
        while True:
            i = low.find(tl, start)
            if i < 0:
                break
            if negations:
                prefix = low[max(0, i - window) : i]
                if any(n in prefix for n in negations):
                    start = i + len(tl)
                    continue
            return t
    return None


def _count_hits(text: str, triggers, negations=None, window: int = 4) -> int:
    low = text.lower()
    n = 0
    for t in triggers:
        tl = t.lower()
        start = 0
        while True:
            i = low.find(tl, start)
            if i < 0:
                break
            if negations:
                prefix = low[max(0, i - window) : i]
                if any(x in prefix for x in negations):
                    start = i + len(tl)
                    continue
            n += 1
            start = i + len(tl)
    return n


def check_require_section(art: Artifact, params: dict) -> Result:
    aliases = params.get("sections", [])
    min_items = int(params.get("min_items", 1))
    need = params.get("item_requires_any", [])
    accept_digit = params.get("accept_digit", True)

    sec = art.find_section(aliases)
    if sec is None:
        return Result(False, f"缺少段落 `## {aliases[0]}`（也接受：{' / '.join(aliases[1:]) or '无'}）")

    its = items_of(sec)
    if len(its) < min_items:
        return Result(False, f"段落「{sec['name']}」只有 {len(its)} 条，要求 ≥{min_items} 条")

    if need:
        bad = []
        for i in its:
            if _contains_any(i, need):
                continue
            # 带数字的条目视为可判定——「位次 1–8 唯一」不该因为没写「至少」被判死
            if accept_digit and DIGIT.search(i):
                continue
            bad.append(i)
        if bad:
            return Result(
                False,
                f"「{sec['name']}」有 {len(bad)} 条缺少要件（需含 {' / '.join(need)}，或含数字），"
                f"例如：{snippet(bad[0])}",
            )

    return Result(True, f"「{sec['name']}」{len(its)} 条，符合")


def check_forbid_pattern_without_reason(art: Artifact, params: dict) -> Result:
    patterns = params.get("patterns", [])
    markers = params.get("reason_markers", [])
    decision = params.get("decision_markers", [])

    hits = []
    for lineno, line in enumerate(art.lines, 1):
        if not line.strip():
            continue
        for p in patterns:
            if p.lower() not in line.lower():
                continue
            if markers and _contains_any(line, markers):
                break  # 有理由，放行
            # 只有「用惯例支撑决策」才算违规；纯描述性引用放行
            if decision and not _contains_any(line, decision):
                break
            hits.append((lineno, p, line.strip()))
            break

    if hits:
        lineno, p, line = hits[0]
        more = f"，另有 {len(hits) - 1} 处" if len(hits) > 1 else ""
        return Result(False, f"第 {lineno} 行用「{p}」当理由{more}：{snippet(line, 50)}")
    return Result(True, "未发现以惯例代替推理")


def check_forbid_pattern_in_section(art: Artifact, params: dict) -> Result:
    """在指定段落内禁止某些词。

    用来查「假设不可证伪」这类问题——「客户可能对价格敏感」不是假设，
    是还没想清楚。
    """
    aliases = params.get("sections", [])
    patterns = params.get("patterns", [])
    sec = art.find_section(aliases)
    if sec is None:
        return Result(True, "段落不存在，跳过", skipped=True)
    for item in items_of(sec):
        for p in patterns:
            if p in item:
                return Result(
                    False,
                    f"「{sec['name']}」里有不可证伪的表述「{p}」：{snippet(item)}",
                )
    return Result(True, f"「{sec['name']}」无不可证伪表述")


def check_require_when_pattern(art: Artifact, params: dict) -> Result:
    trigger = params.get("trigger", [])
    req_sec = params.get("require_section", [])
    req_pat = params.get("require_pattern", [])
    negations = params.get("negation_markers", [])
    min_hits = int(params.get("min_hits", 1))

    if trigger:
        hits = _count_hits(art.text, trigger, negations)
        if hits < min_hits:
            return Result(True, f"未触发（{hits}/{min_hits}）", skipped=True)
        hit = _trigger_hit(art.text, trigger, negations) or trigger[0]
    else:
        hit = None

    missing = []
    if req_sec and art.find_section(req_sec) is None:
        missing.append(f"段落 `## {req_sec[0]}`")
    if req_pat and not art.has(req_pat):
        missing.append(f"文字「{req_pat[0]}」")

    if missing:
        return Result(False, f"出现「{hit}」但缺少 {' 与 '.join(missing)}")

    return Result(True, f"已触发「{hit}」且满足要求")


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
    "forbid_pattern_in_section": check_forbid_pattern_in_section,
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
