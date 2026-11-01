"""加载 values.toml。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


class Config:
    def __init__(self, data: dict, root: Path):
        self.data = data
        self.root = root
        self.version = data.get("version")
        self.name = data.get("name", "")
        self.attribution = data.get("attribution", "")
        self.precedence = data.get("precedence", [])
        self.precedence_reason = data.get("precedence_reason", "").strip()
        self.stages = {s["id"]: s for s in data.get("stages", [])}
        self.values = data.get("values", [])
        self._validate()

    def _validate(self):
        seen = set()
        for v in self.values:
            if "id" not in v or "name" not in v:
                raise ConfigError(f"价值观缺少 id/name: {v}")
            for r in v.get("rules", []):
                rid = r.get("id")
                if not rid:
                    raise ConfigError(f"价值观 {v['id']} 下有规则缺少 id")
                if rid in seen:
                    raise ConfigError(f"规则 id 重复: {rid}")
                seen.add(rid)
                for st in r.get("stage", []):
                    if st not in self.stages:
                        raise ConfigError(f"规则 {rid} 引用了未知阶段: {st}")
                if r.get("check") not in CHECKS:
                    raise ConfigError(
                        f"规则 {rid} 使用了未知检查器: {r.get('check')}（可用: {', '.join(sorted(CHECKS))}）"
                    )

    def stage(self, sid: str) -> dict:
        if sid not in self.stages:
            raise ConfigError(f"未知阶段: {sid}（可用: {', '.join(self.stages)}）")
        return self.stages[sid]

    def rules(self, stage: str | None = None) -> list[dict]:
        out = []
        for v in self.values:
            for r in v.get("rules", []):
                if stage is not None and stage not in r.get("stage", []):
                    continue
                item = dict(r)
                item["_value"] = v["id"]
                item["_value_name"] = v["name"]
                item["_motto"] = v.get("motto", "")
                out.append(item)
        return out

    def rule(self, rid: str) -> dict:
        for r in self.rules():
            if r["id"] == rid:
                return r
        raise ConfigError(f"未知规则: {rid}")


# 延迟导入，避免循环依赖
from .checks import CHECKS  # noqa: E402


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("VH_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    p = (start or Path.cwd()).resolve()
    for cand in [p, *p.parents]:
        if (cand / "values.toml").exists():
            return cand
    if (DEFAULT_ROOT / "values.toml").exists():
        return DEFAULT_ROOT
    raise ConfigError("找不到 values.toml。用 VH_ROOT 指定 harness 根目录。")


def load(root: Path | None = None) -> Config:
    root = root or find_root()
    path = root / "values.toml"
    if not path.exists():
        raise ConfigError(f"找不到 {path}")
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Config(data, root)
