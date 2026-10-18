# 协作与开发约定

> 这份文件是给**开发者 / AI 助手**看的项目约定，请优先遵守。
> （`CONTRIBUTING.md` 指向本文件，避免两处重复维护。）

## 0. 项目形态（重要）

- **Web 应用**：后端 Python + FastAPI（公式与图求值），前端 Vite + React + TypeScript + React Flow（界面）。
- **公式只在 Python 一份**：前端**不做任何伤害计算**，只把整张图 POST 给 `/api/evaluate`，渲染后端返回的文案与数值。
- 卡片类型、字段、菜单、预设、参考表都由后端 `/api/schema` 提供（单一数据源 = `genshin_dmg/nodes.py`）；
  schema 里还给 `panelMacros`（角色面板宏名，前端拿它做输入框高亮）。
- **画布 = 卡片 + 连线**，卡片可以按位置归属于某个「角色」命名空间（前端推导，见 §5 前端）。
- 三类"跨卡片/跨文件"能力，语义各自独立，**不要混用**：
  | 能力 | 作用范围 | 实现 |
  |---|---|---|
  | 「变量」/「赋值变量」卡 | 单文件内 | `graph.py` 求值顺序 |
  | 「外部域」卡 | 跨文件：读另一个工程某域的 `out::` | `genshin_dmg/external.py` |
  | 「域对照表」卡 | 跨文件成批：行×列×固定拐力直接给出矩阵 | `genshin_dmg/matrix.py` |
- 旧版 **tkinter 桌面版**完整保留在 `tkinter` 分支（tag `tkinter-final`）；`main` 上不再有 tkinter 代码。

## 1. 需求不清先问清楚，再动手（重要）

**拿到需求先判断是否足够明确**（对象、期望效果、边界、优先级）。不清楚就先问，不要猜着改。

- **能自己查证的先查证**：读代码、跑一次、看现状，把「查不出来的部分」整理成问题；
  不要用提问代替调查，也不要在没看代码的情况下问显而易见的事。
- **提问要给具体选项**（含推荐项），并说明现状与你怀疑的原因，让用户一眼能选；
  不要空泛地问「你想要什么效果」。
- **含糊时宁可不写代码**：宁可多问一轮，也不要改完再回滚（回滚要占一个 `revert` 提交）。
- 需求自相矛盾、或与既有约定冲突时（例如与本文档某条冲突），**停下来指出并确认**，不要自行选一边。
- 涉及外观/手感的主观要求（间距、大小、颜色），先问清「指哪一层、期望成什么样」，
  最好给出几个可选方案让用户挑。
- 问完把结论落到提交信息或代码注释里，方便以后回溯「为什么这么做」。

### 1.1 一轮做完：不要把已批准的工作推到下一轮（重要）

需求已经明确、方案已经确认之后，**必须在同一个回合里把整件事做完**：
改代码 → 跑测试 → 提交，一次交付完。

- **禁止**用这些话收尾：「要我下一轮把 X 做完吗？」「回『继续』即可」
  「需要我接着做 Y 吗？」——计划已批准时这些都属于把一件事切成两半，
  白白浪费用户一次往返。用户已经说过的方向不需要再征求同意。
- **只有这三种情况才停下来问**：
  1. 出现真正的分叉需要用户选（方案 A / B 各有取舍）；
  2. 被外部条件阻塞（缺依赖、没有测试环境、必须用户本人操作）；
  3. 触及约定冲突或破坏性操作（`reset --hard`、删分支、推远端、改公式口径）。
- **回合内确实做不完时**（上下文或步数上限）：不要伪装成「征求同意」，
  直接说明「已完成 X，剩余 Y 没做的原因 Z」，给出可执行的下一步，
  而不是一句「回继续即可」把球踢回去。
- **汇报要干净**：不要每轮重复「本地领先远端 N 个提交 / 未推送」这类状态播报，
  推送本来就由用户负责（见第 3 节）；只在状态**影响用户决策**时才提。

## 2. 一功能一提交（重要）

**每新增或修改一个功能，单独产生一个 git 提交**，便于用 git 精确回滚某一个功能。

```bash
python -m pytest -q                    # 后端测试（全部在 tests/ 里）
cd web && pnpm test && pnpm typecheck  # 前端测试 + 类型检查
git add -A
git commit -m "feat: 简述这个功能"
```

