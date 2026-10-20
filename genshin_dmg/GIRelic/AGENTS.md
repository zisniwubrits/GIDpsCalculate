# 圣遗物子系统（`genshin_dmg/GIRelic/`）开发约定

> 本文件是仓库根 `AGENTS.md` 的**补充**，只覆盖圣遗物这一块；冲突时**以根 `AGENTS.md` 为准**。
> 只写"这里特有"的规则（口径、公式、接口、坑），通用开发规范不重复抄。

**目录**

| § | 内容 |
|---|---|
| [0](#0-协作约定) | 协作约定（概述 / 先问清 / 责任对半 / 一轮做完） |
| [1](#1-定位与边界) | 定位与边界（独立性、分层、跨界类型） |
| [2](#2-口径已与用户确认改动前必须问) | 口径（近似、刷取、词条、筛选、置信度） |
| [3](#3-数学约定) | 数学约定（分布、通式、精度、Jensen） |
| [4](#4-代码约定) | 代码约定 |
| [5](#5-接口清单) | 接口清单 |
| [6](#6-测试约定) | 测试约定 |
| [7](#7-已知坑) | 已知坑 |
| [8](#8-进度) | 进度 |
| [9](#9-提交约定) | 提交约定 |
| [10](#10-计划通用-dll) | 计划：通用 DLL |

---

## 0. 协作约定

### 0.1 动手前先概述（用户要求）

**每次动手之前，先用一两句话说明"要改哪个文件、加什么函数、跑什么命令"，再执行。**
概述里要写清**会不会碰 `graph.py` / 前端 / HTTP**，让用户一眼判断影响面。
一步一个原子逻辑；做完报结果（改了什么、测试多少 passed、提交号）；方向不对就停下来说明。

### 0.2 「怪我没讲清楚，也怪你没问清楚」（用户原话，责任对半）

- 讲得不清楚是**双方**的失误：事后不许拿"你没说清"当返工理由，也不许闷头猜。
- AI 的义务：
  1. 把需求**复述成可检验的规格**（输入 / 输出 / 边界 / 判据）先确认，再写码；
  2. 发现用户前提与代码事实不符时，**先摆证据**（跑一遍、给实测数字）再问要不要改——
     例：`(3,0,0,2,0)` 是**投影**状态，不代表"这件只有 2 条词条"；
  3. 一个回合内把能问的歧义**一次问完**，带选项 + 推荐项，不要挤牙膏；
  4. 宁可多问一轮，也不要按错误理解写一整块代码再回滚。
- 结论落到文档/提交信息里，写清"为什么这么定"。

### 0.3 一轮做完

方案确认后，**同一回合内走完**：改代码 → 跑测试 → 提交。只有三种情况可以停：
真正的分叉要用户选、外部条件阻塞、触及约定冲突或破坏性操作。不许用"要我下一轮做吗"收尾。

---

## 1. 定位与边界

- **纯后端、纯 Python 层**：只写在 `genshin_dmg/GIRelic/` 里，**不出 HTTP 接口、不改 `/api/schema`、不动前端**。
- **包里自带副本，不 import 主程序实现**：
  参考表 → `relic_tables.py`；通用公式/工具（`mangle` / 全角表 / 抗性系数 / 防御系数）→ `relic_math.py`。
  副本与主体的一致性由 `tests/test_relic_independence.py` 对拍；整目录搬走时连同该测试一起删。
- **单向依赖**（`★` 是唯一例外）：

  ```
  relic_tables.py   参考表副本（RELIC_ROWS），零 import
  relic_math.py     工具副本（mangle / FULLWIDTH / 抗性·防御系数 / clamp），零外依赖
  relic.py          纯算术：树脂 / 词条 / 单件分布 / 通式 / 置信度
  relic_program.py  函数表示：run(程序, 属性) → 伤害（纯执行，不碰工程）
  relic_adapter.py  ★唯一允许 import graph 的地方：GraphDamageFn / damage_fn_from_project /
                    compile_project（工程 → 上面两者）
  ```

- **主体不得 import relic**：主程序不依赖圣遗物；将来要暴露功能，只加薄接口（如 `POST /api/relic/...`），
  由 adapter 调用，不让画布/求值逻辑引用 relic。
- **跨界只认数字**：`list[float]`（9 项属性）、`dict` 程序结构、`float` 伤害值；不传 Graph / 卡片 / 前端字段。
- **失败用异常表达**：不能编译 → `NotCompilable`；输入非法 → `ValueError`；不静默兜底。
- **可删性自检**：删掉 `relic*.py` 后主程序仍能完整跑（`pytest` 全绿）。
- `graph.py` 只在 adapter 的函数体内**惰性** import，`import relic` 不会把图求值拖进来（静态测试守住）。

---

## 2. 口径（已与用户确认，改动前必须问）

### 2.1 三级近似（用户指定；只做这三个近似，其余精确枚举）

| 阶 | 近似 | 常量 | 含义 |
|---|---|---|---|
| 一阶 | 5 个部位**严格等概率** | `SLOT_SHARE = 1/5` | 指定部位必须乘 1/5（否则成本偏小 5 倍，踩过） |
| 二阶 | 副本两套**严格等概率** | `SET_SHARE = 0.5` | 目标套件数 = 掉落件数 × 1/2；散件槽不乘 |
| 三阶 | 初始词条数**严格 3:4 = 4:1** | `FOUR_SUB_RATE = 0.2` | 80% 三词条起手、20% 四词条起手 |

不要引入部位偏好、幸运值、保底之类的东西。BOSS/周本/三合一的 34% 只作可选参数。

### 2.2 刷取与主词条

| 项 | 口径 |
|---|---|
| 副本消耗 | **20 原粹树脂/次** |
| 每次产出 | 必掉 1 件 + **6.5%** 再掉 1 件 → **1.065 件/次** |
| 部位 | 5 个各 1/5 |
| 套装 | 两套各 50%；4 件套 + **允许 1 个散件槽**（任意套） |
| 树脂上限 / 浓缩树脂 | 200（只影响"天数"换算）/ 暂不建模 |

主词条（随机，不能自选）：花固定生命 4780；羽固定攻击 311；
沙（5）生命% / 攻击% / 防御% / 充能 / 精通；
杯（**12** = 7 元素 + **物理**各 5% + 攻击% / 生命% / 防御% / 精通）；
冠（7）生命% / 攻击% / 防御% / 精通 / 暴击率 / 暴击伤害 / 治疗。三张表各自合计 100%。

期望树脂：`20 / (1.065 × 套装份额 × 1/5 × p)`（散件槽不乘套装份额）。

### 2.3 副词条与强化

| 词条 | 权重 |
|---|---|
| 固定生命 / 固定攻击 / 固定防御 | 150 |
| 暴击率 / 暴击伤害 | 75 |
| 生命% / 攻击% / 防御% / 充能 / 精通 | 100 |
| **合计** | **1100** |

- 抽取：按权重、**不放回**，且不与主词条同名 → 池最多 10 项（元素伤害/物理/治疗没有副词条）。
- 初始 3 或 4 条（`FOUR_SUB_RATE`）；**恒为 4 条**（3 条起手在 +4 补第 4 条）。
- 强化 +4/+8/+12/+16/+20 共 5 次，每次在**已有**词条里等概率挑一条。
- 点数：4 起手 **9 点**、3 起手 **8 点** → 期望 **8.2 点/件**。

### 2.4 数值口径

- **词条值一律取平均值**（`relic_tables.RELIC_ROWS` 第 4 列），于是"一件圣遗物 = 每个属性的**词条次数**整数向量"。
- 满级主词条值见 `MAIN_STAT_VALUE`（五星 +20）。
- **4 件套效果数值不建模**（用户在圣遗物域里自己固定）。

### 2.5 筛选：有效词条 + 接受条件

| 项 | 口径 |
|---|---|
| 「明显有效词条」`E` | **用户给定**，副词条池 10 项里任选 **1~10 项**（攻击型常 4~5，辅助可能 1） |
| 判定时机 | 4 条起手看 **+0** 的 4 条；3 条起手看 **+4** 补出的 4 条 |
| 接受条件 | 这 4 条里属于 `E` 的**条数 ≥ k**（k = 1~4，用户给；**代码里参数名是 `min_effective`**） |
| 未通过 | **直接丢弃**：不投强化、不产出（→ 条件分布，不是混合分布） |
| 通过 | 继续强化到 +20（4 起手再 5 次 / 3 起手再 4 次） |
| 成本 | **只算树脂**；垃圾胚子本身就是强化材料 |

**恒等式（别"优化"掉）**：先抽 3 条再补第 4 条 == 顺序抽 4 条（第 4 次抽样），
所以两种起手**判定时刻的集合分布相同**，差别只在后续强化次数（9 点 vs 8 点）。

### 2.6 置信度（口径）

"n 次机会里，**至少有一件**每个有效维度都 ≥ v"的概率——等价于"逐分量最大值 ≥ v"：

```
q_v = Σ_{w ≥ v} P₁[w]          # 单件（通过筛选后）的支配概率
P[v] = 1 − (1 − q_v)^n         # unit="piece"：n 个胚
     = 1 − [(1−q_v)(1−0.065·q_v)]^n   # unit="run"：n 次副本（每轮 1 或 2 件）
```

- 输出 `{(v1,…,vm): 置信度}`，覆盖单件可能出现的全部 v（**非零分量 ≤ 4**、**分量和 ≤ 9**）。
- **不做**"先按全序选最好再判 v"的口径（用户已明确不要；它 ≤ 上式）。

---

## 3. 数学约定

### 3.1 状态与分布

- 单件状态 `P₁ = {状态向量: 概率}`，概率和必须为 1；状态只保留 `E`（或更宽的 `tracked`）里的词条次数。
- 累积 `S[v] = Σ_{w ≤ v} P₁[w]`（按**全序**）；`q_v = Σ_{w ≥ v} P₁[w]`（按**逐分量支配**）。

### 3.2 N 件最好（口径 B，`best_of_n_states`）

$$
P_N[v] = S[v]^N - \bigl(S[v] - P_1[v]\bigr)^N,
\qquad S[v] = \sum_{w \le v} P_1[w]
$$

**只在全序下成立**：偏序（逐分量）直接套会算出和 ≠ 1。`N→∞` 时概率向最大键处集中。

### 3.3 支配概率（置信度，`tail_confidence`）

`q_v` 是 `P₁` 的逐分量后缀和；`1 − (1−q_v)^n` 是"n 件最大值 ≥ v"的概率。它**不是分布**（求和 ≠ 1）。

### 3.4 两条纪律

- **精度**：`S^n − (S−P)^n` 必须写成 `S^n·(1 − (1−P/S)^n)`；
  `1 − (1−q)^n` 用 `-expm1(n·log1p(-q))`。两个接近 1 的数相减会崩。
- **Jensen**：期望的线性可以用，但 `E[f(X)] ≠ f(E[X])`（暴击封顶、乘区相乘都是非线性的），
  两者必须分开标注。

---

## 4. 代码约定

- **键一律 ASCII**：槽位 `flower/plume/sands/goblet/circlet`；词条键与面板宏同名
  （`crit_rate / crit_dmg / atk_pct / atk_flat / hp_pct / em / er / …`）。中文只进 `*_LABELS`。
- **数值单一来源 = 包内 `relic_tables.RELIC_ROWS`**：经 `_relic_average` 取，不在别处散抄数字。
- **不用 `random`**：所有概率来自解析式或**精确枚举**；要抽样必须单独开函数并显式传种子。
- **纯函数**：不读写全局、不改入参、不打印。
- **有效词条集合由用户给**（`check_effective`，1~10 项），不要写死常量；`DEFAULT_TRACKED` 只是早期默认值。
- **追不追踪 ≠ 不存在**：不在 `E` 里的属性仍**占词条池**，必须通过"入选概率"体现，不能直接丢掉。
- **"最好"必须全序**：① 压标量（`state_scalar`）→ `best_of_n`；② 全序键（`total_state_key`）→ `best_of_n_states`。
  键必须可哈希、全序、对状态**互不相同**（撞键 → `ValueError`，绝不静默合并）。

---

## 5. 接口清单

```python
# ---- 常量 / 换算 ----
RESIN_PER_RUN, EXTRA_DROP_RATE, SET_SHARE, SLOT_SHARE, FOUR_SUB_RATE, UPGRADE_ROLLS
SLOTS, SLOT_LABELS, SUBSTAT_LABELS, SUBSTAT_WEIGHT, SUBSTAT_AVG, POOL_KEYS
MAIN_STAT_PROB, MAIN_STAT_VALUE, DAMAGE_MAINS
pieces_for_resin(resin) -> float
resin_cost(slot, main, off_piece=False, …, slot_share=SLOT_SHARE) -> float
substat_pool(main) -> {key: weight};  substat_inclusion(main);  expected_substat_rolls(main);  expected_substats(main)

# ---- 主词条背包 ----
main_combos() -> [dict];  combo_cost(mains, off_piece_slot=None);  feasible_combos(budget, …)

# ---- 单件分布 ----
piece_states(main, q4=FOUR_SUB_RATE, tracked=DEFAULT_TRACKED) -> {vec: p}
expected_rolls_from_states(states, tracked) -> {key: E[次数]}
state_scalar(vector, tracked) -> float;  total_state_key(vector) -> tuple
best_of_n(states, n, score=state_scalar) -> {score: p}
best_of_n_states(states, n, key=total_state_key) -> {vec: p}     # 全序，和为 1
expected_scalar(dist) -> float

# ---- 筛选（§2.5，参数名 min_effective 即口径里的 k）----
check_effective(effective) -> tuple
start_line_sets(main, q4) -> {(frozenset(4 条), "four"|"three"): p}
effective_lines(lines, effective) -> int
pass_probability(main, effective, min_effective=1, q4=FOUR_SUB_RATE) -> float
filtered_piece_states(main, effective, min_effective=1, q4=FOUR_SUB_RATE, tracked=None) -> {vec: p}
filtered_summary(main, effective, min_effective=1, q4=FOUR_SUB_RATE, tracked=None) -> {"pass_rate", "states", "expected_rolls", …}
resin_per_accepted(slot, main, effective, min_effective=1, off_piece=False, q4=FOUR_SUB_RATE) -> float

# ---- 置信度（§2.6）----
state_lattice(dims, max_points=9, max_lines=4) -> [v, …]
suffix_sum(states, grid=None) -> {v: Σ_{w ≽ v} p[w]}
tail_confidence(main, effective, k, n, q4=FOUR_SUB_RATE, unit="piece", extra_rate=EXTRA_DROP_RATE) -> {v: 置信度}

# ---- 伤害函数（adapter，需要工程）----
STATS_ORDER                                  # 9 项，顺序即 ABI 下标
damage_fn_from_project(project, role) -> GraphDamageFn   # .calc(xs) / .calc_batch(rows)
compile_project(project, role) -> Program    # 见 §10
relic_program.run(program, stats) -> {"noncrit", "crit", "expected"};  run_expected(program, stats)
```

**错误语义**

| 情形 | 行为 |
|---|---|
| 主词条该部位出不了 | `resin_cost` → `inf` |
| 没有胚能通过筛选（`k` 过大） | `pass_probability` → `0.0`；`filtered_piece_states` → `ValueError`；`resin_per_accepted` → `inf` |
| 有效词条集合非法/为空、`k∉1~4`、`n<1`、`unit` 非法、`dims≤0` | `ValueError` |
| 全序键撞键、状态列表非法 | `ValueError` |
| 工程链含不可编译卡片 | `NotCompilable`（调用方回退解释层） |

---

## 6. 测试约定（`tests/test_relic.py` / `test_relic_program.py` / `test_relic_independence.py`）

必须有的"对拍"：

1. 概率和 = 1（单件、N 件、筛选后条件分布）；
2. **枚举期望 = 解析期望**（逐属性，1e-9）——最强的正确性检查；
3. N=2 与暴力枚举取 max 对拍（1e-12）；`P_N[v]` 按 `key` 投影 = `best_of_n`（1e-12）；
4. 概率表合计 100%、权重合计 1100、满级值；
5. 单调性：N↑ 期望不减、q4↑ 更好；`tail_confidence` 对 n↑ / k↑ 不减、对 v↑ 不增；
6. 点数随 q4：8 / 8.2 / 9；
7. 恒等式：两种起手集合分布相同（1e-14）；不筛选（k≤1 且 E=全池）= `piece_states`（1e-14）；
8. 置信度闭式：`1−(1−q)^n` 与 `1−[(1−q)(1−0.065q)]^n`（1e-12）；
9. 独立性：`nodes/damage/expr/graph` 的 import 白名单（静态 AST + 干净解释器）。

跑法：`python -m pytest -q`（仓库根）。提交前必须全绿。

---

## 7. 已知坑

| 坑 | 现象 | 正确做法 |
|---|---|---|
| q4 方向写反 | 期望点数算成 8.8 | `q4` = **4 词条起手**概率（副本 0.2） |
| 入选概率用 `4w/W` 近似 | 暴击率期望 0.615（真值 0.673） | `substat_inclusion()` 精确枚举 |
| 偏序直接套 `P_N` | 概率和 ≠ 1 | 先压标量或给全序键 |
| `S^n − (S−P)^n` 直接算 | 大 n 精度崩 | 改写成 `S^n·(1−(1−P/S)^n)`，用 `expm1/log1p` |
| 只看追踪属性算点数 | 合计只有 3.x 点 | 数总点数时 `tracked` 传全部 10 条 |
| 忘了部位的 1/5 | 成本偏小 5 倍（沙·攻击% 算成 141，真值 704） | `resin_cost` 乘 `SLOT_SHARE` |
| 把"最好的那件"当逐分量最大值 | 两种口径混用，结果偏小 | 置信度只用支配口径（§2.6） |
| 用 PowerShell 改写含中文的源码 | mojibake / U+E18C 语法错 | 用编辑工具，别用 `Set-Content` |

---

## 8. 进度

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1 | 常量与换算层（件数 / 主词条成本 / 副词条期望） | ✅ `bb02ac7` |
| 2 | 主词条背包（420 组合 × 5 散件槽，按成本筛） | ✅ `ae9af38` |
| 3 | 单槽模型（P₁ → S → N 件最好的通式） | ✅ `e378f6b` |
| 3.5 | 向量状态的 best-of-N（口径 B） | ✅ `dce03e4` |
| 3.6 | 筛选模型（有效词条 + 接受条件 + 条件分布 + 树脂） | ✅ `a8469de` |
| 3.7 | 置信度分布（逐分量后缀和，`unit=piece/run`） | ✅ `cba2d52` |
| 3.8 | 独立化（包内副本 + adapter 分层） | ✅ `7363e6f` `cbc027c` |
| 4 | 把"最好"的标量换成**真实伤害** | ⬜ 待做（接 adapter） |
| 5 | 5 槽联合（4 套装 + 1 散件）+ 预算约束最优 | ⬜ 待做 |
| 6 | 有效词条由伤害链 ΔD 自动判定 + 输出分布 | ⬜ 待做 |

---

## 9. 提交约定

- 一功能一提交，前缀 `feat(relic):` / `fix(relic):` / `refactor(relic):` / `docs(relic):` / `perf(relic):`。
- 只改 `GIRelic/*.py` + `tests/` 时不需要重建前端；一旦碰 `web/` 或 `nodes.py` 的 schema，按根 `AGENTS.md` §6 重建。
- **不自动 `git push`**；分支 `relic`，不要提交到 `main`。

---

## 10. 计划：通用 DLL

目标：模拟/DP 要调伤害链几十万~几百万次，Python 图求值太慢。
做法：把某工程的伤害链抽象成**纯数值函数**，编译成通用 DLL，用 `ctypes` 调用。

### 10.1 分层

| 层 | 内容 |
|---|---|
| 抽象层 | `DamageFn = Callable[[Sequence[float]], float]` + 固定 `stats_order` |
| 解释层 | `GraphDamageFn`（等价但慢，回退与对拍基准） |
| 函数表示 | `compile_project` → `{"role", "stats_order", "stages": [...]}`（可 JSON，可哈希做指纹） |
| 编译层 | 由程序生成 C（只含算术）→ MinGW `gcc -O3 -shared` → 缓存到 `build/dll/` |
| 调用层 | `ctypes`；批量接口一次算 N 组 |
| 回退 | 无 gcc / 编译失败 / 指纹不符 → 解释层，结果必须一致 |

### 10.2 程序形状（已实现）

```python
Program = {"role": str, "stats_order": (9 项), "stages": [Stage, ...]}
Stage  = {"op": "base"|"mul"|"res", "expr": RPN}
       | {"op": "def",  "exprs": [RPN, RPN, RPN, RPN]}     # 角色等级/敌人等级/减防%/无视防御%
       | {"op": "crit", "rate": RPN, "cd": RPN}            # 当场重算三元组
       | {"op": "add",  "branches": [[Stage, ...], ...]}   # 替换为各分支之和
       | {"op": "result"}
RPN    = [("const", float) | ("stat", int) | (add|sub|mul|div|neg|min|max|pow,)]
```

目前只编译 `base/dmg/res/def/crit/add/result`；反应/星月/擢升/外部域/矩阵 → `NotCompilable` 回退。
拐力等外部量在 `compile_project` 里**常量折叠**（取不注入圣遗物时的基线值）。

### 10.3 输入向量（9 项，下标即 ABI）

| # | 宏 | 中文 | 单位 | # | 宏 | 中文 | 单位 |
|---|---|---|---|---|---|---|---|
| 0 | `atk_pct` | 攻击% | 百分数 | 5 | `def_flat` | 小防御 | 绝对值 |
| 1 | `atk_flat` | 小攻击 | 绝对值 | 6 | `em` | 元素精通 | 绝对值 |
| 2 | `hp_pct` | 生命% | 百分数 | 7 | `crit_rate` | 暴击率 | 百分数 |
| 3 | `hp_flat` | 小生命 | 绝对值 | 8 | `crit_dmg` | 暴击伤害 | 百分数 |
| 4 | `def_pct` | 防御% | 百分数 | | | | |

- **`er` 不在里面**：不进伤害公式，只在词条池里占权重；
- 主词条另算（`dmg` / 冠的双爆 / 沙杯的攻击%·精通），不混进这 9 项；
- 完整工程求值（20 个面板宏）仍由 `Graph.evaluate` 负责，两者不混用。

### 10.4 硬性约定

- 生成 C 必须**白名单**：只允许数字、四则、括号、已知变量名；绝不把用户原始字符串拼进 C。
- 等价性：DLL vs 解释层相对误差 < 1e-9（pytest 守住）。
- 指纹 = 工程 JSON + 属性顺序 + gcc 版本；变了重新编译。
- **DLL 与生成的 `.c` 都不进 git**，输出目录固定 `build/dll/`（`build/` 已 gitignore）；不用 `private/` 放产物。
- 只在圣遗物模拟/DP 用 DLL，**不改变 `/api/evaluate` 的求值路径**。

### 10.5 参考数字（沙·攻击% 主词条，目标套，`E = (crit_rate, crit_dmg, atk_flat)`）

| k | 通过率 | 期望树脂/件 |
|---|---|---|
| 1 | 85.2% | 826 |
| 2 | 33.4% | 2 107 |
| 3 | 3.0% | 23 728 |
| 4 | 0（E 只有 3 项） | inf |

不筛选基线 = `20 / (1.065 × 0.5 × 1/5 × 0.26665)` ≈ **704** 树脂/件。
`E` 定义越宽 → 通过率越高但"有效"越松；`k` 按流派给。

规模参考：`|E|=5` → `state_lattice` 1876 格点、`tail_confidence` ≈ 0.03 s；`|E|=10` → 38 251 格点、≈ 0.2 s。
