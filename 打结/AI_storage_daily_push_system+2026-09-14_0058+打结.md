# AI_storage_daily_push_system 打结记录

> 打结时间：2026-09-14 00:58
> 状态：推送改造收口（微信推「通知 + 前端 URL」），待办：前端卡片结构调整

## 一、当前状态

**推送改造（本轮完成，87 passed 全绿）：**
- 微信推送从纯文本（txt）→ HTML 富文本（html template + 转义）→ 最终定为「通知 + 前端 URL」。
- 微信推送内容：`<b>标题</b>｜分类 + 摘要 + 🔗 查看完整简报(前端 Pages URL) + 📄 原文(source_url)`。
- config 加 `frontend_url` 字段（两主题都写 Pages URL），render_push_message 主链接用 frontend_url、次链接原文，均 html.escape。
- 返工一次：frontend_url=None（YAML 留空）时抛 AttributeError，已修 `str(... or "").strip()` + 补退化断言。

## 二、下一步待办（主人新需求，先记不做）

**前端卡片结构调整：**
- 现状：一段话总结（structured_summary）渲染在 `card__body`（下拉折叠）里，和四段式分析（背景/技术分析/市场影响/竞对信号）混在一起。
- 需求（主人原话）：一篇新闻的标题，下面是「一段话总结」正文，**不要放到下拉单里面**和「背景、竞对信息等四个元素」放在一起。
- 即：卡片结构改为 = 标题（默认可见）+ 一段话总结（默认可见，放标题下方）+ ▼下拉（四段式分析折叠）。
- 涉及：`agent6_render.py` 的 `_card_html`（约 95-99 行把 structured_summary 加到 body 前，需移出 body、放到 header 与 body 之间）+ 可能前端模板 CSS（card__header 下方加一个默认可见的 summary 区）。
- 尚未建卡，下次续接时开 dev→review→tester 链。

## 三、遗留/待办（非阻塞）

1. **pytest 覆盖 docs/index.html**（卡 t_7ebc8692，review 发现，已开卡）：`tests/test_main.py::test_main_continues_after_qa_failure_and_writes_rendered_outputs` 会真跑 `main.main()`，把仓库根 `docs/index.html` 覆盖成测试夹具内容（Acme 动态/source.example），每次 pytest 污染 docs 产物。基线既有问题，待处理。
2. **渲染与去重耦合**（架构问题）：手动重跑时 story_store 已存新闻被判重复，docs 渲染空卡片。理想上渲染应读 story_store 近期 story 而非只看本次新事件。每次手动重跑前需清对应 theme 的 story_store。
3. **worker detached worktree 误删文件**（已修 + 已记 skill）：曾误删 search_tool.py/llm_client.py 等 4 文件，已 git checkout 恢复；orchestrator 跑流水线前先 `git status` 查意外 `D`。

## 四、关键 commit 链（近期）

`fc11f48`（HTML 富文本推送重跑）→ `d7bbe8d`（推送 HTML 富文本 template html）→ `625fe8f`/`c6a2832`（前端 URL + None 修复）→ `bd4a336`（前端 URL 推送重跑）

远程：happydayeach/AI_storage_daily_push_system（public），Pages 已启用。

## 五、记忆/机制（本轮沉淀）

- SOUL.md 加了两条硬流程：① 拆卡前必须 `skill_view('kanban-orchestration')`；② 建卡必须让 worker 知道代码在哪（优先 workspace_kind=dir + workspace_path，`<项目名>` 变量不写死）。
- skill（kanban-orchestration）补：改签名连锁、getter 幂等、backup 核对 git、预建 review 卡无法 request_changes、worktree 误删、dir workspace。
- 项目自包含文档：agent123/AGENTS.md（自加载）+ README + DESIGN + PROJECT_LOG + 打结/ 都已进仓库。
