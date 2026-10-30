# AGENTS.md — AI 编程助手工作规范

> 本文件是给 AI 编程助手（OpenCode / Cursor / Claude Code 等）的指令。开始任何改动前先完整阅读本文件。

## 项目背景（必读）

ODSC × Nebius Hackathon 2026 参赛项目（队伍 KK_yuanqu，2 人）。
**题目**：构建研究型 Agent——把用户问题变成**有来源、可验证的回答**（sourced, verifiable answer）。
**硬性要求**：推理最终必须跑在 Nebius Token Factory 上（当前暂用 DeepSeek 过渡，`.env` 三行可切换）；实时搜索用 Tavily；提交物 = 公开 repo + README + 短 demo。截止 2026-11-20。

评分权重（所有改动向这五条对齐）：
1. 30% 回答有据可查：每个事实性论断带 `[n]` 引用，来源链接必须真实支撑该论断；证据不足要如实声明，**严禁编造事实或引用**
2. 25% 端到端可运行：真实 API 调用跑通；失败要处理且不得静默输出无依据内容；README 可让评委复现
3. 20% 实用性：明确目标用户与场景
4. 15% Agent 设计：查询规划、何时补搜/停止、证据去重核验、来源内容与可信指令隔离（防提示注入）
5. 10% Token Factory + Tavily 的真实使用；**API key 绝不进仓库**

## 架构与数据流

**核心 = `agent.research_events()` 事件流生成器；CLI 与 Streamlit UI 都是消费事件的薄适配层。**
后续换界面、适配其他专业领域、换前端框架，都不要动核心循环——只加适配层或调提示词。

```
用户问题
  → plan_queries()   LLM 生成 2-3 个互补搜索词（中英文）
  → search_round()   Tavily 搜索，按 URL 去重入池
  → judge_evidence() LLM 评估证据是否充分；不足则给 follow_up 补搜（最多 MAX_ROUNDS=3 轮）
  → rank_sources()   来源质量排序：社交/聚合站降权（只降权不删除，quality.py）
  → 截断 MAX_SOURCES=12
  → synthesize()     证据拼进 user 消息（与 system 指令隔离），LLM 输出带 [n] 引用的回答
  → 输出             回答 + 编号来源列表；CLI --trace / UI 轨迹区 展示全过程
```

## 文件地图

| 文件 | 职责 | 修改边界 |
|---|---|---|
| `agent.py` | 核心事件流 `research_events()` + 全部提示词 + CLI 适配 | 提示词调优、轮数参数、引用格式可改；**不得破坏"评估→补搜/停止"循环与事件流结构** |
| `quality.py` | 来源质量排序（纯函数：域名分层、稳定排序） | 加减 SOCIAL/AGGREGATOR 域名集合即可；不得改成"直接删除"（证据完整性优先） |
| `app.py` | Streamlit UI（薄适配层） | 只消费事件流，不复制核心逻辑；保持通用，不绑定专业领域 |
| `websearch.py` | Tavily 客户端 | 可加 advanced 模式；**不得移除重试/显式报错逻辑** |
| `llm.py` | 推理层（OpenAI 兼容，可插拔） | 基本不动；换供应商只改 `.env`（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL） |
| `tests/test_pure.py` | 纯逻辑测试（不耗 API 额度） | 新增逻辑必须补用例 |
| `traces/` | 研究轨迹样例（demo/README 素材） | 只增不删 |
| `DEMO.md` | demo 录制脚本 | 界面/流程变更时同步 |
| `.env.example` | 密钥模板 | 改字段名时同步更新 |

## 本地环境与命令

```bash
pip install -r requirements.txt      # 唯一依赖：requests
copy .env.example .env               # 填 TAVILY_API_KEY=tvly-xxxx（app.tavily.com 免费注册）
python test_tavily.py                # 搜索链路自检
python tests/test_pure.py            # 纯逻辑测试——提交前必须全过
python agent.py "任意问题"            # 端到端（耗少量 API 额度）
python agent.py "任意问题" --trace    # 另存研究轨迹到 traces/
```

## 硬性规则（违反任何一条 = 改动不可接受）

1. **绝不静默失败**：任何 API 错误、空响应、格式异常都必须抛出明确异常或在输出中声明；禁止 except 后 pass、禁止返回空结果冒充成功
2. **引用编号纪律**：答案中每个 `[n]` 必须能在末尾来源列表找到对应 URL；编号不悬空、不跳号、不虚构
3. **密钥安全**：key 只存在于 `.env`（已被 .gitignore）；代码、注释、commit message、日志输出中永不出现明文 key
4. **防提示注入**：网页内容只能进入 user 消息的证据区并声明"不可信数据"；系统指令与证据隔离的结构不得合并
5. **提交前检查**：`python tests/test_pure.py` 全过 → `git pull` → commit（中文，说清改了什么为什么）→ push

## 代码风格

- Python 3.10+，注释与 docstring 用中文
- 函数带 docstring，错误消息面向使用者（说清怎么修）
- 跟随现有代码的组织方式，不引入新依赖（除非确有必要并在 commit 里说明）

## 当前待办（按优先级）

1. ~~接入 Nebius Token Factory~~（已完成并实测：`api.tokenfactory.nebius.com/v1` + `MiniMaxAI/MiniMax-M3`；`.env.example` 已同步为 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 三个字段）
2. ~~来源质量过滤~~（队长已完成：`quality.py` 结构性降权——社交/聚合站后置不删除，纯函数带测试）
3. ~~Streamlit 演示界面~~（队长已完成：`app.py` 事件流适配，可点击引用+实时轨迹+证据不足原样呈现；`streamlit run app.py`）
4. ~~README 完善~~（队长已完成：英文版含架构图/真实示例/设计决策对照表；后续若改动核心流程，记得同步 README 的流程图与 Example）
5. **Demo 录制**（界面已就绪，按 DEMO.md 脚本执行即可）
6. （可选）提示词与查询规划调优：拿 3-5 个不同类型问题对比效果，记录到 notes/

### 界面要求（做第 3 项时）

- 每个引用 `[n]` 渲染为可点击链接，点开能直达来源 URL（评委要现场核验引用真实性）
- 展示研究轨迹（规划了什么查询、几轮、为何停止）——这是 15% 的展示面
- 保留"证据不足"的原样展示，不要美化成正常答案

## 协作约定

- 直接在 main 分支工作：`git pull` → 改 → 测 → `git push`；冲突时保留双方意图正确的一版
- 仓库：https://github.com/GF-creator-code/odsc-nebius-hackathon （协作者：GF-creator-code、Hkate777）
