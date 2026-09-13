# AI_storage_daily_push_system — 项目经验沉淀

## 项目背景
「AI 每日情报简报系统」Agent 1+2+3 链路(检索 → 提炼 → 去重)。仓库:`happydayeach/AI_storage_daily_push_system`,本地 `/tmp/AI_storage_daily_push_system`,代码在 `agent123/`。

## 本次接手时的现状(诊断结论)
- `src/models.py`、`src/utils.py`、`tests/test_agent123.py`、`output/agent123_result.json`、`story_store/stories.json` 全为空文件(1 字节)。
- 4 个数据模型 RawArticle/ExtractedEvent/StoryRecord/DedupResult 被 21 处 import 引用却未定义 → 整条链 ImportError。
- `requirements.txt` 空,依赖未声明。
- **设计说明书 v2.0 的「DeepSeek 原生联网(`enable_search`)」根本不存在**——DeepSeek 官方 API 无此参数,OpenAI SDK 也无。这是设计核心前提错误。

## 本次完成(5 commit)
| commit | 内容 |
|---|---|
| b0305a3 | Slice1:补 4 个 dataclass、包化 src 导入、无效 JSON story store 兜底、requirements/env/utils |
| e53c787 | Slice2:Agent1 改可插拔 Google Custom Search/Mock 搜索源,黑白名单按 domain 生效,移除 enable_search |
| 6e46e67 | Slice3:agent2 JSON 清理(```json+纯```) + entities/key_numbers 类型兜底 + config icon_map 补 7 键 |
| b77f396 | Slice4:补全 mock 测试(11 用例)+ 修裸 except |
| d7a0c17 | Slice2 返工:搜索容错 + 时区过滤修复 |

## 关键决策
- **联网方案**:方案 B —— SearchTool 抽象接口(TavilySearchTool + MockSearchTool),LLM(DeepSeek)只做 Agent2 提炼,Agent1 检索走搜索工具。搜索用 **Tavily Search API**(环境变量 TAVILY_API_KEY,topic=news,真·全网搜索)。2026-09-09 起替换掉 Google CSE(其无法全网搜索)。
- **导入约定**:统一 `from src.xxx import`,加 `src/__init__.py`,运行 `python -m src.main`。
- **测试策略**:全 mock(MockSearchTool/FakeEmbedder/FakeDeepSeekClient),不依赖网络/key/模型下载。

## 坑(实测)
1. **`enable_search` 不存在**:DeepSeek API 与 OpenAI SDK 都无此参数,传了会 TypeError。Agent1 联网必须走搜索工具或换带联网的模型。
2. **时区 aware/naive 相减 TypeError**:`datetime.now()`(naive)减 `datetime.now(timezone.utc)`(aware)抛 TypeError,被裸 `except: pass` 吞掉后"48h 严格过滤"形同虚设(60h 旧闻漏进来)。统一用 aware 时间或 naive 补 +00:00。
3. **搜索失败无容错 = 整条流水线崩**:GoogleSearchTool 网络/HTTP 4xx/JSON 错误要 try/except 返回 [],discover_articles 对每个 keyword 单独容错 continue。
4. **约束与 DoD 不能自相矛盾**(orchestrator 教训):返工卡里写了"只改 3 个文件"但 DoD 要求"新增回归测试"(要改第 4 个文件 tests/),导致 dev 正确 block 求助。写卡时约束和 DoD 要自洽。

## 剩余 TODO(设计说明书第 2~4 阶段,本次未做)
- Agent 4(深度分析)、Agent 5(质检)、Agent 6(渲染推送)、Agent 7(推送适配器)。
- `save_story_store` 持久化合并逻辑(目前是空桩)。
- 真实 DEEPSEEK_API_KEY 接入跑通全链路(Tavily key 已接入并跑通)。
- GitHub Actions 调度 + GitHub Pages 部署。

## 2026-09-09：搜索源 Google CSE → Tavily（本次完成）
- dev→review→tester 全绿。3 个 commit:da855c5(替换 TavilySearchTool)、5493b36(load_dotenv 移入 main + .gitignore)、9e13696(设计说明书 v2.1)。
- TavilySearchTool 用 stdlib urllib 直连 api.tavily.com(topic=news,max_results=10),映射 url/title/snippet=content/published_at=parsedate(published_date)/domain 去 www。
- 真实 Tavily 检索验证通过(返回 10 条);测试 12 passed;源码零 Google 残留。
- 加了 .gitignore(.env/.venv/__pycache__)、python-dotenv、TAVILY_API_KEY 进 .env(不入库)。

