import pytest
from unittest.mock import patch, MagicMock
from llm_fallback import FallbackLLM, get_fallback_llm

def test_fallback_llm_success_first_try():
    """Verify that if the first model succeeds, its response is returned."""
    mock_llm_1 = MagicMock()
    mock_llm_1.call.return_value = "Response from model 1"

    with patch("llm_fallback.LLM", return_value=mock_llm_1):
        fallback = FallbackLLM(["model-1", "model-2"])
        result = fallback.call([{"role": "user", "content": "hi"}])
        assert result == "Response from model 1"
        assert mock_llm_1.call.call_count == 1

def test_fallback_llm_failover():
    """Verify that when model 1 raises an error, model 2 is automatically called."""
    mock_llm_1 = MagicMock()
    mock_llm_1.call.side_effect = Exception("HTTP 429 Rate Limited")

    mock_llm_2 = MagicMock()
    mock_llm_2.call.return_value = "Response from fallback model 2"

    def side_effect(model, **kwargs):
        if "model-1" in model:
            return mock_llm_1
        return mock_llm_2

    with patch("llm_fallback.LLM", side_effect=side_effect):
        fallback = FallbackLLM(["model-1", "model-2"])
        result = fallback.call([{"role": "user", "content": "hi"}])
        assert result == "Response from fallback model 2"
        mock_llm_1.call.assert_called_once()
        mock_llm_2.call.assert_called_once()

def test_fallback_llm_all_fail():
    """Verify that RuntimeError is raised only if all candidates fail."""
    mock_llm_fail = MagicMock()
    mock_llm_fail.call.side_effect = Exception("Outage 503")

    with patch("llm_fallback.LLM", return_value=mock_llm_fail):
        fallback = FallbackLLM(["model-1", "model-2"])
        with pytest.raises(RuntimeError, match="All models in the fallback sequence failed"):
            fallback.call([{"role": "user", "content": "hi"}])
