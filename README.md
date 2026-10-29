# ODSC × Nebius Hackathon — KK_yuanqu

题目：构建把问题变成**有来源、可验证回答**的研究型 Agent。
- 推理：Nebius Token Factory（待配置）
- 搜索：Tavily（本目录已就绪）

## 配置步骤

1. `cp .env.example .env`（Windows: `copy .env.example .env`）
2. 到 [app.tavily.com](https://app.tavily.com) 注册（免费，无需信用卡），控制台复制 `tvly-` 开头的 key，填入 `.env` 的 `TAVILY_API_KEY=`
3. 验证：`python test_tavily.py` —— 应打印综合答案 + 3 条带链接来源

## 快速开始

```bash
pip install -r requirements.txt   # 目前仅依赖 requests
copy .env.example .env            # Linux/macOS 用 cp；然后填入自己的 TAVILY_API_KEY
python test_tavily.py             # 验证搜索链路：应打印综合答案 + 3 条带链接来源
python agent.py "你的研究问题"      # 端到端：带 [n] 引用的回答 + 来源列表
```

## 项目结构
- `agent.py` — 研究主体：规划检索 → Tavily 取证（按 URL 去重）→ LLM 综合 → 带引用回答
- `websearch.py` — Tavily 客户端（`get_client().search(query)`）
- `llm.py` — 可插拔推理层（`.env` 三行即可切换供应商）
- `test_tavily.py` — 搜索链路自检
- `.env.example` — 密钥模板；`.env` 被 gitignore，**key 绝不进仓库**（评分硬性要求）

## 提交物（2026-11-20 截止）
公开仓库 + README（安装运行步骤、架构概览、研究轨迹）+ 短 demo（真实 API 调用，含一个证据不足案例）
