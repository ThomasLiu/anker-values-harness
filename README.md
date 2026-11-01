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

python vh.py stages                                         # 看有哪些阶段和规则
python vh.py prompt pre_task --task "65W 充电器温升超标能不能出货"  # 拿任务前的 gate
python vh.py lint pre_task 拆解卡.md                          # 检查产出，exit 0 才放行
python vh.py report                                         # 看指标
python vh.py selftest                                       # 验证检查器本身有效
python vh.py promote 逃逸产出.md ex.redteam                   # 把一次逃逸沉淀成回归用例
python vh.py critique 交付稿.md --record score.json           # 回收 critic 评分
```

`python vh.py` 是三个平台通用的写法。偷懒的话 POSIX 用 `./vh`，Windows 用 `.\vh`（走 `vh.cmd`），两者都只是转发到 `vh.py`。

`.vh/` 是运行时数据，不进版本库。要留档就用 `vh report --export <path>` 导出 jsonl，`vh report --from <path>` 能读回来。

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

hook 不猜阶段，只看产出第一行的标记 `<!-- vh:stage=pre_deliver -->`，没有标记就跳过。刻意不用 `lint-all`：一份 pre_task 拆解卡永远过不了 pre_deliver 的规则，那样每次写入都会误报，hook 两天内就会被关掉。

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
vh.py                CLI 主入口（vh / vh.cmd 转发到它）
vhcore/              零依赖实现
gates/               三个阶段的操作手册（怎么做得比 lint 要求更好）
rubrics/             0-3 分档描述，给 critic 用
evaluator/critic.md  独立评审 prompt（不共享上下文，防自我一致性偏差）
bench/               17 份判定基准：6 正例 + 11 反例，selftest 用
scenarios/           10 个安克真实业务场景（研发 5 / 非研发 5）
CLAUDE.md            Claude Code 自动加载的三阶段 SOP
docs/DESIGN.md       设计取舍与已知缺陷
docs/ROADMAP.md      缺口清单与分批次方案
.github/workflows/   CI：Linux + Windows 双平台跑 selftest 与正例
```

## 测试场景：安克的真实办公室

`scenarios/scenarios.toml` 里是 10 个真实业务场景，研发岗与非研发岗各 5 个。选场景的标准是三条：真实会发生、有取舍、至少涉及一个不可逆或对外动作。

| 场景 | 岗位 | 卡在哪 |
|---|---|---|
| 65W GaN 充电器 45℃ 满载 78℃ | 硬件研发 | 改模 12 万 vs 放行 |
| eufy 扫地机深色地毯定位丢失 | 算法研发 | 调参糊过去 vs 承认传感器到极限 |
| soundcore 耳机固件全量推送 | 嵌入式 | 3.2% 用户受影响，推出去收不回 |
| Nebula 投影亮度标称口径 | 硬件 + 产品 | 法务不许认，用户投诉 40 条 |
| 41.2 万台移动电源批次召回 | 质量 + 硬件 | 3.9 亿成本 vs 热失控 |
| 电芯二供导入，顺带压价 7% | 供应链 | 保供 vs 降本 |
| 北美站新品首发定价与备货 | 电商运营 | 价格带 vs 类目排名 |
| 割草机器人 Q4 是否继续投 | 品类规划 | 规模不够 vs 产品力不够 |
| 算法团队扩编的人才画像 | HR | 大厂背景要求 vs 80 万预算 |
| 批量客诉的统一口径 | 客服 | 40 个客服各自为政 |

`bench/` 里是对应的判定基准：6 份合格产出（正例）+ 11 份真实逃逸样本（反例，每条 blocking 规则一个）。`vh selftest` 跑这 17 份。

正例必须全过——否则是误报，合格产出被打回，agent 会开始绕过 harness。反例必须被指定规则拦下——否则是漏报，harness 变成装饰品。

## 已知边界

- **lint 只查结构，不查质量。** 它拦得住「没有红队自查」，拦不住「红队自查写得敷衍」。后者交给 `evaluator/critic.md`，但 critic 是概率性的，不是门禁。
- **正则会被绕。** 一个足够聪明的模型可以写出形式上合规、实质空洞的产出。这套 harness 的目标不是防恶意，是防无意识的偷懒。
- **不是所有任务都值得跑全量。** 轻任务用 `vh prompt <stage> --brief`，只注入 blocking 规则。给每个任务都套全套 gate 的后果是 harness 被关掉——这是最常见的一种死法。

## License

MIT
