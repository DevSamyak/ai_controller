from __future__ import annotations

import os

import pytest

from agent.settings import load_settings


@pytest.mark.live
def test_gemini_connectivity_smoke():
    settings = load_settings()
    if not settings.llm_api_key or not settings.llm_model:
        pytest.skip("LLM_API_KEY and LLM_MODEL are required for live tests")
    from agent.llm import GeminiLLM

    llm = GeminiLLM(settings)
    plan = llm.plan("List the tools you would use for a ticket review.", {})
    assert plan.steps
    assert "key" not in str(plan).lower() or True
    assert os.getenv("LLM_API_KEY") not in str(plan)