- 提交信息前缀约定：`feat:` 功能 / `fix:` 修 bug / `perf:` 性能 / `refactor:` 重构 / `docs:` 文档 / `chore:` 杂项。
- **一个提交只做一件事**：不要把两个不相关的功能塞进同一个提交。
- 需要撤销某个功能时用 `git revert <commit>`（保留历史）；本地未推送时才考虑 `git reset --hard <commit>~1`。
- 改了 `web/` 的内容，提交前记得 `pnpm build`（见 §6），否则别人拿到的是旧界面。

## 3. 推送与打包

- **不要自动 `git push`（不推云端）**：改完只做本地提交，推送完全由仓库所有者自己决定。
  需要回滚时用本地 `git reset` / `git revert`，不要用推送去改远端。
- `backup-v0.0` 分支里是个人存档，**任何情况下都不要推送**。
- 不要自动构建 exe / 打包：仓库根有 `GenshinDamageCalc.spec`（PyInstaller），
  但**只有用户明确要求时才用**。

## 4. 目录职责

| 路径 | 职责 |
|---|---|
| `genshin_dmg/damage.py` | 伤害公式，**纯函数、不依赖 UI**，改动必须配单元测试 |
| `genshin_dmg/expr.py` | 输入框解析（算式 / 变量 / 全角符号）与数值格式化 |
| `genshin_dmg/nodes.py` | 卡片类型注册表；**前端 schema 的唯一来源**（含 `panelMacros`） |
| `genshin_dmg/graph.py` | 节点图模型与求值（变量多轮解析、角色命名空间、拐力、环路检测、工程 JSON 往返） |
| `genshin_dmg/external.py` | 「外部域」：跨文件读另一个工程某域的 `out::`；路径多基准、只读、防环、mtime 缓存、补全候选 |
| `genshin_dmg/matrix.py` | 「域对照表」：行=工程文件、列=拐力来源文件、左上角=固定拐力，逐格求值 |
| `genshin_dmg/report.py` | 文本报告（导出结果） |
| `genshin_dmg/tutorial.py` | F1 教程文案（后端提供文本，前端只渲染） |
| `server/app.py` | FastAPI 接口 + 生产环境静态托管 `web/dist`（index.html no-cache、assets 长缓存） |
| `server/storage.py` | 工程落盘：记忆目录/记忆文件、`save_target`（写回原文件）、工程名清洗 |
| `server/dialogs.py` | 本机原生文件对话框（子进程弹 tkinter） |
| `server/build_check.py` | 前端产物是否过期（启动器 / main.py / /api/health 共用） |
| `web/src/App.tsx` | 前端主界面（画布、工具栏、侧栏、撤销重做、工程读写、快捷键） |
| `web/src/model.ts` | 画布模型纯函数（落位、对齐、预设、JSON 往返、拐力箭头判定、来源行编辑、关键字高亮）——业务规则放这里，方便单测 |
| `web/src/api.ts` | 全部后端调用（含 `suggestExternal`、`cellPanel`） |
| `web/src/types.ts` | 全部类型定义（先读它再看逻辑） |
| `web/src/components/` | 见下方"组件分层" |
| `web/src/state/` | 撤销重做、后端请求（防抖/丢弃过期响应）、localStorage 持久化 |
| `web/public/` | 静态资源（目前是 `favicon.svg`），**构建时原样复制到 `dist/` 根**；改它也要 build |
| `tests/` | **后端测试全都在这里**：`test_damage` / `test_graph` / `test_role_namespace` / `test_matrix` / `test_server` / `test_storage` / `test_save_target` / `test_build_check` / `test_launcher`；`tests/conftest.py` 把仓库根补进 `sys.path`，所以在仓库根或 `tests/` 里跑都行 |
| `tests/test_*.py` | 后端与启动器测试（`python -m pytest`），一个模块一个文件 |
| `web/src/**/*.test.ts(x)` | 前端测试（`pnpm test`） |
| `private/` | 个人存档与笔记，**已被 .gitignore 忽略，不要提交** |

**组件分层（`web/src/components/`）**：同一类输入必须复用同一个组件，不要各写一套。

