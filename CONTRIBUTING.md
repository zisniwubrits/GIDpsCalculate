# 参与贡献

项目的协作与开发约定统一写在 **[AGENTS.md](AGENTS.md)**（一功能一提交、提交信息前缀、不自动推送、目录职责、后端/前端代码约定、运行与端口、公式来源）。

提交前请至少跑通：

```bash
python -m pytest -q                     # 后端：公式 / 图求值 / 接口
cd web && pnpm test && pnpm typecheck   # 前端：单测 + 类型检查
```
