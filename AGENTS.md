# 协作与开发约定

> 这份文件是给**开发者 / AI 助手**看的项目约定，请优先遵守。
> （`CONTRIBUTING.md` 指向本文件，避免两处重复维护。）

## 0. 项目形态（重要）

- **Web 应用**：后端 Python + FastAPI（公式与图求值），前端 Vite + React + TypeScript + React Flow（界面）。
- **公式只在 Python 一份**：前端**不做任何伤害计算**，只把整张图 POST 给 `/api/evaluate`，渲染后端返回的文案与数值。
- 卡片类型、字段、菜单、预设、参考表都由后端 `/api/schema` 提供（单一数据源 = `genshin_dmg/nodes.py`）。
- 旧版 **tkinter 桌面版**完整保留在 `tkinter` 分支（tag `tkinter-final`）；`main` 上不再有 tkinter 代码。

## 1. 一功能一提交（重要）

**每新增或修改一个功能，单独产生一个 git 提交**，便于用 git 精确回滚某一个功能。

```bash
python -m pytest -q                    # 后端测试（公式 / 图求值 / 接口）
cd web && pnpm test && pnpm typecheck  # 前端测试 + 类型检查
git add -A
git commit -m "feat: 简述这个功能"
```

- 提交信息前缀约定：`feat:` 功能 / `fix:` 修 bug / `perf:` 性能 / `refactor:` 重构 / `docs:` 文档 / `chore:` 杂项。
- **一个提交只做一件事**：不要把两个不相关的功能塞进同一个提交。
- 需要撤销某个功能时用 `git revert <commit>`（保留历史）；本地未推送时才考虑 `git reset --hard <commit>~1`。

## 2. 推送与打包由用户手动执行

- 不要自动 `git push`；只做本地提交。
- 不要自动构建 exe / 打包；用户明确要求时才做。

## 3. 目录职责

| 路径 | 职责 |
|---|---|
| `genshin_dmg/damage.py` | 伤害公式，**纯函数、不依赖 UI**，改动必须配单元测试 |
| `genshin_dmg/expr.py` | 输入框解析（算式 / 变量 / 全角符号）与数值格式化 |
| `genshin_dmg/nodes.py` | 卡片类型注册表；**前端 schema 的唯一来源** |
| `genshin_dmg/graph.py` | 节点图模型与求值（变量两轮解析、环路检测、工程 JSON 往返） |
| `genshin_dmg/report.py` | 文本报告（导出结果） |
| `genshin_dmg/tutorial.py` | F1 教程文案（后端提供文本，前端只渲染） |
| `server/app.py` | FastAPI 接口 + 生产环境静态托管 `web/dist` |
| `web/src/App.tsx` | 前端主界面（画布、工具栏、侧栏、撤销重做、工程读写） |
| `web/src/model.ts` | 画布模型纯函数（落位、对齐、预设、JSON 往返）——业务规则放这里，方便单测 |
| `web/src/components/` | 卡片、连线、表格、右键菜单、弹窗、侧栏、工具栏 |
| `web/src/state/` | 撤销重做、后端请求、localStorage 持久化 |
| `test_damage.py` / `test_graph.py` / `test_server.py` | 后端测试（`python -m pytest`） |
| `web/src/**/*.test.ts(x)` | 前端测试（`pnpm test`） |
| `private/` | 个人存档与笔记，**已被 .gitignore 忽略，不要提交** |

## 4. 代码约定

### 后端（Python）

- 字段取值一律走 `genshin_dmg/nodes.py` 里的 `_num()` / `_pct()` / `_expr()`：
  **支持算式（`70+30`、`200*3`）与变量名**，且会读到当前求值上下文的变量表（contextvar）。
  不要直接用 `float()`，也不要用模块全局存变量表（会污染并发请求）。
- 数值展示统一 `fmt_num()`（带千分位、**不出现科学计数法**）；复制用 `plain_num()`（纯数字）。
- 有效暴击率封顶 100%。
- **新增卡片类型**：只在 `genshin_dmg/nodes.py` 的 `NODE_TYPES` 里注册
  （`inputs` / `fields` / `compute` / 可选 `factor`），`schema()` 会自动把它给到前端，
  前端菜单与卡片渲染**无需改动**。同时补 `test_graph.py` 用例。
- 改动画布结构（节点、连线、尺寸、缩放、字段）时，必须同步
  `Graph.to_dict()` / `Graph.from_dict()`，保证工程 JSON 可往返（且与旧 tkinter 工程兼容）。
- 变量求值顺序不要随意改：①变量卡片定义 → ②结果卡片三元组 → ③变量卡片再解析一轮（可引用结果变量，同名以结果卡片为准）。

### 前端（TypeScript / React）

- **卡片外观与字段由 `/api/schema` 驱动**：不要在 TS 里硬编码卡片类型、字段名或中文标签。
- 数值字段值**保持字符串**（要支持算式与变量），不要 `parseFloat` 后回写。
- 位置 / 尺寸 / 选中态属于界面状态：**不要进入 `/api/evaluate` 的载荷**（否则拖卡片会一直重算）。
- 计算相关规则写进 `src/model.ts` 这类纯函数文件并配单测；组件里只做渲染与事件转发。
- 改了界面后跑 `pnpm test` + `pnpm typecheck`。
- 测试夹具 `web/src/test/schema.fixture.json` 由后端生成；**后端 schema 变更后重新生成**：

  ```bash
  python -c "import json,io;from genshin_dmg import nodes;io.open('web/src/test/schema.fixture.json','w',encoding='utf-8',newline='\n').write(json.dumps(nodes.schema(),ensure_ascii=False,indent=2)+'\n')"
  ```

- 前端测试环境补丁集中在 `web/src/test/setup.ts`（jsdom 缺 ResizeObserver / 尺寸 / 剪贴板），
  以及 `web/src/test/d3-drag-stub.ts`（d3-drag 在 jsdom 下会抛异常），改动请留意注释里的原因。

## 5. 运行与端口

- 后端默认 **127.0.0.1:8777**（8000 常被本机其它项目占用，别改回去），`--port` 可改。
- 前端开发服务器 5173，Vite 已把 `/api` 代理到 8777；后端换端口时用环境变量：
  PowerShell `$env:DSH_API="http://127.0.0.1:9000"; pnpm dev`。
- 生产：`cd web && pnpm build` → `web/dist`，由 `python main.py` 直接托管。

## 6. 公式来源

- 通用伤害：<https://ellen.rth1.xyz/原神产球及附着/index.html>
- 月 / 星等进阶：<https://yuhuazhe.cn/zlk/gongshi.html>
- 两处跨源差异（已在代码注释中标注）：激化 EM 分母 ellen `+1200` vs 羽化哲 `+2000`；扩散倍率 `0.6` vs `0.65`。
