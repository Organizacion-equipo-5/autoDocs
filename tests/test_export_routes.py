import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from routes.export import _prepare_documentation_results
from services.ai_enhancer import AIEnhancer


def test_export_enriches_and_caches_full_results_before_selection():
    original_results = {
        "functions": [{"name": "first"}, {"name": "second"}],
        "classes": [],
        "endpoints": [],
    }
    analysis_result = {"results": original_results}
    db = SimpleNamespace(analysis_results=MagicMock())

    def enrich(results, output_language):
        results.update({
            "ai_documentation_enhanced": True,
            "ai_output_language": output_language,
            "ai_documentation_version": AIEnhancer.DOCUMENTATION_VERSION,
        })
        return results

    with patch("routes.export.AIEnhancer") as mock_ai_type:
        mock_ai_type.DOCUMENTATION_VERSION = AIEnhancer.DOCUMENTATION_VERSION
        mock_ai = mock_ai_type.return_value
        mock_ai.is_available.return_value = True
        mock_ai.enhance_documentation.side_effect = enrich

        selected_results = _prepare_documentation_results(
            db,
            "project-1",
            {},
            analysis_result,
            json.dumps({"functions": [1]}),
            "es",
        )

    assert [item["name"] for item in selected_results["functions"]] == ["second"]
    assert "ai_documentation_enhanced" not in original_results
    saved_results = db.analysis_results.update_one.call_args.args[1]["$set"]["results"]
    assert len(saved_results["functions"]) == 2
    assert saved_results["ai_documentation_enhanced"] is True
    mock_ai.enhance_documentation.assert_called_once()


def test_export_reuses_results_already_enriched_for_language():
    cached_results = {
        "functions": [{"name": "first", "ai_description": "Descripción"}],
        "ai_documentation_enhanced": True,
        "ai_output_language": "es",
        "ai_documentation_version": AIEnhancer.DOCUMENTATION_VERSION,
    }
    db = SimpleNamespace(analysis_results=MagicMock())

    with patch("routes.export.AIEnhancer") as mock_ai_type:
        mock_ai_type.DOCUMENTATION_VERSION = AIEnhancer.DOCUMENTATION_VERSION
        mock_ai_type.return_value.is_available.return_value = True
        result = _prepare_documentation_results(
            db, "project-1", {}, {"results": cached_results}, None, "es"
        )

    assert result["functions"][0]["ai_description"] == "Descripción"
    mock_ai_type.return_value.enhance_documentation.assert_not_called()
    db.analysis_results.update_one.assert_called_once()
