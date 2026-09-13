# DESIGN.md — 架构 + config 结构 + 关键决策

## 数据流

```
Agent1 discover_articles(theme_config, searcher) -> List[RawArticle]
Agent2 process_articles(articles, llm, theme_config) -> List[ExtractedEvent]
Agent3 Deduplicator.dedupe(events, story_records) -> DedupResult(new, update, dropped)
Agent4 analyze(result, searcher, llm, theme_config) -> List[DeepReport]
Agent5 qa(reports, theme_config) -> QAResult
Agent6 render_html/render_push_message(reports, theme_config) -> html / text
Agent7 push_all(adapters, push_message) -> results
```

- 去重：embedding 相似度双阈值（0.88 / 0.75），story_store 按 theme_id 隔离，14 天过期。
- QA 不阻断渲染推送（main.py 里 qa 结果只落盘，不影响后续）。
- 渲染复用仓库根 `eu-storage-daily-*.html` 设计稿，用 `_CONTENT_MARKER` / `_FOOTER_MARKER` / `_FILTER_BAR_MARKER` 定位替换内容区。

## config 结构（theme_<主题>.yaml）

```yaml
theme_id: "nordic_education"          # 主题唯一标识
theme_name: "北欧存储·教育行业"       # system_prompt 用
page_title: "北欧存储·教育行业"       # 前端 <title>/<h1>/页脚 用
region: ["Sweden","Finland","Denmark","Iceland","Norway"]  # 地域（支持 str 或 list，国家维度）
relevance_theme: "存储产业（数据存储、云存储、闪存、NAND、SSD...）"  # Agent2 relevant 判断标准
keywords_matrix:                      # 关键词矩阵（英文），region × keyword 笛卡尔积
  - ["data storage", "cloud storage", "data center"]
  - ["distributed storage", "edge computing", "data lake"]
  - ["flash storage", "NAND", "SSD"]
  - ["education technology", "EdTech", "smart campus"]
source_whitelist: []                  # 空=不限制
source_blacklist: ["ttplus.cn"]
categories:                           # 四大分类（含 id/icon，用于 section 分组）
  - {id: "sec-industry", label: "产业热点", icon: "🏭"}
  - {id: "sec-vertical", label: "垂直行业热点", icon: "📊"}
  - {id: "sec-regulation", label: "监管与合规", icon: "⚖️"}
  - {id: "sec-product", label: "产品与技术", icon: "🚀"}
industries:                           # 产业标签（含 general，双标签之产业）
  flash: {icon: "💾", label: "闪存", desc: "闪存存储硬件（NAND/SSD/存储芯片/DRAM）"}
  distributed: {icon: "🌐", label: "分布式", desc: "分布式存储/边缘存储/多云/数据湖"}
  data-protection: {icon: "📀", label: "数据保护", desc: "数据保护/GDPR/数据合规/数据主权"}
  general: {icon: "📦", label: "通用", desc: "存储相关但不属于闪存/分布式/数据保护"}
verticals:                            # 行业标签（双标签之行业）
  education: {icon: "🎓", label: "教育", desc: "教育行业（教育信息化/智慧校园/在线教育）"}
  finance: {icon: "💰", label: "金融", desc: "金融行业"}
competitors:                          # 竞对信号段分析对象
  ["Dell DataDomain", "HPE", "Rubrik", "Cohesity", "Hitachi", "Commvault", "Pure Storage"]
event_types: ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"]
analysis_template_sections: ["背景", "技术分析", "市场影响", "竞对信号"]  # new 事件四段式
update_section_name: "新进展"         # update 事件段名
template_glob: "eu-storage-daily*.html"
theme_colors: {primary: "#1a5fb4", accent: "#e66100"}
icon_map: {财报: "📈", 产品发布: "🚀", 监管: "⚖️", 合作: "🤝", 并购: "🏦", 漏洞: "🔒", 其他: "📌"}
push_targets:
  - channel: "wechat"
```

## config_loader 机制

- `load_theme_config(theme_id)` 读 yaml（不 resolve）。
- `resolve(config)` 补默认值（deepcopy，缺省字段用内置默认，显式字段不覆盖）。
- 便捷 getter 一律 `resolve(config)[key]`（幂等）：get_categories/get_industries/get_verticals/get_sections/get_event_types。
- 兼容：categories 支持 list[str]（旧格式，补默认 id/icon）和 list[dict]（新格式）。

## 关键决策

1. **搜索**：Tavily（英文关键词 + 国家维度 region 列表），不用中文/泛地区词。
2. **相关性过滤**：Agent2 单次 LLM 调用输出 `relevant` 布尔，仅 strict `is False` 丢弃（fail-open）。
3. **推送**：单一 pushplus 聚合适配器，channel（默认 wechat）+ option 覆盖微信/飞书，不建独立渠道。
4. **渲染**：复用仓库根 `eu-storage-daily-*.html` 设计稿，config 驱动标题/标签/filter-bar。
5. **竞对信号**：聚焦 competitors 厂商布局，无布局留空（agent5 QA 对齐可空）。
6. **产业标签**：闪存/分布式/数据保护 + general（通用兜底，存储相关但不属三类）。
7. **多主题**：换主题 = 新建 config + 改 THEME，代码零改动（C8 用 git diff 证明）。
