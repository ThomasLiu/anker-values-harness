# ROADMAP：把已知缺口堵上

> 这份文档按 harness 自己的格式写，并且必须通过 `vh lint pre_deliver`。
> 通不过就说明这套东西连自己的方案都约束不住。

## 真实目标

**表面需求**：列一份待办清单，把 README 和 DESIGN 里写着的「已知边界」逐条修掉。

**真实目标**：让这套 harness 从「能演示」变成「能日常用」。判断标准不是规则更多，而是**三件事成立**：post_task 真的会被跑、critic 的分数真的会被记下来、配置真的和业务仓库分开。

**依据**：telemetry 里 post_task 一条都没有；critic 至今是手动调用、结果散落在对话里；agent 汇报过「先读了 values.toml 和 checks.py 照着写」。这三条都不是「规则不够」，是**流程没接上**。

所以本方案的排序原则是：**先接流程，再改规则，最后跑实验**。反过来做等于在没人用的功能上加需求。

## 关键假设

- 假设：post_task 没被跑，是因为它挂在「任务结束」这个没有触发点的位置，而不是因为沉淀本身太难 → 验证：给 4 个场景补跑 post_task，若平均返工次数 ≤1 次则假设成立，>2 次说明是规则过重
- 假设：warning 级规则零代价是设计漏洞，不是有意为之 → 验证：查 git log 与 DESIGN.md，确认无「warning 故意不阻断」的论证
- 假设：`fp.number-provenance` 用单位词触发的漏报面大于误报面 → 验证：构造 3 份纯数字无单位的产出，实测漏报数；再跑 r3 盲测统计误报数
- 假设：agent 读源码这件事，靠文档劝阻无效，只能靠物理隔离 → 验证：把 harness 装到仓库外，重跑 OPEN 组，看「照着写」的汇报是否归零

## 验收标准

- G1 至 G9 九条缺口，每条都有可执行的验收命令，全部跑通
- `vh selftest` 用例数从 12 增至 ≥20，通过率 100%
- telemetry 里 post_task 记录数 ≥8 条，critic 记录数 ≥4 条
- 在业务仓库执行 `grep -r "first-principles" .` 返回零结果
- CI 在 PR 上跑通 selftest + 全量 bench，故意改坏一个检查器时 CI 必须红

---

## 缺口清单

### G1 · warning 级规则零代价

**现状**（`vhcore/cli.py:86`）：`return 1 if blocking else 0`。warning 失败不改变退出码，所以 `fp.real-goal`、`ex.debt`、`cg.decision-log` 三条规则**不可能阻止任何东西**——不是没问题，是没问题也不会有后果。

这和 README 那句「没有 lint 的价值观是装饰品」直接冲突：这三条规则现在就是装饰品。

**动作**：
1. `vh lint` 增加 `--strict`：warning 失败也返回 1。
2. 默认行为不改（避免过度返工），但 `vh report` 新增「warning 债务」区块：统计每条 warning 规则的累计失败次数，连续 3 次以上未修复的标红。
3. `post_task` 阶段默认开启 strict——沉淀阶段本来就该严。

**验收**：构造一份只有 warning 失败的产出，`vh lint pre_task <f> --strict` 返回 1；`vh report` 输出含 `warning 债务` 段落且能列出 `fp.real-goal`。

---

### G2 · post_task 从未真跑（共成长零验证）

**现状**：telemetry 里 post_task 记录为 0。共成长这条价值观只有配置、正例、反例，**没有一次真实业务验证**。它涨得最少，原因是「实验没跑到」，不是「规则不行」。

**动作**：
1. **把触发点做出来**，不靠自觉：`vh lint pre_deliver` 通过时，stderr 打印一行 `→ 交付已过，下一步：vh prompt post_task`。不改退出码，只做提示。
2. **重任务强制**：`vh lint pre_deliver --require-post` 时，若同目录不存在 `*-post.md`，返回 2。
3. **补实验**：4 个场景（rd-thermal / rd-recall / nonrd-pricing / nonrd-cell-source）各补跑 post_task，产出存 `eval/r3/runs/`，独立 critic 盲评共成长维度。