| 组件 | 用在哪 | 关键约束 |
|---|---|---|
| `CodeInput` | 数值 / 百分比 / 单行文本字段 | 透明 input 叠在带色副本上；`value` 是唯一真相 |
| `CodeField` | 多行定义区（「变量」卡） | 滚动/字体/内边距/换行必须与 textarea 完全一致，否则高亮错位 |
| `ExternalSources` + `SourceInput` | 「外部域」的来源列表 | 一行一个单行框；回车加行、空行退格删行；补全用小弹窗 |
| `MatrixEditor` (+ `MatrixPanelDialog`) | 「域对照表」卡 | 行/列/固定拐力直接在表格里选；单元格右键面板只读 |
| `PanelParts` | 角色面板弹窗 **与** 矩阵单元格面板 | 两处外观必须**一模一样**，公共零件只在这里实现 |
| `CanvasWatermark` | 画布水印 | 纯装饰：`z-index:-2`、`pointer-events:none`，不得影响拖动/框选/连线 |
| `ErrorBoundary` | 包住整个应用（`main.tsx`） | 渲染期异常显示可读错误卡片，**不能白屏** |
| `CardNode` / `CardEdge` | 卡片与连线本体 | 端口是卡片组件的兄弟节点（测试里从 `parentElement` 找） |

## 5. 代码约定

### 后端（Python）

- 字段取值一律走 `genshin_dmg/nodes.py` 里的 `_num()` / `_pct()` / `_expr()`：
  **支持算式（`70+30`、`200*3`）与变量名**，且会读到当前求值上下文的变量表（contextvar）。
  不要直接用 `float()`，也不要用模块全局存变量表（会污染并发请求）。
- 数值展示统一 `fmt_num()`（带千分位、**不出现科学计数法**）；复制用 `plain_num()`（纯数字）。
- 有效暴击率封顶 100%。
- **新增卡片类型**：只在 `genshin_dmg/nodes.py` 的 `NODE_TYPES` 里注册。
  可用键：`title` / `label` / `group`（菜单分组：直伤乘区 / 反应源 / 星月部件 / 域 / 变量 / 工具）/
  `inputs` / `fields` / `compute` / `factor` / `table` / `hidden_fields` / `bare` /
  `external_domain` / `no_output` / `resizable` / `wide_fields`。
  注册后 `schema()` 会自动给到前端，前端菜单与卡片渲染**无需改动**。同时补 `tests/test_graph.py` 用例。
- 改动画布结构（节点、连线、尺寸、缩放、字段）时，必须同步
  `Graph.to_dict()` / `Graph.from_dict()`，保证工程 JSON 可往返（且与旧 tkinter 工程兼容）。
  **工程 JSON 不存卡片的 `role`**（角色归属由前端按位置推导，只在求值载荷里出现）。
- 变量求值顺序不要随意改（完整顺序与理由见 `genshin_dmg/graph.py` 的 `Graph.evaluate` docstring，
  两处必须保持一致）：①「变量」卡片定义 → ②「★结果」卡片三元组 → ③「赋值变量」卡片（显式连线赋值）
  → ④「变量」卡片再解析一轮（可引用 ②③，`locked` 保护）→ ⑤「角色 / 武器」卡片的面板宏（`角色::宏`）
  → ⑥ 拐力与生效值（`own:: / out:: / in::` 子命名空间）→ ⑦ 补算引用了 `in:: / own::` 的定义
  → ⑧ 逐节点求值。
  同名优先级：赋值变量卡 > ★结果卡三元组 > 变量卡片；**角色面板宏覆盖同名全局变量**。
  拐力来源取「拐力生效前」的自身值快照，所以拐力不会顺着拐力传递；
  带角色归属的「★结果 / 赋值变量」卡片登记进该角色的命名空间（`角色::名字`）。

**「外部域」（`external.py`）的规则**：

- **只读**：只读被引用文件，绝不改写它。
- **只读显式声明**：只取那个域里显式写过的 `out::名字 = 值`；面板里的普通项不对外给出。
- 取的是对方**求值之后**的 `out::`（对方文件内部的拐力已经算进去了）。
- **路径**：绝对路径直接用；相对路径按「当前工程目录 → 它的上一级 → 后端记住的目录」依次试，
  自动补 `.json`，支持 `~/`；**不去子目录里猜同名文件**（会有歧义 —— 用户口径：要读子目录就把目录写出来）。
- **防环**：文件互相引用时"切断再往下读"，被切断的那次结果不进缓存；按 mtime 缓存，敲键盘不反复读盘。
- **补全**：`suggest_paths` / `suggest_domains` 只列候选，**不替用户做决定**；目录补成 `名字/`。
- `Graph.skip_external` 是**防环开关**：文件互相引用时由 `external.py` 把它置真以停止继续往外读，
  但本文件**自己的** `out::` 仍照常求值（不会因为环就变 0），被切断的那次也不进缓存。

