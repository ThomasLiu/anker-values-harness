# anker-values-harness

把企业价值观编译成 agent 可执行的 **gate / rubric / telemetry**，让「第一性 · 求极致 · 共成长」真正支配每一个任务，而不是变成 system prompt 里的一段装饰。

> 这是一个个人实验项目，与安克创新（Anker Innovations）无隶属关系。价值观表述引自其公开资料，实现方式是作者自己的。

---

## 问题

把价值观写进 system prompt 会失效，原因是结构性的：

| 失效原因 | 表现 | 对策 |
|---|---|---|
| **不可判定** | 「求极致」没有通过/不通过，模型只能靠自我感觉 | 每条价值观拆成带 `check` 的规则，lint 能判真假 |
| **不显形** | 多数任务里价值观不冲突，模型感知不到要调用 | gate 挂在固定阶段，强制产出对应字段 |
| **无代价** | 违反了没有任何反馈，下次照旧 | lint 失败退出码非零，不返工不能交付 |

一句话：**没有 lint 的价值观是装饰品。**

## 怎么做的

三条价值观 → 三层编译：

```
价值观（values.toml）
   ↓ 编译
gate（注入层）       vh prompt <stage>   按阶段注入规则，不注入全部
   ↓
lint（判定层）       vh lint <stage> <f> 确定性检查，非 0 即打回
   ↓
telemetry（观测层）  vh report            看价值观有没有漂移
```

价值观留在人格层，具体规则按阶段注入——这是刻意的。价值观段落越长，注意力稀释越严重。

## 快速开始

零依赖，Python 3.11+（用到 `tomllib`）。macOS / Linux / Windows 都能跑。

```bash
git clone git@github.com:ThomasLiu/anker-values-harness.git
cd anker-values-harness

python vh.py stages                                    # 看有哪些阶段和规则
python vh.py prompt pre_task --task "帮我写触达文案"     # 拿任务前的 gate
python vh.py lint pre_task 拆解卡.md                    # 检查产出，exit 0 才放行
python vh.py report                                    # 看指标
python vh.py selftest                                  # 验证检查器本身有效
python vh.py report --from eval/telemetry/r1-r2.jsonl  # 从归档复现历史数据
python vh.py promote 逃逸产出.md ex.redteam             # 把一次逃逸沉淀成回归用例
python vh.py critique 交付稿.md --record score.json     # 回收 critic 评分
```

`python vh.py` 是三个平台通用的写法。偷懒的话 POSIX 用 `./vh`，Windows 用 `.\vh`（走 `vh.cmd`），两者都只是转发到 `vh.py`。

`.vh/` 是运行时数据，不进版本库；实验用的遥测归档在 `eval/telemetry/`，那份进库——否则 clone 下来所有数字都不可复现。

接到任何 agent 上的最小用法：

```
1. 任务开始 → vh prompt pre_task --task "<任务>" → 按骨架产出 → vh lint pre_task
2. 交付之前 → vh prompt pre_deliver → 补齐 → vh lint pre_deliver
3. 任务结束 → vh prompt post_task → 沉淀 → vh lint post_task
```

lint 非 0 就返工。绕过一次，这套 harness 就废了。

## 接到 Claude Code

仓库里已经放好接线，clone 下来用 `claude` 打开就生效，不用额外配置：

| 文件 | 作用 |
|---|---|
| `CLAUDE.md` | 三阶段 SOP，Claude Code 自动读进上下文 |
| `.claude/agents/vh-critic.md` | 独立评审 subagent，不共享主 agent 上下文 |
| `.claude/hooks/vh-gate.py` | 可选硬门禁：写完 markdown 自动跑 lint，没过就回灌给 agent |

