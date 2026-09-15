# AI_storage_daily_push_system 打结记录

> 打结时间：2026-09-15 22:55
> 状态：推送排版方向待定（用户要「前端排版 + 四段式可折叠」，正在讨论 CSS 精简方案）

## 一、关键记号：30 篇完整正文版本

**commit `ba4a54e`**（本地 tag `full-content-30reports`）：
- 内容：`render_push_message` 生成完整正文（标题 + 标签索引 + 📋一段话总结 + 四段式全展开 + 📄原文），**无 max_reports 限制，30 篇全推**。
- 用户评价：「内容完整」，是「能输出 30 篇的那个」。
- 缺陷：30 篇完整正文 > pushplus 2 万字硬上限 → 推送被拒（code 999「发送内容过大」）。
- 保留原因：内容完整，作为回退/对比基线。

## 二、当前版本（b0b1bbf）

- `render_push_message` 加 `max_reports`（默认 10，config 可配 `push_max_reports`），只推前 10 篇完整正文。
- 实测：10 篇 = 15286 字符 < 2 万，pushplus 推送成功（wechat: True）。
- 但用户不满意：**丢了前端排版，四段式全展开、不能收缩，纯文本无排版**。

## 三、待讨论：推送排版方案（用户新需求，未动工）

用户要的推送效果：
- 每篇：标题 + 一段话总结（默认可见）+ 四段式（**默认收缩，点开才展开**）。
- 有**排版**（卡片式，不是 `<b>`+`<br>` 裸文本）。

技术约束（关键）：
1. 完整前端（含整套 CSS/JS）= 28901 字 > 2 万字，pushplus 拒收 → 「原样全推前端」走不通。
2. 前端四段式折叠靠 JS（`toggleCard`），pushplus 短消息页面**大概率不执行 JS** → 折叠须改用原生 `<details>/<summary>` 标签。
3. CSS 要「精简」——只留卡片排版必需样式，砍掉响应式/动画/hover 等，控制总量 < 2 万字。

待确认（用户）：前端格式是否照搬 `eu-storage-daily` 卡片设计，还是按「标题+摘要可见、四段式折叠」重做简洁排版。

## 四、遗留待办（非阻塞）

1. pytest 污染 docs/index.html（卡 t_7ebc8692，未处理）。
2. 渲染与去重耦合（手动重跑前需清 story_store）。
3. review_tmp/ 有探针残留（probe_push_fix.py 等），收尾时清理。

## 五、关键 commit 链

`af0a149`(9-14 daily) → `547a3aa`(9-15 daily) → `ba4a54e`(完整正文30篇，tag full-content-30reports) → `bc41e93`(docs) → `92570ac`(9-15 daily) → `b0b1bbf`(max_reports 默认10)

## 六、机制备忘

- pushplus `/send` 返回 shortCode；shortMessage 详情页 = `pushplus.plus/shortMessage/<shortCode>`。
- pushplus content 2 万字硬上限，超则 code 999 拒收（非自动转短消息）。
- 微信渠道 content 长 → 短消息，点开看全文；前提是 content ≤ 2 万字。