**「域对照表」（`matrix.py`）的规则**：

- 行 = 一个工程文件（该文件**只有一个域**，且域内有「★结果」卡）；列 = 一个作拐力来源的文件；
  左上角 = 固定拐力（对**所有**组合都加一次）；单元格 = 行角色在「该列 `out::` + 固定域 `out::`」下的期望伤害。
- 实现是"把行文件读进来求值，再用 `Graph.extra_buffs` 把列 + 固定域的 `out::` 注入行角色"；
  拐力只作用于**直接目标**，不会顺着行文件内部的箭头继续传。
- `POST /api/matrix/cell` 返回单个单元格的角色面板（**只读**，样式与角色面板一致）。

**保存目标（`storage.save_target`）**：

- 记住的那个文件里**工程名与当前工程名一致** → 写回**原文件**（保留原文件名）；
- 否则按工程名在记忆目录生成 `<工程名>.json`（改名 / 新工程的行为）。
- 由 `tests/test_save_target.py` 守住，改动 `project_file` / `remember_path` 时一起跑。

### 前端（TypeScript / React）

- **界面里不要堆长提示（重要）**：除非用户明确要求，**操作界面里不显示过长的操作说明**。
  弹窗只留「标题 + 输入框 / 表格 + 按钮」；「这个字段怎么用」「名字可以怎么引用」
  这类解释一律放 **F1 教程**（`genshin_dmg/tutorial.py`），不要塞进弹窗或卡片里。
  输入框的 `placeholder` 也不写「例如 火神 / 主C」这种示例，留空即可。
  状态反馈优先靠界面自身（按钮高亮、红字错误、图标），**不要为了"说一遍"再弹一条 toast**。
  违反这条会被要求整体删掉（历史上「角色面板」「设置角色名」「命名卡片」「设置结果变量」
  「新建项目」的说明段落与示例都被这样删过）。**只有**这两类短文字该留：
  ①当场校验的错误（重名、格式非法、压到别的区域）；②不可逆操作的后果（删除 / 清空）。
- **卡片外观与字段由 `/api/schema` 驱动**：不要在 TS 里硬编码卡片类型、字段名或中文标签。
- 数值字段值**保持字符串**（要支持算式与变量），不要 `parseFloat` 后回写。
- 位置 / 尺寸 / 选中 / 折叠属于界面状态：**不要进入 `/api/evaluate` 的载荷**（否则拖卡片会一直重算）。
  **例外**：`role`（角色归属，由前端按位置推导）**必须进载荷** —— 后端靠它把字段读进对应命名空间；
  但工程 JSON 不存它（见 §5 后端）。
- **关键字高亮**：`highlightTokens(text, macros)` 在 `model.ts`；关键字固定 `own` / `out` / `in`，
  宏名来自 `schema.panelMacros`。匹配规则：长名优先（`atk_pct` 先于 `atk`）、
  前后不能紧贴标识符字符（不能把 `atk_pct` 里的 `atk` 切出来）。新增关键字请改这一处，别在组件里各写正则。
- **补全一律走后端**（`/api/external/suggest`）：前端不自己扫目录；**不用 `datalist`**
  （候选是异步来的，浏览器不会刷新已弹出的原生下拉），用小弹窗按输入框定位。
- 计算相关规则写进 `src/model.ts` 这类纯函数文件并配单测；组件里只做渲染与事件转发。
- 改了界面后跑 `pnpm test` + `pnpm typecheck`。
- **渲染不能白屏**：新面板/新弹窗要确保异常被 `ErrorBoundary` 接住（历史白屏事故：旧后端没有
  `schema.panelMacros`，角色面板弹窗直接崩，整页空白）。
- 测试夹具 `web/src/test/schema.fixture.json` 由后端生成；**后端 schema 变更后重新生成**：

  ```bash
  python -c "import json,io;from genshin_dmg import nodes;io.open('web/src/test/schema.fixture.json','w',encoding='utf-8',newline='\n').write(json.dumps(nodes.schema(),ensure_ascii=False,indent=2)+'\n')"
  ```

- 前端测试环境补丁集中在 `web/src/test/setup.ts`（jsdom 缺 ResizeObserver / 尺寸 / 剪贴板），
  以及 `web/src/test/d3-drag-stub.ts`（d3-drag 在 jsdom 下会抛异常），改动请留意注释里的原因。

## 6. 运行与端口

