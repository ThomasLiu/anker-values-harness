# CLAUDE.md

这个仓库把三条价值观（第一性 · 求极致 · 共成长）编译成可执行的 gate / lint / telemetry。
你在本仓库或使用本 harness 的项目里工作时，**三阶段流程是强制的，不是建议**。

命令一律用 `python vh.py`（Windows / macOS / Linux 通用）。

## 三阶段流程

| 阶段 | 命令 | 产出 | 通过条件 |
|---|---|---|---|
| 任务前 | `python vh.py prompt pre_task --task "<任务>"` | 拆解卡 | `python vh.py lint pre_task <文件>` exit 0 |
| 交付前 | `python vh.py prompt pre_deliver` | 交付稿 | `python vh.py lint pre_deliver <文件>` exit 0 |
| 任务后 | `python vh.py prompt post_task` | 沉淀记录 | `python vh.py lint post_task <文件>` exit 0 |

每个阶段都必须：**先 `prompt` 拿 gate → 按骨架产出 → `lint` 验证**。跳过 prompt 直接产出等于没跑。

## 硬规则

1. **lint 非 0 就是被拦下。** 补内容后重跑，不要绕过、不要换阶段重跑、不要 `--no-log` 掩盖。
2. **不许为了让 lint 通过去改 `values.toml` 或 `vhcore/checks.py`。** 规则是判定标准，不是障碍物。真要改，先说明这是改标准而不是改产出。
3. **规则以 `vh prompt` 的输出为准。** 不要去读 `values.toml` 和检查器源码「照着写」——实测过，那只会产出形式合规、实质空洞的东西。
4. **轻任务用 `--brief`。** 只注入 blocking 规则。给每个任务都套全套 gate 的后果是这套东西被关掉。
5. **产出文件存 UTF-8。** GBK 也能读，但会提示你另存。

## 交付前

跑完 `lint pre_deliver` 之后，用 `vh-critic` subagent 做一次独立评审（它看不到你的自我辩护）：

```
交给 vh-critic：<产出文件路径>
```

critic 返回 `silent_downgrade: true` 或 `verdict: 不可交付` 时，不许交付。拿到评分后用
`python vh.py critique <文件> --record <score.json>` 写进遥测。

## 不要做的事

- 不要自评。自我一致性偏差会让你永远给自己高分。
- 不要把「写了段落」当成「满足要求」。检查器只判结构，critic 判质量，两个都过才算过。
- 不要在没跑 gate 的情况下声称任务完成。
