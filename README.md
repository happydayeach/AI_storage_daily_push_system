# AI_storage_daily_push_system

「AI 每日情报简报系统」—— 从检索到推送的全自动行业情报流水线。

**主题可复用**：换主题（地域/行业侧重改变）时只新建一个 config 文件，代码零改动。

## 流水线（Agent 1-7）

```
Tavily 检索 → LLM 提炼(相关性过滤+双标签) → 去重 → 深度分析(四段式) → 质检 → 渲染(前端模板) → pushplus 推送
```

| Agent | 职责 | 文件 |
|---|---|---|
| 1 | 检索（region×关键词笛卡尔积） | `src/agent1_discovery.py` |
| 2 | 提炼（relevant 闸门 + industry/vertical + title_zh + 一段话总结） | `src/agent2_extraction.py` |
| 3 | 去重（embedding） | `src/agent3_dedupe.py` |
| 4 | 深度分析（四段式 + 竞对信号厂商布局） | `src/agent4_analysis.py` |
| 5 | 质检（不阻断渲染推送） | `src/agent5_qa.py` |
| 6 | 渲染（复用前端模板）+ 推送文案 | `src/agent6_render.py` |
| 7 | 推送（pushplus 聚合） | `src/agent7_push.py` |

## 运行

```bash
cd agent123
# 依赖见 .env（DEEPSEEK_API_KEY / TAVILY_API_KEY / PUSHPLUS_TOKEN）
THEME=europe_storage .venv/bin/python -m src.main    # 跑完整流水线
.venv/bin/python -m pytest -q                         # 全量测试
```

## 换主题

换主题 = 新建 `config/theme_<主题>.yaml`，**不改代码**，用 `THEME` 环境变量切换。

现有主题：
- `europe_storage`：欧洲存储市场（默认）
- `nordic_education`：北欧存储·教育行业（5 国维度 + 教育行业标签）

## 部署

- GitHub Actions：`.github/workflows/daily.yml`，cron `0 6 * * *`（UTC），跑完自动 commit 产物回仓库。
- GitHub Pages：发布 `docs/index.html` → https://happydayeach.github.io/AI_storage_daily_push_system/

## 文档索引

- `agent123/AGENTS.md`：项目专属约定 + pitfall + 上手速览（agent 自加载）
- `DESIGN.md`：架构 + config 结构 + 关键决策
- `PROJECT_LOG.md`：项目经验沉淀
- `打结/`：项目状态 + 下一步

## 给 agent 的快速上手

进项目先读 `agent123/AGENTS.md`（自加载），它覆盖了怎么跑、约定、坑、架构速览。
