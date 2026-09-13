# AGENTS.md — AI_storage_daily_push_system 项目上下文

> 本文件是项目自包含上下文，任何 agent（有无历史记忆）进入本目录即可自引导上手。
> 跨项目通用约定见全局 memory / skill；本文件只放本项目专属知识 + 通用约定的落地细节。

## 项目是什么

「AI 每日情报简报系统」：Tavily 检索 → LLM 提炼（相关性过滤 + 双标签）→ 去重 → 深度分析（四段式）→ 质检 → 渲染（前端模板）→ pushplus 推送。GitHub Actions 每日 UTC 06:00 调度，产物 commit 回仓库 + GitHub Pages 发布。

## 怎么跑 / 怎么测

```bash
cd agent123
THEME=<theme_id> .venv/bin/python -m src.main          # 跑完整流水线（默认 europe_storage）
.venv/bin/python -m pytest -q                            # 全量测试
```

- `THEME` 环境变量指定主题，默认 `europe_storage`，可选 `nordic_education`。
- 依赖：DEEPSEEK_API_KEY、TAVILY_API_KEY、PUSHPLUS_TOKEN（.env + GitHub Secrets）。
- 前端页面：`docs/index.html`，GitHub Pages 发布到 https://happydayeach.github.io/AI_storage_daily_push_system/

## 项目专属约定

### 换主题 = 新建 config，不改代码
换主题时新建 `config/theme_<主题>.yaml`（填 theme_id/theme_name/region/industries/verticals/categories/keywords_matrix/page_title/competitors/theme_colors/push_targets 等），**不改任何 src 代码**，用 `THEME` 环境变量切换。配置化已由 `config_loader.py` 完成（默认值兜底 + 幂等 resolve）。

### Tavily 英文检索
Tavily 是英文引擎，检索新闻**必须用英文关键词**，地域用**具体国家维度**（Sweden/Finland/Denmark/Iceland/Norway，而非「北欧」泛词），优先英文网页。中文词/泛地区词会搜到 SEO 垃圾。

## 项目专属 pitfall（踩过的坑）

1. **config_loader getter 必须幂等 resolve**：`get_sections`/`get_industries` 等一律 `resolve(config)[key]`，不要直接 `config.get(...)`。曾因 get_sections 漏 resolve + resolve 漏 analysis_template_sections 默认值，导致空 config 拿到空四段。
2. **改「某段可空/签名/配置语义」要同步所有消费模块**：如「竞对信号可空」牵扯 agent4（产出）+ agent5（QA 校验）+ agent6（渲染）三处，改一个要同步另外两个。
3. **显式声明会覆盖默认值**：北欧主题 `industries:` 显式写了 flash/distributed/data-protection 就漏了 general，导致 general 标签静默丢失。显式声明某字段时，要补全该字段的所有项（含 general）。
4. **竞对信号段可空**：无厂商布局时留空，agent5 QA 已对齐（新报告空竞对信号不判缺失，其他必填段仍判红）。
5. **去重导致 docs 空**：手动重跑 main.py 时，已存 story_store 的新闻会被判「重复」，docs 渲染成空卡片。渲染理想上应读 story_store 近期 story 而非只看本次新事件（待优化）。

## 通用约定的本项目落地

- **测试按模块拆分**：`src/<模块>.py` ↔ `tests/test_<模块>.py` 一一对应，映射表见 `tests/MAPPING.md`。改代码工作流：看 diff → 查 MAPPING → 只读相关测试+接口 → 改 → 跑相关测试 → 全量。
- **review 临时文件**：探针/证据脚本统一放 `<项目>/review_tmp/`，打结时删除。

## 指向其他文档

- `../README.md`：项目概述 + 部署 + 运行
- `../DESIGN.md`：架构 + 数据流 + config 结构
- `../PROJECT_LOG.md`：项目经验沉淀（按时间）
- 打结文件：`../打结/*.md`（项目状态 + 下一步）

## 架构速览

- `src/agent1_discovery.py`：Tavily 检索（region × keyword 笛卡尔积，URL 去重，48h 时区过滤）
- `src/agent2_extraction.py`：LLM 提炼（relevant 相关性闸门 + industry/vertical 双标签 + title_zh + structured_summary），单次调用
- `src/agent3_dedupe.py`：embedding 去重（threshold 0.88/0.75）
- `src/agent4_analysis.py`：深度分析（new 四段式 / update 新进展），竞对信号聚焦 competitors 厂商布局
- `src/agent5_qa.py`：质检（new 四段必填除竞对信号可空 / update 更新段校验），不阻断渲染推送
- `src/agent6_render.py`：渲染（复用前端模板 + config 驱动标题/标签/filter-bar）+ 推送文案
- `src/agent7_push.py`：pushplus 聚合适配器（channel 默认 wechat）
- `src/config_loader.py`：主题配置加载（默认值兜底 + 幂等 resolve + 便捷 getter）
- `src/main.py`：Agent1→7 串接，THEME 环境变量指定主题