注意 `CLAUDE.md` 是**软约束**：它让 agent 知道该跑 gate，但拦不住 agent 跳过。要变成硬门禁，把 `.claude/settings.example.json` 的内容合并进 `.claude/settings.json`：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PROJECT_DIR}/.claude/hooks/vh-gate.py\""
          }
        ]
      }
    ]
  }
}
```

（macOS 上若没有 `python` 命令，改成 `python3`。）

默认**没有**装这个 hook。原因是它会对每一次文件写入触发，轻任务上纯属噪音——DESIGN.md 里写过，「给每个任务都套全套 gate 的后果是 harness 被关掉」。等三阶段流程跑顺了再考虑上硬门禁。

## 跨平台

三处平台差异已经处理掉，Windows 上不用改任何东西：

| 差异 | 处理 |
|---|---|
| 没有 shebang / 执行位 | `vh.py` 是主入口，`vh`（POSIX）和 `vh.cmd`（Windows）都转发到它 |
| 控制台代码页不是 UTF-8 | 启动时把 stdout/stderr 钉成 UTF-8，重定向到管道也不会崩 |
| 编辑器存 GBK / 带 BOM | 读产出时按 UTF-8 → GB18030 降级，并提示建议另存 UTF-8 |
| autocrlf 把脚本改成 CRLF | `.gitattributes` 强制 `vh` / `*.py` 用 LF，`*.cmd` 用 CRLF |

CI 同时跑 `ubuntu-latest` 和 `windows-latest`，两边都必须过。

## 规则一览

| 价值观 | 规则 | 阶段 | 级别 | 查什么 |
|---|---|---|---|---|
| 第一性 | `fp.real-goal` | 任务前 | warning | 区分表面需求与真实目标 |
| 第一性 | `fp.assumption-explicit` | 任务前/交付前 | blocking | 关键假设 ≥2 条，每条带验证方式 |
| 第一性 | `fp.assumption-falsifiable` | 任务前/交付前 | blocking | 假设里禁止「应该/可能/大概/或许」 |
| 第一性 | `fp.no-convention-appeal` | 交付前 | blocking | 禁止用「行业惯例」支撑决策（有理由或纯描述则放行） |
| 第一性 | `fp.number-provenance` | 交付前 | blocking | 数字结论 ≥3 个时必须声明来源或标注估算 |
| 第一性 | `fp.alternatives` | 交付前 | blocking | 备选方案 ≥2 个 |
| 求极致 | `ex.criteria-first` | 任务前 | blocking | 验收标准 ≥2 条且可判定 |
| 求极致 | `ex.redteam` | 交付前 | blocking | 红队自查 ≥3 条，每条要说清「如果成立什么会废掉」 |
| 求极致 | `ex.blast-radius` | 交付前 | blocking | 不可逆动作必须写影响范围（否定句不算触发） |
| 求极致 | `ex.debt` | 交付前 | warning | 写死/草稿/占位必须登记技术债 |
| 共成长 | `cg.asset` | 任务后 | blocking | 沉淀必须是可加载资产，不是感想 |
| 共成长 | `cg.decision-log` | 任务后 | warning | 决策必须记理由 |
| 共成长 | `cg.tradeoff-declared` | 任务后 | blocking | 有降级必须声明取舍 |
| 仲裁 | `arb.no-silent-downgrade` | 交付前 | blocking | 不允许静默降级 |

## 冲突仲裁

三条价值观一定打架。**唯一硬规则：不允许静默降级。**

任何取舍必须写成：

```
取舍声明：为了 X 放弃了 Y，因为 Z。牺牲可接受的前提是：……
```

默认优先级：

```
安全/不可逆  >  共成长(长期资产)  >  第一性(判断质量)  >  求极致(打磨程度)
```

求极致故意排最后——它是最容易被时间挤掉的一条，必须让它在取舍中被**明确牺牲**，而不是被**悄悄遗忘**。

## 目录

```
values.toml          唯一事实源：价值观 → 规则 → 检查器
VALUES.md            人读版：释义 + 正例/反例
vh                   CLI 入口
vhcore/              零依赖实现
gates/               三个阶段的操作手册（怎么做得比 lint 要求更好）
rubrics/             0-3 分档描述，给 critic 用
evaluator/critic.md  独立评审 prompt（不共享上下文，防自我一致性偏差）
bench/               正例/反例基准，selftest 用
scenarios/           业务场景用例
eval/                A/B 实测记录
eval/telemetry/      归档遥测，report --from 读它
docs/DESIGN.md       设计取舍与已知缺陷
docs/ROADMAP.md      缺口清单与分批次方案
.github/workflows/   CI：selftest + 正例全过 + 配置校验
```

## 实测

两轮 subagent 实验，4 个猎头业务场景，独立 critic 盲评（每条价值观 0-3 分，满分 9）：

| 条件 | 合计 /36 | 第一性 | 求极致 | 共成长 | 静默降级 |
|---|---|---|---|---|---|
| 裸跑 | 12 | 1.00 | 0.25 | 1.75 | 3/4 份有 |
| 带 harness（规则可见） | 24 | 1.75 | 2.50 | 1.75 | 0/4 |
| 带 harness（盲测） | **31** | **2.25** | **3.00** | **2.50** | **0/4** |

三点结论：

1. **求极致从 0.25 涨到 3.00 是最大的贡献。** 裸跑时零份写红队自查、零份写影响范围——不是能力问题，是没有要求就不会主动自我否定。
2. **规则透明会被反向利用。** 规则可见组里 4/6 个 agent 汇报「我先读了 values.toml 和检查器源码，照着写」。真实部署应把配置和业务仓库分离（`VH_ROOT` 指到仓库外），agent 只看 `vh prompt` 输出。
3. **没解决的是「结论确定度高于证据强度」。** critic 在三个场景里独立给出同一个判断。为此加了 `fp.number-provenance`，但尚未经过新一轮验证。

完整数据、被修掉的 7 个解析 bug 见 [`eval/RESULTS.md`](eval/RESULTS.md)。原始数字可直接复现：

```bash
./vh report --from eval/telemetry/r1-r2.jsonl   # 43 次 lint 的通过率与被拦规则
./vh selftest                                    # 13 个基准用例
```

## 已知边界

- **lint 只查结构，不查质量。** 它拦得住「没有红队自查」，拦不住「红队自查写得敷衍」。后者交给 `evaluator/critic.md`，但 critic 是概率性的，不是门禁。
- **正则会被绕。** 一个足够聪明的模型可以写出形式上合规、实质空洞的产出。这套 harness 的目标不是防恶意，是防无意识的偷懒。
- **不是所有任务都值得跑全量。** 轻任务用 `vh prompt <stage> --brief`，只注入 blocking 规则。给每个任务都套全套 gate 的后果是 harness 被关掉——这是最常见的一种死法。

## License

MIT
