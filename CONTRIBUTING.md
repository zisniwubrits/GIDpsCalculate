# 协作与开发约定

> 这份文件是给**开发者 / AI 助手**看的项目约定，请优先遵守。

## 1. 一功能一提交（重要）

**每新增或修改一个功能，单独产生一个 git 提交**，便于用 git 精确回滚某一个功能。

```bash
python -m unittest test_damage -v      # 提交前必须通过
git add -A
git commit -m "feat: 简述这个功能"
```

- 提交信息前缀约定：`feat:` 功能 / `fix:` 修 bug / `perf:` 性能 / `refactor:` 重构 / `docs:` 文档 / `chore:` 杂项。
- **一个提交只做一件事**：不要把两个不相关的功能塞进同一个提交。
- 需要撤销某个功能时用 `git revert <commit>`（保留历史）；本地未推送时才考虑 `git reset --hard <commit>~1`。

## 2. 推送由用户手动执行

不要自动 `git push`。改完只做本地提交，推送由仓库所有者自行决定。

## 3. 目录职责

| 路径 | 职责 |
|---|---|
| `genshin_dmg/damage.py` | 伤害计算核心，**纯函数、不依赖 UI**，改动必须配单元测试 |
| `genshin_dmg/nodeboard.py` | 乘区节点编辑器（画布 / 卡片 / 连线 / 工程存取） |
| `genshin_dmg/gui.py` | 主窗口、底部按钮、F1 教程文本 |
| `test_damage.py` | 公式单元测试（`python -m unittest test_damage`） |
| `main.py` | 启动入口 |
| `private/` | 个人存档与笔记，**已被 .gitignore 忽略，不要提交** |

## 4. 代码约定

- 数值输入框一律走 `_num()` / `_pct()`：**支持算式（`70+30`、`200*3`）与变量名**，不要直接用 `float()`。
- 数值展示统一用 `_fmt()`（两侧一致），**不要出现科学计数法**。
- 卡片的显示值 = 「本卡系数 ｜ 输出」；三元组（未暴击 / 暴击 / 期望）仅在数值不同时全部展示。
- 有效暴击率封顶 100%。
- 新增卡片类型：在 `NODE_TYPES` 注册（含 `inputs` / `compute` / 可选 `factor`），需要出现在左侧菜单时同步加进 `PALETTE`。
- 改动画布结构（节点、连线、尺寸、缩放）时，记得同步 `to_dict()` / `from_dict()`，保证工程 JSON 可往返。

## 5. 公式来源

- 通用伤害：<https://ellen.rth1.xyz/原神产球及附着/index.html>
- 月 / 星等进阶：<https://yuhuazhe.cn/zlk/gongshi.html>
- 两处跨源差异（已在代码注释中标注）：激化 EM 分母 ellen `+1200` vs 羽化哲 `+2000`；扩散倍率 `0.6` vs `0.65`。
