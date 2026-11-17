"""UI smoke test: run app.py for real via Streamlit's official AppTest (purely local;
no API calls are triggered)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import llm  # noqa: E402

# The sidebar shows the "actually effective config" (app.py calls llm.load_env() at startup
# before reading the environment). Assertions compute the same way dynamically, so the model
# name is never hardcoded -- switching .env must not break this test.
llm.load_env()
EXPECTED_BASE = os.environ.get("LLM_BASE_URL", llm.DEFAULT_BASE)
EXPECTED_MODEL = os.environ.get("LLM_MODEL", llm.DEFAULT_MODEL)

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_app_starts_clean():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30)
    at.run()
    assert not at.exception, f"app.py failed to start: {at.exception}"
    assert at.title[0].value == "Sourced"
    # Sidebar always shows the inference endpoint and model (on-screen self-attestation for
    # the "real Nebius usage" scoring item)
    sidebar_code = " ".join(e.value or "" for e in at.sidebar.code)
    assert EXPECTED_BASE in sidebar_code, f"sidebar missing current endpoint {EXPECTED_BASE}"
    assert EXPECTED_MODEL in sidebar_code, f"sidebar missing current model {EXPECTED_MODEL}"
    # Home page: 1 text input + research button + 3 example questions
    assert len(at.text_input) == 1
    assert len(at.button) >= 4


if __name__ == "__main__":
    test_app_starts_clean()
    print("[ok] UI smoke test passed")