**验收**：`vh report` 里 post_task 记录 ≥8 条；`vh report` 能读出共成长维度的 critic 均分，与新分数可对比。

---

### G3 · critic 手动、分数不进 telemetry

**现状**：`vh critique <file>` 只负责渲染 prompt，跑完的 JSON 评分留在对话里，`vh report` 完全看不到。所以「结构合规但实质空洞」这个问题没有任何量化追踪。

**动作**：
1. 新增 `vh critique --record <file> --score <json|@file>`：把 critic 返回的 JSON 写进 telemetry，记录类型标 `kind: "critic"`。
2. `telemetry.py` 的 `report()` 分出 critic 维度：三条价值观均分、`silent_downgrade` 率、`verdict` 分布。
3. **约束不变**：critic 必须独立上下文，CLI 只做「渲染 prompt」和「回收结果」两件事，中间那步由人或另一个 agent 完成。不做自动化评分。

**验收**：`vh report` 输出含「第一性 / 求极致 / 共成长」三条均值；`--record` 写入后 `report --json` 里 `critic` 键非空。

---

### G4 · 配置未与业务仓库分离

**现状**：`config.py:79` 已经支持 `VH_ROOT`，但默认向上查找 `values.toml`，实际都在同一个仓库。agent 读源码后「照着写」是常态，0 返工不能当约束力强的证据。

**动作**（不改代码，改部署形态）：
1. 新增 `vh init --target <业务目录>`：在目标目录写 `.vh/config.toml`，内容只有 `root = "<harness 绝对路径>"`，不含任何规则。
2. `config.py` 的查找顺序改为：`VH_ROOT` > `./.vh/config.toml` > 向上找 `values.toml`。
3. `vh` 脚本做成可软链到 `~/.local/bin`，业务仓库里只放这个软链，不放 harness 本体。
4. 文档写明：业务仓库里**只允许**出现 `vh prompt` 的输出和 `vh lint` 的报错。

**验收**：在业务仓库执行 `grep -r "first-principles" .` 返回零结果；`vh stages` 仍能正常输出。

---

### G5 · fp.number-provenance 有漏报面，且未验证

**现状**：触发词是 `%` `万` `元` `pt` `个点`。「岗位 12 个，客户 3 家，费率 22」这种写法**完全不触发**——因为没带单位词。而这条规则本来就是为了拦「精确的算术、不可靠的依据」。

**动作**：
1. 触发逻辑改为**数字密度**：全文 `\d+` 出现 ≥8 次且缺少 `## 数据来源` 段落即拦。单位词枚举补不完，数字密度不会漏。
2. 防误伤：排除 `## 验收标准`、`## 红队自查` 段落内的数字——那些数字是判据，不是结论。
3. 新增检查器 `require_when_density`，保留旧的原语不动（向后兼容）。
4. 加回归用例 `bench/negative/pre_deliver-bare-numbers.md`。

**验收**：新用例被拦；`bench/positive/pre_deliver-good.md` 仍通过；r3 盲测里 4 份产出的返工次数 ≤2 次/份（超过说明过度返工）。

---

### G6 · telemetry 不进版本库，数据不可复现

**现状**：`.gitignore` 第 3 行 `.vh/`。README 让读者跑 `vh report` 看指标，但 clone 下来是 0 条——所有数字在别人机器上都复现不了。

**动作**：
1. `vh report --export <path>`：把当前 telemetry 归档成 jsonl。
2. 实验数据用 `vh report --export eval/telemetry/r3.jsonl` 归档，**进版本库**；`.vh/` 继续 ignore（那是运行时数据）。
3. `vh report --from <path>` 支持读归档文件。
4. README 的复现命令写成 `vh report --from eval/telemetry/r3.jsonl`。

**验收**：`git clone` 后直接跑 `vh report --from eval/telemetry/r3.jsonl`，输出的通过率与 README 表格一致。

---

### G7 · 没有 CI

