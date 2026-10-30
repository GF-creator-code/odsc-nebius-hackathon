# Demo 录制脚本（评分 25% + 30% 的展示面）

> 目标时长 2-3 分钟。评委明确要看到：①完整真实调用链路 ②回答+来源引用现场核验 ③**一个证据不足/失败案例**（不许剪掉）。
> 录制时机：Streamlit 界面完成后（界面未就绪前可用 `python agent.py --trace` 命令行先彩排）。

## 开场（约 15 秒）

画面：界面首屏（或终端）
口播（英文，面向国际评委）：
> "This is Sourced, a research agent that answers questions with evidence you can verify. Watch the full pipeline run live — no prewritten answers."

**要露出的点**：输入框为空、干净首屏；如果是命令行，先敲 `python agent.py "..." --trace` 让轨迹同步可见。

## 场景 1：时效性问题——展示完整循环（约 60-90 秒）

问题（示例，可换）：**"What won the 2026 Nobel Prize in Physics, and for what work?"**

录制要点（按顺序）：
1. 输入问题 → 点研究 → **研究轨迹区实时滚动**：规划出的 2-3 个查询 → 第 1 轮新增 N 条 → "证据充分，停止搜索"的判定理由
2. 回答渲染完成 → **滚动到引用**：指出回答中的 `[n]` 与底部来源列表一一对应
3. **关键动作：当场点开 1-2 个引用链接**（评委会核验引用是否真实支撑论断——nobelprize.org 官方页最佳）
4. 指出回答里的"限定段"（例如：获奖理由中的"发现"指发现高能中微子本身，而非确定其天体源），口播：
   > "It also tells you where evidence is indirect — that limitation is part of the answer."

## 场景 2：证据不足案例（约 30-45 秒）★必录

问题（选一个真搜不到充分证据的，提前试好，例如极小众的未公开信息）：
- 候选："某特定内部项目的未公开技术细节" / "某个尚未公布的具体数字"

录制要点：
1. 提问 → 轨迹显示多轮补搜（这里正好展示"何时细化搜索"）
2. 最终输出"【证据不足】…"及缺口说明
3. 口播：
   > "When the evidence isn't there, it says so and explains what's missing. It never fabricates sources."
4. （如果补搜轮触发了 Tavily 报错路径，留住不剪：展示错误被明确处理而非静默）

## 场景 3：防注入设计（约 20 秒，加分项）

口播 + 画面切到代码 `agent.py` 的 `synthesize()`：
> "Web content is injected as untrusted data, isolated from system instructions — a source page can't hijack the agent."

（可提前在测试问题里埋一个含指令的页面，若现场演示风险大，就用代码讲解代替。）

## 收尾（约 10 秒）

口播：
> "Plan, search, judge, answer — with every claim sourced. Repo link in the description."

画面：仓库首页（README 架构图）停留 2 秒。

## 录制清单

- [ ] OBS/PowerPoint 录屏，1080p，鼠标指针放大
- [ ] 浏览器提前登录无痕窗口（避免自动补全/个人痕迹入镜）
- [ ] `.env` 与任何 key 明文**绝不入镜**（终端演示时注意环境变量回显）
- [ ] 提前跑一遍两个问题，确认额度够（Tavily 每月 1000 次）、网络稳
- [ ] 轨迹文件 `traces/` 已有真实样例，README 已链接，可作为备用素材剪入
- [ ] 英文字幕/口播；时长超 3 分钟就砍场景 3