## 已知架构问题（记录备查，暂不解决 —— 只记录，不操作）
- **dev worker 无状态**：dev/review/tester 不持跨项目记忆，连当前项目其他部分都不清楚，全部依赖 orchestrator 喂上下文。
- **orchestrator 会话时效**：coder 会话超 24h 无激活会重置（idle_minutes=1440），且记忆有字符上限。
- 多天项目状态连续性目前靠「打结 log.md + 记忆指针」兜底；系统性方案（项目级持久状态/上下文快照，让无状态 worker 自动完整重定向）待日后设计。


## 2026-09-09：LLM provider 开关 + DeepSeek 改 flash（本次完成）
- llm_client.py 的 DeepSeekClient 改为 LLMClient，支持 `LLM_PROVIDER` 切换 deepseek | codex。
- **DeepSeek 分支**：`deepseek-v4-flash` + `extra_body={"thinking":{"type":"disabled"}}`（省 token；`deepseek-chat` 已退役，`deepseek-v4-pro` 是推理模型需抬 max_tokens）。
- **Codex 分支**：`gpt-5.6-terra`（OAuth，读 ~/.codex/auth.json + ChatGPT-Account-Id header，走 Responses API；`gpt-5.4-mini` 实测 400 不支持 ChatGPT 账号）。
- 真实双 provider 验证通过；14 测试全绿。commits：f09ef25(开关)、5a6b4de(改 flash)。

## 2026-09-13：Agent6 渲染返工 + workspace 损坏恢复（本次完成）

### Agent6 渲染返工（update 事件丢数据）
- **缺陷**：`agent6_render.py` 的 `_card_html` 固定遍历硬编码 `_SECTION_NAMES` 四段名，不按 `report.is_update` 分支。Agent4 `_analyze_update` 只产出 `sections={"新进展":...}` 单键 + `is_update=True` + `history_summary`，导致 update 报告渲染成 4 个空 `<p></p>`，「新进展」正文与 history_summary 完全丢失。
- **修复**（commit 4e0d95a）：`_card_html` 按 `report.is_update` 分支——update 渲染「新进展」+（有值才）「历史摘要」；new 走四段模板。补 update 渲染回归测试 + 修正 category 断言（命中卡片 `<span class="tag">` 非 header 文案）+ 补四段段内容断言。
- **教训**：dev 首版只测了 new 事件（is_update=False），update 路径零覆盖 → 绿测试对数据丢失完全失守。**凡有 is_update/new 双分支的渲染/分析逻辑，必须两个分支都上测试用例**。
- dev→review→tester 全绿：25 passed（基线 24 +1），review 六项全绿，tester 独立 21 断言 PASS。

### workspace 损坏恢复（重要教训）
- **现象**：/tmp 被 macOS 系统清理（9/11），`.git/config` + `.git/HEAD` 丢失 + 10 个源码文件（agent3_dedupe.py/embedding_client.py/utils.py/__init__.py/config yaml 等）被删 + venv 被清（pyvenv.cfg 缺失、site-packages 被 strip）。
- **恢复**：本地 `.git/objects`（122 个）+ `refs` + `logs/HEAD` 完好，只需重建 `.git/config`（origin 指向）与 `.git/HEAD`（`ref: refs/heads/main`），再 `git reset --hard` 即完整恢复工作区；venv 用 uv 重建。
- **风险**：若 objects 也被清，代码永久丢失。**评审通过必须及时 push（远程才是真正兜底），且关键 commit 不要只在本地 /tmp 存一份**。
- 本次 Agent6 的 `7c1b790` 曾一度只在本地（远程只到 Agent5 的 7fb1242），万幸 objects 完好才救回；返工全绿后已 push `8b75367` 上远程。

## 2026-09-13：Agent7 + 端到端接线 + 部署（本次完成，系统端到端跑通）

### Slice E：Agent7 统一推送适配器（pushplus/wecom/feishu）
- 三渠道 API 准确格式：pushplus `POST http://www.pushplus.plus/send`（body `{token,title,content,template:"txt"}`，判 `code==200`）；wecom `POST webhook`（`{"msgtype":"text","text":{"content":...}}`，判 `errcode==0`）；feishu `POST webhook`（`{"msg_type":"text","content":{"text":...}}`，判 `code==0` 兼容 `StatusCode==0`）。
- `PushAdapter` ABC + 三实现；`build_adapters` 占位符回退环境变量、无凭证跳过；`push_all` 单渠道失败不中断。
- HTTP 用 stdlib `urllib.request`（项目约定，不引 requests）。

