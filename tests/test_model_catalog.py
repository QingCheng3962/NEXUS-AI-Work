"""模型自动检测的纯函数测试。"""

from core import model_catalog


def test_parse_openai_models() -> None:
    models = model_catalog.parse_models(
        {
            "object": "list",
            "data": [
                {
                    "id": "model-a",
                    "name": "Model A",
                    "context_window": 128000,
                    "max_output_tokens": 8192,
                },
                {"id": "model-b"},
                {"id": "model-a", "name": "duplicate"},
            ],
        }
    )
    assert [item["id"] for item in models] == ["model-a", "model-b"]
    assert models[0]["name"] == "Model A"
    assert models[0]["context_window"] == 128000
    assert models[1]["name"] == "model-b"


def test_parse_models_accepts_plain_list() -> None:
    assert model_catalog.parse_models(["alpha", "beta"]) == [
        {
            "id": "alpha",
            "name": "alpha",
            "context_window": 0,
            "max_output_tokens": 0,
        },
        {
            "id": "beta",
            "name": "beta",
            "context_window": 0,
            "max_output_tokens": 0,
        },
    ]


def test_model_endpoint_candidates() -> None:
    default = model_catalog._endpoint_candidates("")
    assert default[0] == "https://api.deepseek.com/models"

    custom = model_catalog._endpoint_candidates("https://example.com/anthropic")
    assert custom[0] == "https://example.com/models"

    v1 = model_catalog._endpoint_candidates("https://example.com/v1")
    assert v1[0] == "https://example.com/v1/models"


def test_detect_models_uses_discovered_list(monkeypatch) -> None:
    monkeypatch.setattr(model_catalog, "api_key", lambda: "test-key")
    monkeypatch.setattr(
        model_catalog,
        "_request_models",
        lambda endpoint, key, token="": [{"id": "detected", "name": "Detected"}],
    )
    models = model_catalog.detect_models("https://example.com/anthropic")
    assert models[0]["id"] == "detected"


def test_select_options_maps_ids_to_labels() -> None:
    options = model_catalog.select_options(
        [{"id": "m1", "name": "Model One"}, {"id": "m2", "name": "Model Two"}]
    )
    assert options == {"m1": "Model One", "m2": "Model Two"}
