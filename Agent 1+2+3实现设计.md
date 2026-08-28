# Agent链路实现方案：检索 → 提炼 → 去重
## 目标
根据设计说明书，实现**检索 → 提炼 → 去重**三条Agent业务链路。
当前新闻检索API尚未确定，因此做接口抽象，提供模拟数据源用于开发测试；同时预留 GDELT / Bing News / NewsAPI 等真实新闻API接入点位。

## 编码约束原则
1. **模块化**
每个 Agent 封装为独立函数/类，业务逻辑隔离，方便后续替换实现、单元测试。

2. **配置驱动**
`theme_config` 主题配置对象作为整个链路的唯一输入源。

3. **无状态设计**
历史 story 新闻库由外部传入文件/数据；Agent内部不维护持久状态，仅处理当前批次数据。

4. **可观测性**
链路关键节点输出日志，便于调试、排查流程问题。

## 项目结构：
```
agent_123/
├── config/
│   └── theme_europe_storage.yaml        # 主题配置（示例）
├── story_store/
│   └── stories.json                     # 历史 story 库（持久化）
├── src/
│   ├── agent1_discovery.py              # 信源发现
│   ├── agent2_extraction.py             # 抓取与提炼
│   ├── agent3_dedupe.py                 # 去重聚类
│   ├── models.py                        # 数据模型 (dataclasses)
│   ├── llm_client.py                    # Claude API 封装
│   ├── embedding_client.py              # 嵌入模型封装（本地sentence-transformers）
│   └── main.py                          # 主流程编排
├── requirements.txt
└── README.md
```
