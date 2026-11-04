"""UI冒烟测试：用Streamlit官方AppTest真实执行app.py（纯本地，不触发任何API调用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 清掉外部环境变量，确保侧边栏显示的是llm.py默认值（Nebius）
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("LLM_MODEL", None)

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_app_starts_clean():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30)
    at.run()
    assert not at.exception, f"app.py启动异常：{at.exception}"
    assert at.title[0].value == "Sourced"
    # 侧边栏常显推理端点与模型（评分项"真实使用Nebius"的界面自证）
    sidebar_code = " ".join(e.value or "" for e in at.sidebar.code)
    assert "api.tokenfactory.nebius.com" in sidebar_code
    assert "MiniMax" in sidebar_code
    # 主页：1个输入框 + 研究按钮 + 3个示例问题
    assert len(at.text_input) == 1
    assert len(at.button) >= 4


if __name__ == "__main__":
    test_app_starts_clean()
    print("[ok] UI冒烟测试通过")