**现状**：无 `.github/`。selftest 靠人记得跑，改坏检查器不会被发现。

**动作**：`.github/workflows/vh.yml`，三个 job：
1. `selftest`：跑 `vh selftest`，17 个用例必须全过。
2. `lint-bench`：对 `bench/positive/*` 跑对应阶段 lint，必须 exit 0。
3. `config-valid`：加载 `values.toml`，校验所有规则引用的检查器存在。

**验收**：PR 上绿灯；故意把 `check_require_section` 的 `min_items` 判断改成 `<=`，CI 必须红。

---

### G8 · 逃逸用例靠手写，没有沉淀机制

**现状**：`bench/negative/` 里 11 个用例全是手写的。DESIGN.md 说「给每次逃逸加一条回归用例」，但没有工具支持，等于靠自觉。

**动作**：新增 `vh promote <artifact> <rule-id>`：把一份被拦下的真实产出复制进 `bench/negative/`，自动追加到 `cases.toml`，然后立刻跑 selftest 确认新用例有效。

**验收**：`vh promote` 后 `cases.toml` 条目数 +1，`vh selftest` 用例数同步 +1 且全过。

---

### G9 · 检查器只判结构（不堵，降低伤害）

**现状**：这是已知边界，DESIGN.md 明确写了「防的是无意识的偷懒，不是防恶意」。试图堵死会掉进军备竞赛。

**动作**：不增加规则数量，只给三条最容易被糊弄的规则加**二级判据**：
1. `ex.redteam`：每条必须含条件句（`如果` / `若` / `一旦`）+ 后果词。现在只查后果词，写「导致排期掉期」就能过。
2. `fp.assumption-explicit`：验证方式不得是「让对方一句话推翻」——把验证成本转嫁给对方不算验证。
3. `ex.debt`：技术债必须有明确到期日（`Q\d` / `\d+月` / `\d+周` / `下周`），「客户给数据后重算」等于无到期日。

**验收**：三条规则各自的 negative 用例被拦；正例仍通过。

---

## 分批次

| 批次 | 内容 | 性质 | 风险 | 状态 |
|---|---|---|---|---|
| **P0** | G6 归档、G7 CI、G8 promote、G3 critic 回收 | 纯工程，不改判定语义 | 低 | 已完成 2026-11-01 |
| **P1** | G1 warning 代价、G5 数字密度、G9 二级判据 | 改判定语义，可能误伤 | 中 | 待启动 |
| **P2** | G2 post_task 实验、G4 部署隔离 | 靠跑，不靠写 | 低 | 待启动 |

P0 是纯增量，不动任何现有行为，可以直接做。P1 会改变判定结果，做完必须重跑 selftest 和一轮盲测。P2 不是写代码，是跑实验和改部署形态，做完了才谈得上「堵上」。

## 备选方案

- **方案 B：推倒重来，换成 LLM-as-judge 做全部判定。** 好处是能判质量、能抓「结构合规但空洞」；代价是每次 lint 要一次模型调用、结果不确定、不可离线、没法进 CI。否决理由：deterministic-first 是这个项目唯一站得住的差异化，换掉就变成又一个 prompt 工程。
- **方案 C：只做 G2 和 G4，其余放着。** 好处是两件事就能让「能演示」变成「能日常用」；代价是 warning 零代价、数据不可复现、无 CI 这三条会持续腐蚀可信度，半年后没人敢信 `vh report` 的数字。否决理由：G6 和 G7 加起来不到半天工作量，性价比太高。
- **方案 D：维持现状，把 README 的「已知边界」写得更诚实。** 好处是零成本；代价是这项目的卖点就是「能判真假」，承认判不了就没卖点了。

## 红队自查

