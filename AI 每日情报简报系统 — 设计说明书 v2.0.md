好的，我将当前最新方案（**Tavily 搜索版**）整理为一份完整、规范的设计文档，方便您后续迭代修改。

---

# AI 每日情报简报系统 — 设计说明书 v2.0

> **版本**：v2.1（Tavily 搜索版）  
> **状态**：✅ 已完成 Agent 1+2+3 核心链路设计，进入实现阶段  
> **目标**：复刻并改进“欧洲存储市场每日情报简报”，实现 **检索 → 提炼 → 去重 → 分析 → 推送** 全自动化链路，全程无人在环。  
> **核心变更**：Agent 1 信源发现改用 **Tavily Search API**（真·全网搜索）替代爬虫；原 v2.0「DeepSeek 原生联网 `enable_search`」方案因该参数不存在已废弃。

---

## 目录

1. [核心需求（不变）](#1-核心需求不变)
2. [v1.0 → v2.0 变更摘要](#2-v10--v20-变更摘要)
3. [系统架构与数据流](#3-系统架构与数据流)
4. [Agent 详细设计](#4-agent-详细设计)
5. [数据模型](#5-数据模型)
6. [主题配置（theme_config）](#6-主题配置theme_config)
7. [视觉与主题系统（不变）](#7-视觉与主题系统不变)
8. [部署与调度（不变）](#8-部署与调度不变)
9. [关键 Prompt 工程](#9-关键-prompt-工程)
10. [待调优参数](#10-待调优参数)
11. [项目目录结构](#11-项目目录结构)
12. [后续开发计划](#12-后续开发计划)

---

## 1. 核心需求（不变）

以下约束自 v1.0 起确立，贯穿整个设计，**不可动摇**：

| 需求 | 说明 |
| :--- | :--- |
| **数据源不固定** | 不维护 RSS 白名单，每轮实时检索 |
| **时间窗口** | 只抓取过去 24–48 小时内发布的内容 |
| **去重** | 每天与历史 story 库做语义去重，避免重复报道 |
| **语言策略** | 优先英文数据源，减少中文转译导致的旧闻重复 |
| **持续报道** | 对同一热点事件保持跨天追踪，报道“新进展”而非重复背景 |
| **多 Agent 拆分** | 链路拆成职责单一的多个 Agent，可独立替换 |
| **无人在环** | 所有判断（去重阈值、异常处理）必须程序化 |
| **可复用** | 架构预留多主题扩展（`theme_id` 一等公民） |

---

## 2. v1.0 → v2.0 变更摘要

| 模块 | v1.0 原始方案 | **v2.1 当前方案（Tavily 版）** |
| :--- | :--- | :--- |
| **Agent 1（信源发现）** | 调用 Bing News / GDELT / NewsAPI | 使用 **Tavily Search API**（`topic=news`，真·全网搜索）直接返回结构化新闻列表 |
| **Agent 2（抓取与提炼）** | `requests` + BeautifulSoup 爬取全文 → 喂给 Claude | **完全移除爬虫**，直接基于标题 + Snippet 让 DeepSeek 做结构化提取 |
| **外部依赖** | `requests`, `beautifulsoup4`, `anthropic`, `newspaper3k` | `openai`（DeepSeek SDK）, `sentence-transformers`, `python-dotenv` |
| **版权合规风险** | 需人工约束 LLM“转述不引用”，但抓取全文仍有风险 | **仅使用公开 Snippet**，绝不复制全文，合规性最高 |
| **维护成本** | 需应对网站反爬、HTML 结构变化 | **维护成本归零**，网站改版与系统无关 |

---

## 3. 系统架构与数据流

### 整体数据流（v2.0）

```text
[主题配置 theme_config]
         ↓
┌────────────────────────────────────────────────────────────┐
│ Agent 1：信源发现（Tavily 搜索）                           │
│   输入：关键词矩阵                                         │
│   操作：调用 Tavily Search API（topic=news）               │
│   输出：RawArticle[] (url, title, snippet, published_at, domain) │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ Agent 2：提炼（DeepSeek 推理）                             │
│   输入：RawArticle[]                                       │
│   操作：基于 title + snippet 生成结构化事件卡片             │
│   输出：ExtractedEvent[] (含 event_type, entities, summary_zh, category) │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ Agent 3：去重聚类（本地 Embedding + 余弦相似度）           │
│   输入：ExtractedEvent[] + 历史 Story 库                   │
│   操作：生成 embedding，双阈值判定 new / update / duplicate │
│   输出：DedupResult { new, update, duplicate_dropped_count } │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ Agent 4：深度分析（待实现）                                │
│   仅处理 new / update，进行二次定向检索，生成深度报告       │
└────────────────────────────────────────────────────────────┘
         ↓
┌────────────────────────────────────────────────────────────┐
│ Agent 5：质检（待实现） → Agent 6：渲染与推送（待实现）    │
└────────────────────────────────────────────────────────────┘
         ↓
    写回 Story 库 + git commit
```

### 关键设计决策

- **Agent 1 检索走 Tavily Search API；Agent 2 提炼走 DeepSeek Client**，二者独立。
- **需维护两个 key**：`TAVILY_API_KEY`（搜索）+ `DEEPSEEK_API_KEY`（提炼）。
- **Agent 3 使用本地 `sentence-transformers`**，无需额外 API 调用，成本可控且速度快。

---

## 4. Agent 详细设计

### 4.1 Agent 1：信源发现（Tavily 搜索）

| 属性 | 描述 |
| :--- | :--- |
| **输入** | `theme_config.keywords_matrix`（关键词分组列表） |
| **核心方法** | 对每个关键词，调用 `TavilySearchTool.search(keyword)`（`topic=news`，`max_results=10`）返回结构化结果列表 |
| **输出** | `List[RawArticle]`，包含 `url, title, snippet, published_at, domain` |
| **去重策略** | 按 URL 去重；时间窗口由代码按 `published_at` 强制过滤（48 小时） |
| **异常处理** | 某关键词搜索失败时记录日志并跳过，不影响整体流程 |

**Prompt 核心指令**（见第 9 节完整模板）：
- 指定时间窗口（过去 24–48 小时）。
- 要求返回严格 JSON 格式。
- 优先权威技术媒体。
- 禁止虚构内容。

---

### 4.2 Agent 2：提炼（DeepSeek 推理）

| 属性 | 描述 |
| :--- | :--- |
| **输入** | `RawArticle`（仅使用 `title` + `snippet`，**不再抓取全文**） |
| **核心方法** | 调用 DeepSeek，将标题和摘要作为上下文，输出结构化 JSON |
| **输出** | `ExtractedEvent`，包含 `event_type`, `entities`, `key_numbers`, `summary_zh`, `category` |
| **版权合规** | 强制要求“转述、不引用原文”，输入仅是公开片段，输出是重新组织的摘要 |
| **分类映射** | `category` 字段直接映射到四大分类（产业热点 / 垂直行业热点 / 监管与合规 / 产品与技术） |

---

### 4.3 Agent 3：去重聚类（本地 Embedding）

| 属性 | 描述 |
| :--- | :--- |
| **输入** | `List[ExtractedEvent]` + 历史 Story 库（近 14 天） |
| **核心算法** | 1. 使用 `sentence-transformers/all-MiniLM-L6-v2` 生成摘要向量<br>2. 计算当前事件之间、当前事件与历史事件之间的余弦相似度<br>3. 双阈值判定 |
| **阈值** | `threshold_a = 0.88`（重复，丢弃）<br>`threshold_b = 0.75`（更新，持续追踪） |
| **输出** | `DedupResult { new: [], update: [], duplicate_dropped_count: int }` |
| **内部去重** | 同批次事件之间先做一次去重，保留最早发布的事件 |

---

## 5. 数据模型

### 5.1 RawArticle（Agent 1 输出）

```python
@dataclass
class RawArticle:
    url: str
    title: str
    snippet: str
    published_at: str   # ISO 8601
    domain: str
```

### 5.2 ExtractedEvent（Agent 2 输出）

```python
@dataclass
class ExtractedEvent:
    event_type: str          # 财报/漏洞/产品发布/监管/合作/并购/其他
    entities: List[str]      # 公司/产品/法规
    key_numbers: List[str]   # 金额/日期/编号
    summary_zh: str          # 中文转述摘要（100-150字）
    category: str            # 产业热点 / 垂直行业热点 / 监管与合规 / 产品与技术
    source_url: str
    published_at: str
    domain: str
    title: str = ""          # 原始标题（便于追溯）
    snippet: str = ""        # 原始摘要（便于追溯）
```

### 5.3 StoryRecord（持久化 Story 库）

```python
@dataclass
class StoryRecord:
    story_id: str            # 唯一标识，建议用 uuid 或 hash
    theme_id: str            # 属于哪个主题
    first_seen_date: str     # 首次出现日期
    last_updated_date: str   # 最后更新日期
    summary_history: List[str]  # 每次更新的摘要（追加）
    embedding: List[float]   # 最新摘要的向量
    source_urls: List[str]   # 所有来源 URL
    category: str            # 所属分类
```

### 5.4 DedupResult（Agent 3 输出）

```python
@dataclass
class DedupResult:
    new: List[ExtractedEvent]
    update: List[Dict]       # [{"event": ExtractedEvent, "story_id": str, "history_summary": str}]
    duplicate_dropped_count: int
```

---

## 6. 主题配置（theme_config）

每个主题一份 YAML 文件，存放于 `config/` 目录。

```yaml
# config/theme_europe_storage.yaml
theme_id: "europe_storage"

# 关键词矩阵：多组同义/相关查询，分别检索后合并
keywords_matrix:
  - ["数据保护", "GDPR", "云存储合规", "欧洲数据法案"]
  - ["分布式存储", "边缘存储", "多云架构", "数据湖"]
  - ["闪存", "NAND", "SSD", "存储芯片", "3D NAND"]

# 信源黑白名单（可选，暂不启用）
source_whitelist: []
source_blacklist: []

# 四大分类（固定）
categories:
  - "产业热点"
  - "垂直行业热点"
  - "监管与合规"
  - "产品与技术"

# 深度分析模板结构
analysis_template_sections:
  - "背景"
  - "技术分析"
  - "市场影响"
  - "竞对信号"

# 视觉主题变量（对应 HTML）
theme_colors:
  primary: "#1a5fb4"
  accent: "#e66100"

# 事件类型 → Emoji 映射
icon_map:
  财报: "📈"
  产品发布: "🚀"
  监管: "⚖️"
  合作: "🤝"
  并购: "🏦"
  漏洞: "🔒"
  其他: "📌"

# 推送目标列表（待实现）
push_targets: []
```

---

## 7. 视觉与主题系统（不变）

沿用 v1.0 设计，三层分离：

| 层级 | 内容 | 更新频率 |
| :--- | :--- | :--- |
| **通用层**（代码） | HTML 骨架、响应式 CSS 变量、暗色模式、卡片交互 JS | 一次性做好，基本不改 |
| **主题可变层**（配置） | 色板、图标映射、分类体系 | 新增主题时新增一份配置 |
| **内容数据层**（每日生成） | Agent 4 输出的结构化 JSON | 每天自动生成 |

### 当前主题的固定产业标签（展示层）

- `📀 数据保护`（蓝色系）
- `🌐 分布式`（紫色系）
- `💾 闪存`（翠绿色系）

### 辅助行业标签（动态显示，有新闻才出现）

`金融` · `医疗` · `制造` · `零售` · `政府` · `运营商` · `商业市场`

---

## 8. 部署与调度（不变）

| 环节 | 方案 |
| :--- | :--- |
| **调度** | GitHub Actions Scheduled Workflow（cron），每天定时触发 |
| **运行环境** | GitHub Actions Runner（国际出口，直连 DeepSeek API） |
| **状态持久化** | 仓库内 SQLite/JSON 文件，Pipeline 最后一步 `git commit` 回仓库 |
| **详情页托管** | GitHub Pages（`docs/` 目录） |
| **密钥管理** | GitHub Actions Secrets（`DEEPSEEK_API_KEY`, pushplus token, 企业微信 webhook 等） |

---

## 9. 关键 Prompt 工程

### 9.1 Agent 1：搜索（Tavily Search API）

Agent 1 不再通过 LLM 联网搜索，而是直接调用 Tavily Search API：

- 端点：`POST https://api.tavily.com/search`
- 请求体：`{"query": keyword, "max_results": 10, "topic": "news", "search_depth": "basic"}`
- 鉴权：`Authorization: Bearer $TAVILY_API_KEY`
- 返回字段：`title / url / content / score / published_date`

字段映射到 `RawArticle`：`url ← url`、`title ← title`、`snippet ← content`、`published_at ← parsedate(published_date)`、`domain ← urlparse(url).netloc`（去 www）。

---

### 9.2 Agent 2：结构化提炼 Prompt

```text
请根据以下新闻信息，提取关键字段并以 JSON 格式返回。

新闻标题：{article.title}
新闻摘要（Snippet）：{article.snippet}
发布时间：{article.published_at}
来源域名：{article.domain}

请输出 JSON，包含以下字段：
- "event_type": 事件类型，从 ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"] 中选择。
- "entities": 关键实体列表（公司名、产品名、法规名等）。
- "key_numbers": 关键数字或日期列表（如金额、百分比、发布日期）。
- "summary_zh": 用中文转述摘要，严禁逐句引用原文，必须用自己的话重新组织，控制在 100-150 字。
- "category": 分类，从 ["产业热点", "垂直行业热点", "监管与合规", "产品与技术"] 中选择一个最合适的。

**只输出 JSON，不要有其他任何文字。**
```

**System Prompt**：`"你是一个专业的技术新闻分析师，擅长结构化信息提取。"`

---

## 10. 待调优参数

| 参数 | 默认值 | 说明 | 调优方式 |
| :--- | :--- | :--- | :--- |
| `threshold_a` | 0.88 | 重复判定阈值，≥ 此值视为重复 | 运行一周后用真实数据观察，若漏判/误判过多则调整 |
| `threshold_b` | 0.75 | 更新判定阈值，≥ 此值且 < A 视为同一事件的“新进展” | 同上 |
| `Agent 1 的 `hours_back` | 48 | 时间窗口（小时） | 可根据需要调整为 24（更精简）或 72（更全面） |
| Agent 1 的 `max_results` | 10 | Tavily 单次返回结果条数 | 若新闻条数不足，可增加到 20 |
| `Agent 2 的 `max_tokens` | 800 | 单条提炼输出长度 | 若摘要过长被截断，可增加 |

---

## 11. 项目目录结构

```text
.
├── config/
│   └── theme_europe_storage.yaml       # 主题配置
├── story_store/
│   └── stories.json                    # 历史 Story 库（持久化）
├── output/
│   └── agent123_result.json            # Agent 1-3 每日输出
├── src/
│   ├── __init__.py
│   ├── main.py                         # 主流程编排
│   ├── models.py                       # 数据模型
│   ├── llm_client.py                   # DeepSeek API 封装
│   ├── search_tool.py                  # Tavily 搜索封装（SearchTool 抽象）
│   ├── embedding_client.py             # sentence-transformers 封装
│   ├── agent1_discovery.py             # 信源发现（Tavily 搜索）
│   ├── agent2_extraction.py            # 结构化提炼
│   ├── agent3_dedupe.py                # 去重聚类
│   └── utils.py                        # 工具函数（日期、日志等）
├── tests/
│   └── test_agent123.py                # 单元测试（可选）
├── .env.example                        # 环境变量模板
├── requirements.txt
└── README.md
```

---

## 12. 后续开发计划

### 第一阶段 ✅（已完成设计）
- [x] 需求分析与架构设计
- [x] HTML 原型（四大分类 + 双标签系统）
- [x] Agent 1+2+3 核心代码设计（Tavily 版）
- [x] 数据模型与配置规范

### 第二阶段（待实现）
- [ ] Agent 4：深度分析
  - 对 `new` 事件做二次定向检索（Tavily 搜索）
  - 生成四段式深度报告（背景 / 技术分析 / 市场影响 / 竞对信号）
  - 对 `update` 事件生成“新进展”段落 + 链接历史摘要
- [ ] Agent 5：质检自检（条目数、字段完整性、异常日志）

### 第三阶段（待实现）
- [ ] Agent 6a：HTML 详情页生成（套用现有模板）
- [ ] Agent 6b：推送消息体生成（适配 pushplus / 企业微信 / 飞书）
- [ ] Agent 7：统一推送适配器
- [ ] Story 库持久化合并逻辑（`save_story_store` 完整实现）

### 第四阶段（部署）
- [ ] GitHub Actions Workflow 配置
- [ ] GitHub Pages 自动发布
- [ ] 环境变量配置与测试运行
- [ ] 连续运行 7 天，调优阈值参数

---

## 附录：快速参考

### 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整流程
export DEEPSEEK_API_KEY="sk-xxx"
export TAVILY_API_KEY="tvly-xxx"
python src/main.py

# 仅测试 Agent 1（Tavily 搜索）
python -c "from src.search_tool import TavilySearchTool; print(TavilySearchTool().search('europe storage market'))"
```

### 环境变量

| 变量名 | 必填 | 说明 |
| :--- | :--- | :--- |
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 |
| `TAVILY_API_KEY` | ✅ | Tavily 搜索 API 密钥 |
| `PUSHPLUS_TOKEN` | ❌ | pushplus 推送 token（Agent 7 使用） |
| `WECOM_WEBHOOK` | ❌ | 企业微信机器人 Webhook（Agent 7 使用） |
| `FEISHU_WEBHOOK` | ❌ | 飞书机器人 Webhook（Agent 7 使用） |

---

*文档版本：v2.1 | 最后更新：2026-09-09 | 维护者：AI 情报系统开发组*