### Slice F：端到端接线（main 串 Agent4-7）
- main.py 之前只串到 Agent3 + save_story_store；本次串 Agent4 analyze → Agent5 qa → Agent6 render → Agent7 push。
- QA 不阻断（passed=False 仍渲染推送，结果落盘）；reports 空 / push_message 空时跳过推送不 crash。

### Slice G：部署（GitHub Actions + Pages）
- `.github/workflows/daily.yml`：cron `0 6 * * *` + workflow_dispatch + `permissions.contents: write` + 跑 `python -m src.main` + commit 回仓库。
- **3 个 Critical 坑（review 实机抓出，workflow 每次运行必失败）**：
  1. `working-directory: agent123` 使 main.py 写 `agent123/docs/`，但提交步在仓库根 `git add docs/` → `fatal: pathspec`。修：HTML 用绝对路径（`os.path.dirname×3(abspath(__file__))`）写**仓库根** `docs/`。
  2. `.gitignore` 忽略 `agent123/output/` 但该目录下 `agent123_result.json` 已跟踪 → `git add` 退出码 1，`bash -eo pipefail` 终止提交步。修：删 `.gitignore` 的 output 忽略规则（结果 JSON 本就该持久化跟踪）。
  3. `actions/checkout@v4` 检出 detached HEAD，裸 `git push` 报错。修：`git push origin HEAD:${{ github.ref_name }}`。
- **Actions Runner 无 codex OAuth**（`~/.codex/auth.json` 只在本地）→ `LLM_PROVIDER` 固定 `deepseek`。
- **GitHub Free plan 不支持 private repo Pages**（HTTP 422「Your current plan does not support GitHub Pages」）。最终决策：暂不启用 Pages，只跑 Actions 生成 HTML/JSON。

### 端到端真实验证成功
- 手动 `workflow_dispatch` 触发 run `34764419815`，全 job 绿（8m50s），真实 Tavily 检索 + DeepSeek 分析跑通。
- workflow 自动 commit `chore: daily briefing 2026-09-13`，`docs/index.html` + `agent123/output/agent123_result.json` 入库 main 分支。

### 编排教训（orchestrator）
- 建 dev→review→tester 依赖链时，**tester 卡的 parents 必须是 review 卡**（链是 dev→review→tester），不是 dev 卡。并行建 review+tester 卡时 review id 未返回，易误填 dev id；应串行建卡，或用 `kanban_link` 事后补连 tester→review 边。

## 2026-09-13 晚间：设计纠正 + 调优 + 前端集成 + Pages 发布（全链路彻底打通）

> 本段**纠正/更新**了上一段（Slice E 三渠道、Slice G「暂不启用 Pages」）的若干结论。

### 1. Agent7 设计纠正：三渠道 → 单一 pushplus 聚合（主人纠正）
- 之前把 pushplus/wecom/feishu 当**三独立渠道**（WecomAdapter/FeishuAdapter 直接对接下游 webhook）是**错误设计**。
- 纠正：pushplus 是**聚合推送网关**，一个 token + `channel`（默认 wechat）+ `option`（webhook 编码）覆盖微信/飞书/企业微信。删 WecomAdapter/FeishuAdapter，只留 PushplusAdapter；workflow 同步删 WECOM/FEISHU secrets。
- **教训**：接第三方服务前先查清它的**聚合/转发能力**，别把「下游渠道」误当「独立接入点」。pushplus 的 channel 枚举：wechat/webhook/cp/mail/app/qq 等。

### 2. push_all 结果键碰撞
- 所有 PushplusAdapter 的 `channel` 类属性都是 "pushplus"，多下游（微信+飞书）时 `results[adapter.channel]` 键互相覆盖。改用 `send_channel[:option]` 作 key 区分下游。

### 3. 关键词收窄 + Agent2 相关性过滤（堵垃圾站 SEO）
- 关键词「合规」「分布式」太宽泛，检索出金融/证券/药品合规 + 博彩垃圾（`ttplus.cn` 等用 SEO 蹭「数据合规」词）。
- 收窄：`合规`→`数据存储`、`分布式`→`分布式存储`、补 `闪存存储`；黑名单 +`ttplus.cn`。
- Agent2 提炼时加 `relevant` 字段（单次 LLM 调用同时判断相关性+提炼，**fail-open**：仅 strict `is False` 丢弃）。效果：**21 篇含 8 噪声 → 5 篇全相关**。
- **教训**：纯关键词检索必被 SEO 蹭词，要在提炼环节加「主题相关性」LLM 判断（治本，比加黑名单更根本）。