- **如果 post_task 的返工主要来自「沉淀」段落写不出来，而不是流程没触发**，那 G2 做完只会让 agent 学会写一段套话过关，共成长维度仍然零验证，整个方案的第一优先级就选错了。这个假设我现在无法在跑实验前验证。
- **如果把 warning 改成 strict，agent 会开始对着 warning 规则做形式化填充**（它已经会对着 blocking 规则这么干了），结果是产出更长、更空，lint 通过率上升但 critic 分数不动甚至下降，那 G1 就是负收益。
- **如果数字密度触发阈值定低了**，凡是带验收标准的产出都会被拦，因为验收标准天生全是数字，返工率飙升，两周后这套东西被关掉——这是 DESIGN.md 里写的最常见的死法。
- **如果 G4 的物理隔离做成了，但 agent 转而从 `vh lint` 的报错文案里反推规则**，那隔离就是白做的，规则可见与不可见的差距不会缩小。报错文案里已经带了 `fix:` 提示，等于把规则讲了一遍。
- **如果这九条都做完了，最大的风险是「所有缺口都堵上了」这个结论本身**：单场景单 critic 的小样本撑不起任何关于「有效性」的断言，方案验收标准全是工程指标，没有一条是「产出质量提升」。方案可能全绿而项目实际上没变好，那「缺口已堵上」这个结论就不成立。

## 影响范围

**谁能看到**：只影响本仓库和 Thomas 本地的 harness 使用，不涉及对外发布、不涉及客户数据。P0 会新增 `.github/workflows/`，如果仓库设为公开，CI 日志公开可见（当前内容是 bench 用例和规则，不含业务数据）。

**能否撤回**：可以。P0 是纯增量（新命令、新文件），删掉即恢复。P1 改的是 `values.toml` 的 `params` 和 `checks.py` 的两个函数，`git revert` 即可。G4 改部署形态，但代码层面只是调整 `find_root` 的查找顺序，回退改一行。

**最坏后果**：P1 的误伤导致返工率上升，如果没人及时调阈值，使用者会开始 `--no-verify` 式绕过，harness 名存实亡。这个后果不可逆——一旦形成绕过习惯，加再多规则都没用。

**补救方式**：P1 上线前先在现有 bench 产出上回扫一遍，统计误报数；误报率 >20% 就不上线。上线后第一周盯 `vh report` 的返工率，超过基线 1.5 倍立即回滚。

## 数据来源

本文的每条数字都能用仓库里的命令复现：

- **规则数、反例覆盖**：解析 `values.toml` 的 `[[values.rules]]` 与 `bench/cases.toml` 的 `expect_rules` 求差集。
- **`selftest` 17/17**：`python vh.py selftest`。
- **「岗位 12 个，客户 3 家，费率 22」不触发 `fp.number-provenance`**：把这段写进任意 markdown 后 `vh lint pre_deliver <f>`，exit 0——三个数字都没带单位词。
- **「目前不打算发送任何群发消息」被误报为 `ex.blast-radius` 触发**：同样构造一份产出实测，否定词窗口 4 字符不够长，`不打算发送` 里的「发送」仍被当成动作。

## 技术债

- **数字密度阈值 8 是拍的，没有数据支撑。** 为什么现在不还：需要先统计一轮完整实验产出的数字分布才能定。什么时候还：G5 实施前，用 `grep -o '[0-9]\+' eval/r3/runs/**/*.md | wc -l` 跑一遍分布再定。
- **`vh promote` 会把产出原文复制进 bench，里面可能含业务信息。** 为什么现在不还：当前 bench 都是自造用例，暂无泄漏。什么时候还：第一次用真实业务产出 promote 之前，必须先做脱敏。
- **G4 的 `vh init` 只做单向生成，没有 `vh deinit`。** 为什么现在不还：回滚靠手删 `.vh/config.toml` 即可。什么时候还：出现第二次「想撤销但删错了」的时候。

## 取舍声明

取舍声明：为了本周能把 P0 做完并上线，放弃了在 P0 阶段一并做 G4 的部署隔离，因为 G4 需要改 `find_root` 的查找顺序、影响所有已有调用路径，和纯增量的 P0 混在一起会让回滚变复杂。这个牺牲可接受的前提是：P0 期间继续只在单仓库内使用，不对外声称「配置已隔离」——README 里那句「真实部署应分离」保持原样，不改写成「已解决」。
