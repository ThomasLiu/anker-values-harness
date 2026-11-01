"""轻量 markdown 结构解析。

只做一件事：把一份产出切成「段落 -> 条目」，供确定性检查使用。
刻意不引入 markdown 库——检查器要足够简单，才不会成为新的故障点。
"""

from __future__ import annotations

import re

HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*#*\s*$")
BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*\s*[:：]?\s*$")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP = re.compile(r"^\s*\|[\s:|\-]+\|\s*$")


def normalize(name: str) -> str:
    s = name.strip().strip("*_`# ")
    s = re.sub(r"[\s\u3000]+", "", s)
    return s.rstrip("：:")


class Artifact:
    """一份待检查的产出。"""

    def __init__(self, text: str, path: str = "<inline>"):
        self.text = text
        self.path = path
        self.lines = text.splitlines()
        self.sections = self._parse()

    def _parse(self):
        sections = []
        current = None
        for raw in self.lines:
            line = raw.rstrip()
            m = HEADING.match(line)
            name = None
            level = 0
            if m:
                level = len(m.group(1))
                name = m.group(2)
            else:
                mb = BOLD_LINE.match(line)
                if mb:
                    level = 7
                    name = mb.group(1)
            if name:
                current = {
                    "name": name.strip(),
                    "norm": normalize(name),
                    "level": level,
                    "lines": [],
                }
                sections.append(current)
                continue
            if current is not None:
                current["lines"].append(line)
        return sections

    def find_section(self, aliases):
        """按「最具体」原则匹配段落。

        文档标题（H1）经常包含正文段落的名字，例如 `# 沉淀记录` 会匹配到
        「沉淀」。所以匹配要分级：精确 > 前缀 > 包含，同级取名字最短的，
        并且 H1 一律降权——标题不是段落。
        """
        if not aliases:
            return None
        best = None
        best_key = None
        for sec in self.sections:
            for w in aliases:
                w = normalize(w)
                if not w:
                    continue
                norm = sec["norm"]
                if norm == w:
                    rank = 0
                elif norm.startswith(w):
                    rank = 1
                elif w in norm:
                    rank = 2
                else:
                    continue
                key = (rank, 1 if sec["level"] == 1 else 0, len(norm))
                if best_key is None or key < best_key:
                    best_key = key
                    best = sec
        return best

    def section_names(self):
        return [s["name"] for s in self.sections]

    def has(self, needles):
        return any(n in self.text for n in needles)


def items_of(section) -> list[str]:
    """取段落下的条目。

    markdown 里一条 bullet 常常跨行（续行用缩进），续行必须归并到上一条，
    否则「- 假设：…… \\n  → 验证：……」会被判成「假设没有验证方式」。
    """
    out = []
    prose = []
    for line in section["lines"]:
        if not line.strip():
            continue
        m = ITEM.match(line)
        if m:
            out.append(m.group(1).strip())
            continue
        if TABLE_SEP.match(line):
            continue
        if TABLE_ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append(" ".join(c for c in cells if c))
            continue
        if out and line[:1] in (" ", "\t", "　"):
            out[-1] = out[-1] + " " + line.strip()
            continue
        prose.append(line.strip())
    if not out and prose:
        return [" ".join(prose)]
    return out


def snippet(s: str, n: int = 60) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