- 后端默认 **127.0.0.1:8777**（8000 常被本机其它项目占用，别改回去），`--port` 可改。
- 前端开发服务器 5173，Vite 已把 `/api` 代理到 8777；后端换端口时用环境变量：
  PowerShell `$env:DSH_API="http://127.0.0.1:9000"; pnpm dev`。
- 生产：`cd web && pnpm build` → `web/dist`，由 `python main.py` 直接托管（`web/public/` 里的文件会原样进 `dist/`）。

**接口清单**（改接口时同步这里）：

| 接口 | 作用 |
|---|---|
| `GET /api/health` | 健康检查 + 前端产物是否过期 |
| `GET /api/schema` | 卡片 / 菜单 / 预设 / 参考表 / `panelMacros` |
| `GET /api/help` | F1 教程文本 |
| `GET /api/external/suggest` | 「外部域」路径 / 域名补全候选 |
| `POST /api/evaluate` | 整张图求值 |
| `POST /api/report` | 生成报告并落盘 |
| `GET /api/storage` | 当前工程目录 |
| `POST /api/save/project` | 一键保存（`save_target` 决定写哪个文件） |
| `POST /api/open` | 本机原生对话框打开工程并记住目录 |
| `POST /api/matrix/cell` | 「域对照表」单个单元格的角色面板（只读） |

### 前端产物必须重建（很容易踩的坑）

**改了 `web/` 下任何东西（含 `web/public/`），都要 `pnpm build`**；否则后端继续把**旧界面**发给浏览器：
接口全部正常、功能却缺失（新按钮/新面板不出现），因为没有报错而极难发现。

判定逻辑只有一份，在 `server/build_check.py`：`web/dist/index.html` 不存在，
或**比前端源码最新修改时间旧**（监视 `web/src` 全部文件 + `index.html` /
`package.json` / `vite.config.ts` / `tsconfig.json` / 锁文件）就算过期。三处共用：

| 位置 | 行为 |
|---|---|
| `launcher.bat` | 过期就**自动重建**（不再只看 dist 是否存在） |
| `python main.py` | 启动时在终端打印警告与修复命令 |
| `GET /api/health` | 返回 `webStale` / `webBuildTime` / `webSourceTime`，前端工具栏显示「⚠ 前端产物过期」 |

另外 `index.html` 一律以 `Cache-Control: no-cache` 提供（入口不能缓存，否则重建后
浏览器仍会加载旧 bundle）；`/assets/*` 文件名带内容 hash，长缓存 + `immutable`。

自检：`python -m server.build_check`（退出码 0 = 最新，1 = 需要重建）。

### 启动器（`launcher.bat`）：必须纯 ASCII，界面文案用英文

cmd.exe 按「读文件那一刻的控制台代码页」解析批处理。中文 Windows 双击时是 936(ANSI)，
文件里只要出现非 ASCII（中文）字节就会解析错位 —— `echo ` 前缀被上一行吃掉，
菜单行被当成命令执行：`'[4]' is not recognized as an internal or external command`。

实测（同内容只改编码，各跑 3 次）：起始代码页 936 时 UTF-8 中文版 **3/3 报错**，纯 ASCII 版 **0/3**。

因此：

- 文件**只含 ASCII**（`rem` 注释、`echo` 文案全部英文），行尾 **CRLF**，无 BOM；
- 不要加 `chcp`（会改掉用户控制台代码页，纯 ASCII 下没有必要）；
- 中文本地化留给 README 与网页界面，命令行只保留英文。

`tests/test_launcher.py` 会守住这些约束（纯 ASCII / CRLF / 无 BOM / 无 chcp / 包管理器顺序 / 默认端口与 main.py 一致）。

## 7. 公式来源

- 通用伤害：<https://ellen.rth1.xyz/原神产球及附着/index.html>
- 月 / 星等进阶：<https://yuhuazhe.cn/zlk/gongshi.html>
- 两处跨源差异：
  - **激化精通项已定为 `5×EM/(EM+1200)`**（ellen 口径，用户已确认，勿改成 +2000）；由 `tests/test_damage.py::test_mastery_term_is_1200` 锁定。
    手动搭激化链时「精通增益」卡片填 k=5 / 分母=1200；星月与剧变仍用 +2000。
  - 扩散倍率 ellen `0.6` vs 羽化哲 `0.65`：当前沿用 `0.6`。
- 「外部域」与「域对照表」**不引入新公式**：它们只是把别处算好的 `out::` 相加/注入，
  真正的伤害仍由 `damage.py` 计算。改这两处的行为时，别顺手改公式口径。
