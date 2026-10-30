"""LLM 推理客户端（可插拔）

默认端点为 Nebius Token Factory（OpenAI 兼容），可用 .env 覆盖：
    LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1
    LLM_API_KEY=<nebius key>
    LLM_MODEL=MiniMaxAI/MiniMax-M3
未设置 LLM_API_KEY 时回退读取 OpenCode 登录文件（本地开发便利）。
其余代码零改动。


加固点：
- 瞬时失败（网络/429/5xx）指数退避重试，最多 2 次；鉴权错误快速失败
- content 为 None（部分模型工具调用场景）显式报错，不返回空串冒充答案
- requests.Session 连接复用
"""

import json
import os
import time

import requests

TIMEOUT = 120
DEFAULT_BASE = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "MiniMaxAI/MiniMax-M3"
RETRIES = 2
BACKOFF = (2, 5)

# OpenCode 登录文件：key 已在本机，避免明文复制到处散落
OPENCODE_AUTH = os.path.expanduser("~/.local/share/opencode/auth.json")

_session = requests.Session()


class LLMError(RuntimeError):
    pass


def load_env(path: str = None) -> None:
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _opencode_key() -> str:
    try:
        with open(OPENCODE_AUTH, encoding="utf-8") as f:
            return json.load(f)["opencode"]["key"]
    except Exception:
        return ""


def chat(messages: list, model: str = None, temperature: float = 0.2) -> str:
    """OpenAI 兼容 chat completions，返回首条回复文本。失败抛 LLMError，绝不静默。"""
    load_env()
    base = os.environ.get("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")
    key = os.environ.get("LLM_API_KEY", "").strip() or _opencode_key()
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if not key:
        raise LLMError("无 LLM key：设置 LLM_API_KEY，或登录 OpenCode 以便自动读取")

    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            resp = _session.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "temperature": temperature},
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            last_err = f"LLM 网络请求失败：{e}"
            if attempt < RETRIES:
                time.sleep(BACKOFF[attempt])
                continue
            raise LLMError(last_err) from e

        if resp.status_code in (401, 403):
            raise LLMError("LLM key 无效（401/403）")
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"LLM 限流/服务端错误（{resp.status_code}）"
            if attempt < RETRIES:
                time.sleep(BACKOFF[attempt])
                continue
            raise LLMError(last_err)
        if resp.status_code != 200:
            raise LLMError(f"LLM 返回 {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM 响应格式异常: {resp.text[:200]}") from e
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                "LLM 返回空内容（content 为 None/空）——"
                "可能是模型走了工具调用分支或被安全拦截，请重试或换模型"
            )
        return content
    raise LLMError(last_err or "LLM 未知错误")  # 逻辑上不可达，防御性保留
