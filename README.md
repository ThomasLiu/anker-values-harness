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

零依赖，Python 3.11+（用到 `tomllib`）。

```bash
git clone git@github.com:ThomasLiu/anker-values-harness.git
cd anker-values-harness

./vh stages                                  # 看有哪些阶段和规则
./vh prompt pre_task --task "帮我写触达文案"   # 拿任务前的 gate
./vh lint pre_task 拆解卡.md                  # 检查产出，exit 0 才放行
./vh report                                  # 看指标
./vh selftest                                # 验证检查器本身有效
```

接到任何 agent 上的最小用法：

```
1. 任务开始 → vh prompt pre_task --task "<任务>" → 按骨架产出 → vh lint pre_task
2. 交付之前 → vh prompt pre_deliver → 补齐 → vh lint pre_deliver
3. 任务结束 → vh prompt post_task → 沉淀 → vh lint post_task
```

lint 非 0 就返工。绕过一次，这套 harness 就废了。

## 规则一览

| 价值观 | 规则 | 阶段 | 级别 | 查什么 |
|---|---|---|---|---|
| 第一性 | `fp.real-goal` | 任务前 | warning | 区分表面需求与真实目标 |
| 第一性 | `fp.assumption-explicit` | 任务前/交付前 | blocking | 关键假设 ≥2 条，每条带验证方式 |
| 第一性 | `fp.no-convention-appeal` | 交付前 | blocking | 禁止用「行业惯例」当理由（同行有「因为/测算/依据」则放行） |
| 第一性 | `fp.alternatives` | 交付前 | blocking | 备选方案 ≥2 个 |
| 求极致 | `ex.criteria-first` | 任务前 | blocking | 验收标准 ≥2 条且可判定 |
| 求极致 | `ex.redteam` | 交付前 | blocking | 红队自查 ≥3 条致命弱点 |
| 求极致 | `ex.blast-radius` | 交付前 | blocking | 不可逆动作必须写影响范围 |
| 求极致 | `ex.debt` | 交付前 | warning | 写死特例必须登记技术债 |
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
docs/DESIGN.md       设计取舍与已知缺陷
```

## 已知边界

- **lint 只查结构，不查质量。** 它拦得住「没有红队自查」，拦不住「红队自查写得敷衍」。后者交给 `evaluator/critic.md`，但 critic 是概率性的，不是门禁。
- **正则会被绕。** 一个足够聪明的模型可以写出形式上合规、实质空洞的产出。这套 harness 的目标不是防恶意，是防无意识的偷懒。
- **不是所有任务都值得跑全量。** 轻任务用 `vh prompt <stage> --brief`，只注入 blocking 规则。给每个任务都套全套 gate 的后果是 harness 被关掉——这是最常见的一种死法。

## License

MIT
