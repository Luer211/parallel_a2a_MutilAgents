---
# === 必需字段 ===
name: advanced-web-intelligence
description: >
  该技能用于执行深度的互联网信息检索与自动化交互。
  当用户需要：1) 获取实时新闻或特定知识；2) 从复杂网页提取清洗后的正文；
  3) 处理需要模拟人类点击、滚动或处理动态加载（SPA）的网页任务时使用。
  核心价值在于平衡了搜索的“速度（Serp+Jina）”与“深度（Browser-use）”。

# === 可选字段 ===
version: 1.1.0
allowed_tools: [serp_search, jina_reader, browser_executor]
required_context: [search_query, target_depth]
license: MIT
author: AI Engineer <dev@example.com>
tags: [search, scraping, automation, playwright]
---

# 深度网络搜索与交互技能 (Advanced Web Intelligence)

## 概述
本技能集成了两种互补的网络处理策略：
1. **轻量级检索路径**：利用 SerpAPI 获取搜索引擎结果，配合 Jina Reader 将 URL 转为干净的 Markdown。适用于 80% 的信息获取任务，速度快、Token 消耗低。
2. **重量级交互路径**：利用基于 Playwright 的 Browser-use 技术，模拟真实用户行为。适用于需要处理 JavaScript 渲染、翻页、点击特定按钮或处理反爬虫校验的复杂场景。

## 前置条件
* **SerpAPI Key**: 用于访问 Google/Bing 搜索结果。
* **Jina API**: 用于将 HTML 转化为 LLM 友好的 Markdown。
* **Playwright 环境**: 运行 Browser-use 代理的浏览器内核（Chromium）。
* **网络访问**: 确保运行环境具备访问目标网站的代理权限。

## 工作流程
智能体应遵循“先易后难”的原则执行任务：

1.  **意图识别**：判断用户是需要“查个资料”（轻量级）还是“去某网站帮我操作/订票/查动态数据”（重量级）。
2.  **执行轻量级路径**：
    * 调用 `serp_search` 获取候选 URL 列表。
    * 对高相关度 URL 调用 `jina_reader` 获取网页内容。
3.  **执行重量级路径（如有必要）**：
    * 若轻量级路径无法获取内容（如遇到：请开启 JS、验证码、单页应用渲染空白），则启动 `browser_executor`。
    * 通过视觉反馈或 DOM 树导航执行 `click`, `scroll`, `input` 等动作。
4.  **合成回答**：整合两路信息，给出最终结论并附带来源链接。

## 最佳实践
* **Token 节省**：优先使用 Jina Reader，因为它返回的是过滤掉 HTML 噪声的文本。
* **并发控制**：在进行 SerpAPI 搜索时，建议限制一次只读取前 3-5 个最相关的链接。
* **容错处理**：如果 Browser-use 陷入死循环（如由于弹窗阻挡），应设定最大步数（Max Steps）并强制退出。

## 示例
### 场景 A：查询最新 AI 论文
* **输入**：帮我总结一下昨天在 arXiv 上发布的关于 MoE 架构的新论文。
* **动作**：`serp_search` -> 找到链接 -> `jina_reader` 提取 -> 总结。

### 场景 B：获取动态金融数据
* **输入**：去某个特定交易所页面，帮我看看那个动态变化的 K 线图现在的价格。
* **动作**：`browser_executor` -> 导航至 URL -> 等待 Canvas/DOM 加载 -> 截图或提取特定 Element Text。

## 故障排查
* **Jina 返回 403/Forbidden**：说明目标网站封禁了简单爬虫，请切换至 `browser_executor` 并设置随机 User-Agent。
* **搜索结果不相关**：优化 `search_query`，尝试增加 `site:example.com` 等高级搜索指令。