### 4. 双标签（industry/vertical）
- 前端页面有「产业标签」（闪存/分布式/数据保护）+「行业标签」（金融/医疗/制造/零售/政府/运营商）。Agent2 补这两个字段（与 relevant **同一次 LLM 调用**输出，英文枚举直接映射前端 data-* 属性）。

### 5. Agent6 render_html 复用前端模板（主人纠正）
- 之前 render_html **另起炉灶写简陋卡片模板**，完全没用仓库根 `eu-storage-daily-*.html` 设计稿（1037 行成品：双标签/四段式/暗色模式/筛选器/折叠 JS）。
- 纠正：render_html 用 `Path.glob` 读取设计稿模板文件，用 `_CONTENT_MARKER`/`_FOOTER_MARKER` 定位内容区，替换卡片 + 填充四大分类/双标签/四段式/历史回溯/主题色，保留完整 CSS+JS。
- **教训（重要）**：项目里**已有的设计稿/原型，实现时必须复用，别让 dev 另起炉灶**。orchestrator 拆「渲染」类 slice 前，先确认「是否已有设计稿/前端原型」。

### 6. 转 public + Pages 发布 + 推送打通
- GitHub Free plan 不支持 private repo Pages（422）→ 主人授权**转 public**（secrets 仍加密安全），Pages 源 main `/docs`，发布到 `https://happydayeach.github.io/AI_storage_daily_push_system/`。
- pushplus 推送三连坑：code 905（未实名，去 verify.pushplus.plus）→ code 999（未关注「pushplus 推送加」公众号）→ http 明文（改 https）。
- **教训**：本地跑 main.py 生成的 `docs/index.html` 是**未 commit** 的，Pages 发布的是 origin/main 的旧版；生成产物要及时 commit+push（或依赖 workflow 的 commit 步）。验证 Pages 时用 `curl | grep data-industry` 确认真是双标签版。

### 7. QA bug（待修）
- Agent5 对 update 事件误查四段（`analysis_template_sections`），但 Agent4 对 update 只产出「新进展」单段 → 4 篇 update 被误判 issues。待修：update 改查「新进展」段（QA 不阻断渲染推送，故功能正常，仅质检数字不准）。

### 本轮测试 & 提交
- 测试累计 **45 passed** 全绿。关键 commit：4e0d95a(Agent6 返工)、aa43fd1/9794100(Agent7 聚合)、d14f661(相关性过滤)、ce83f9b(双标签)、db0157f(前端复用)、3fe722c(生成产物)。

## 2026-09-13 深夜：配置化重构完成（多主题复用，换主题零改代码）

### 成果
- T0 + C1(含返工) + C2~C8 全绿，测试 **45 → 64 passed**。
- 核心：换主题 = 新建一个 `theme_<主题>.yaml` + 改 `THEME` 环境变量，**代码零改动**（C8 用 `git diff` 证明只动了 config/ + tests/，未碰任何 src/*.py）。
- 主人约定：以后说「换主题」→ 新建 config，不改代码（记忆已存）。

### 关键设计（config_loader）
- `load_theme_config(theme_id)` 读 yaml + `resolve()` 补默认值兜底 + 便捷 getter（get_categories/get_industries/get_verticals/get_sections/get_event_types）。
- 14 处硬编码 → config：industries/verticals/region/relevance_theme/theme_name/event_types/update_section_name/template_glob/categories(带 id+icon)。
- 各模块 config 化：agent2 prompt 动态生成、agent4 system_prompt 主题化、agent6 标签/section/模板、agent1 region 前置、agent5 QA update 段名、main THEME 参数化。

### 教训（重要，拆卡 scope 相关）
1. **config_loader getter 必须幂等 resolve**：C1 初版 `get_sections` 直接 `config.get(...)` 漏了 resolve，且 resolve 默认值表漏了 analysis_template_sections → 到 C2 调用时才暴露。铁律：getter 一律 `resolve(config)[key]`。
2. **改函数签名要把连锁影响写进 scope**：C3 改 `process_articles` 加 theme_config，漏了 test_main.py 的 monkeypatch（两参数 lambda）→ dev block。拆卡时 spec 要么列全「签名变更的连锁测试」，要么明确「授权顺带修连锁测试」。
3. **拆卡 scope 边界要留「顺带修复」授权**：C2/C3 dev 都因「修复需超出 spec 允许的文件范围」而 block。给 dev 卡加一句「若发现前置依赖缺陷需超出本卡文件范围修复，先 block 报 orchestrator 而非硬绕过」。
4. **sync_project.sh backup 误判**：dev 自行 commit 后，backup 可能误判「无变更可提交」跳过 push。评审通过后必须核对 `git rev-parse HEAD` vs `origin/main`，不一致手动 `git push` 兜底。




