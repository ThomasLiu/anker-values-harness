# CLAUDE.md

把三条价值观（第一性 · 求极致 · 共成长）编译成确定性 lint 的小工具。价值观本身不写进 prompt——写了会失效，原因见 `docs/DESIGN.md`。

Python 3.11+，零依赖。入口是 `vh.py`；`./vh` 和 `.\vh` 是它的薄壳，行为一致。

## 工作流

每个任务走三个阶段，每阶段都是「取 gate → 产出 → lint」：

| 阶段 | 取 gate | 产出 | 判定 |
|---|---|---|---|
| 任务前 | `python vh.py prompt pre_task --task "<任务>"` | 拆解卡 | `python vh.py lint pre_task "<文件>"` |
| 交付前 | `python vh.py prompt pre_deliver` | 交付稿 | `python vh.py lint pre_deliver "<文件>"` |
| 任务后 | `python vh.py prompt post_task` | 沉淀记录 | `python vh.py lint post_task "<文件>"` |

规则内容由 `vh prompt` 注入，这里不另立一套。轻任务加 `--brief` 只注入 blocking 规则——全量 gate 套在每个小任务上，结果是这套东西被关掉。

## 其余命令

```bash
python vh.py stages    # 有哪些阶段、各多少条规则
python vh.py report    # 通过率、最常被拦的规则、critic 均分
python vh.py selftest  # 改过检查器后必须跑
```

## 约定

- 产出存 UTF-8，第一行写阶段标记 `<!-- vh:stage=pre_deliver -->`，hook 靠它选阶段。
- `lint` 非 0 就是被拦下，补内容后重跑。绕过一次，后面的检查就都失去意义。
- 改 `values.toml` 或 `vhcore/checks.py` 属于改判定标准，不是改产出。要做就单独说明，别混在一次交付里。

## 三个会失效的默认做法

1. **读 `values.toml` 和检查器源码来「照着写」。** 看到规则全文会诱发「对着检查表凑结构」——段落齐全、条目够数、实质空洞，而 lint 恰恰判不出这种空洞。规则以 `vh prompt` 的输出为准。
2. **把 lint 通过当成质量合格。** 检查器只判结构，段落写了但内容是套话照样通过。质量那关交给 critic：交付前用 `vh-critic` subagent 评审（它看不到你的自我辩护），返回 `silent_downgrade: true` 或「不可交付」时按不可交付处理，评分用 `critique --record` 写进遥测。
3. **用 `lint-all` 当单文件门禁。** 一份 pre_task 拆解卡永远过不了 pre_deliver 的规则，会 100% 误报。按阶段跑。

## 改代码时

- 动过 `vhcore/` 或 `values.toml` 就跑 `python vh.py selftest`，必须全过。
- 新增规则要同时补正例和反例（`bench/`），只补一边等于没验证。
- 每次逃逸都值得用 `python vh.py promote "<产出>" <规则id>` 沉淀成回归用例。
