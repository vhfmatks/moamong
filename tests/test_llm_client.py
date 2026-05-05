from __future__ import annotations

import requests
import pytest

from moamong_app.llm_client import (
    LlmResponseError,
    ModelTestResult,
    OpenAICompatibleClient,
    fetch_available_models,
    parse_generated_row,
    parse_generated_product_keywords,
    parse_site_search_keyword,
    test_chat_model,
    test_embedding_model,
    test_llm_models,
)
from moamong_app.models import Category, CategoryCandidate, LlmSettings, ProductRow


def test_parse_generated_row_accepts_valid_json() -> None:
    generated = parse_generated_row(
        """
        {
          "product_name": "얼굴배게",
          "keywords": ["얼굴베개", "마사지쿠션"],
          "mycate": "WB100",
          "mycate_name": "마사지용품",
          "confidence": 0.91
        }
        """
    )

    assert generated.product_name == "얼굴배게"
    assert generated.keywords == ["얼굴베개", "마사지쿠션"]
    assert generated.mycate == "WB100"
    assert generated.mycate_name == "마사지용품"
    assert generated.confidence == 0.91
    assert generated.raw_response.strip().startswith("{")


def test_parse_generated_product_keywords_accepts_category_free_json() -> None:
    generated = parse_generated_product_keywords(
        """
        {
          "product_name": "얼굴전용 마사지 베개",
          "keywords": ["얼굴베개", "마사지얼굴베개"],
          "review_reason": "사이트 추천어를 반영했습니다."
        }
        """
    )

    assert generated.product_name == "얼굴전용 마사지 베개"
    assert generated.keywords == ["얼굴베개", "마사지얼굴베개"]
    assert generated.mycate == ""
    assert generated.mycate_name == ""
    assert generated.confidence == 1.0
    assert generated.review_reason == "사이트 추천어를 반영했습니다."


def test_parse_site_search_keyword_accepts_valid_json() -> None:
    keyword = parse_site_search_keyword(
        """
        {
          "search_keyword": "스프레이건 거치대",
          "alternatives": ["변기 스프레이건", "화장실 스프레이건"],
          "review_reason": "핵심 물건명을 유지했습니다."
        }
        """
    )

    assert keyword == "스프레이건 거치대"


def test_parse_generated_row_rejects_missing_required_fields() -> None:
    with pytest.raises(LlmResponseError, match="missing required field"):
        parse_generated_row(
            """
            {
              "product_name": "얼굴배게",
              "keywords": ["얼굴베개"],
              "mycate": "WB100",
              "confidence": 0.91
            }
            """
        )


def test_client_rejects_category_outside_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "product_name": "얼굴배게",
                              "keywords": ["얼굴베개", "마사지쿠션"],
                              "mycate": "WB999",
                              "mycate_name": "없는 카테고리",
                              "confidence": 0.91
                            }
                            """
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured_payload.update(kwargs["json"])
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)
    client = OpenAICompatibleClient(LlmSettings(api_key="test", retry_count=0))
    row = ProductRow(index=0, values={"상품명": "얼굴배게"})
    candidates = [CategoryCandidate(Category("WB100", "생활용품 > 침구 > 베개 >"), 1.0)]

    with pytest.raises(LlmResponseError, match="supplied candidates"):
        client.generate(row, candidates)
    user_message = captured_payload["messages"][1]["content"]
    assert "WB100" in user_message
    assert "얼굴배게" in user_message


def test_client_generates_product_keywords_without_category_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "product_name": "얼굴전용 마사지 베개",
                              "keywords": ["얼굴베개", "마사지얼굴베개"],
                              "review_reason": ""
                            }
                            """
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured_payload.update(kwargs["json"])
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)
    client = OpenAICompatibleClient(LlmSettings(api_key="test", retry_count=0))
    row = ProductRow(
        index=0,
        values={
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개",
            "마이카테": "WB100",
        },
    )

    generated = client.generate_product_keywords(
        row,
        {
            "coupang": ["얼굴베개", "마사지얼굴쿠션"],
            "naver": ["안면베개"],
        },
    )

    user_message = captured_payload["messages"][1]["content"]
    system_message = captured_payload["messages"][0]["content"]
    assert generated.product_name == "얼굴전용 마사지 베개"
    assert "Korean ecommerce SEO" in system_message
    assert "마사지샵 얼굴 쿠션 베개" in user_message
    assert "쿠팡" in user_message
    assert "얼굴베개" in user_message
    assert "판매량" in user_message
    assert "검색 노출" in user_message
    assert "구매 전환" in user_message
    assert "대표 키워드" in user_message
    assert "롱테일" in user_message
    assert "과장" in user_message
    assert "브랜드" in user_message
    assert "Candidate categories" not in user_message
    assert "마이카테" not in user_message


def test_client_generates_site_search_keyword_from_original_name(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "search_keyword": "하트 비즈",
                              "alternatives": ["비즈 부자재", "공예 비즈"],
                              "review_reason": ""
                            }
                            """
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured_payload.update(kwargs["json"])
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)
    client = OpenAICompatibleClient(LlmSettings(api_key="test", retry_count=0))
    row = ProductRow(
        index=0,
        values={
            "상품명": "기존 상품명",
            "원본상품명(참고용)": "공예용 하트모양 비즈 부자재 10p",
        },
    )

    keyword = client.generate_site_search_keyword(row)

    user_message = captured_payload["messages"][1]["content"]
    assert keyword == "하트 비즈"
    assert "공예용 하트모양 비즈 부자재 10p" in user_message
    assert "search_keyword" in user_message


def test_client_retries_without_response_format_when_model_does_not_support_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payloads = []

    class ResponseFormatErrorResponse:
        text = """
        {
          "error": {
            "message": "Invalid parameter: 'response_format' of type 'json_object' is not supported with this model.",
            "type": "invalid_request_error",
            "param": "response_format"
          }
        }
        """

        def raise_for_status(self) -> None:
            raise requests.HTTPError("400 Client Error: Bad Request", response=self)

    class SuccessResponse:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "product_name": "얼굴전용 마사지 베개",
                              "keywords": ["얼굴베개", "마사지얼굴베개"],
                              "review_reason": ""
                            }
                            """
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured_payloads.append(kwargs["json"])
        if len(captured_payloads) == 1:
            return ResponseFormatErrorResponse()
        return SuccessResponse()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)
    client = OpenAICompatibleClient(LlmSettings(api_key="test", model="gpt-4", retry_count=0))

    generated = client.generate_product_keywords(
        ProductRow(index=0, values={"원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개"}),
        {"naver": ["얼굴베개"]},
    )

    assert generated.product_name == "얼굴전용 마사지 베개"
    assert "response_format" in captured_payloads[0]
    assert "response_format" not in captured_payloads[1]


def test_client_error_includes_openai_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorResponse:
        text = """
        {
          "error": {
            "message": "The model `missing-model` does not exist or you do not have access to it.",
            "type": "invalid_request_error"
          }
        }
        """

        def raise_for_status(self) -> None:
            raise requests.HTTPError("400 Client Error: Bad Request", response=self)

    def fake_post(*args, **kwargs):
        return ErrorResponse()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)
    client = OpenAICompatibleClient(LlmSettings(api_key="test", model="missing-model", retry_count=0))

    with pytest.raises(LlmResponseError, match="missing-model"):
        client.generate_product_keywords(
            ProductRow(index=0, values={"원본상품명(참고용)": "마사지샵 얼굴 쿠션 베개"}),
            {"naver": ["얼굴베개"]},
        )


def test_fetch_available_models_categorizes_chat_and_embedding_models(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"id": "gpt-4.1-mini"},
                    {"id": "text-embedding-3-small"},
                    {"id": "custom-chat-model"},
                ]
            }

    def fake_get(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.get", fake_get)

    models = fetch_available_models(
        LlmSettings(
            base_url="https://llm.example.test/v1/",
            api_key="secret-key",
            timeout_seconds=12,
        )
    )

    assert captured["args"] == ("https://llm.example.test/v1/models",)
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["kwargs"]["timeout"] == 12
    assert models.llm_models == ["custom-chat-model", "gpt-4.1-mini"]
    assert models.embedding_models == ["text-embedding-3-small"]


def test_fetch_available_models_error_includes_openai_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorResponse:
        text = """
        {
          "error": {
            "message": "The API key is invalid for model listing.",
            "type": "invalid_request_error"
          }
        }
        """

        def raise_for_status(self) -> None:
            raise requests.HTTPError("401 Client Error: Unauthorized", response=self)

    def fake_get(*args, **kwargs):
        return ErrorResponse()

    monkeypatch.setattr("moamong_app.llm_client.requests.get", fake_get)

    with pytest.raises(LlmResponseError, match="API key is invalid"):
        fetch_available_models(LlmSettings(api_key="bad-key", retry_count=0))


def test_chat_model_posts_minimal_chat_completion_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "{\"ok\": true}"
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    content = test_chat_model(
        LlmSettings(
            base_url="https://llm.example.test/v1/",
            api_key="secret-key",
            model="chat-model",
            timeout_seconds=7,
            retry_count=0,
        )
    )

    assert content == "{\"ok\": true}"
    assert captured["args"] == ("https://llm.example.test/v1/chat/completions",)
    assert captured["kwargs"]["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
    }
    assert captured["kwargs"]["timeout"] == 7
    payload = captured["kwargs"]["json"]
    assert payload["model"] == "chat-model"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


def test_embedding_model_posts_embeddings_request_and_returns_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "index": 0,
                        "embedding": [0.1, 0.2, 0.3],
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    dimension = test_embedding_model(
        LlmSettings(
            base_url="https://llm.example.test/v1/",
            api_key="secret-key",
            embedding_model="embed-model",
            timeout_seconds=9,
            retry_count=0,
        )
    )

    assert dimension == 3
    assert captured["args"] == ("https://llm.example.test/v1/embeddings",)
    assert captured["kwargs"]["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
    }
    assert captured["kwargs"]["json"] == {
        "model": "embed-model",
        "input": ["테스트"],
    }
    assert captured["kwargs"]["timeout"] == 9


def test_embedding_model_rejects_malformed_embedding_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"index": 0, "embedding": []}]}

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    with pytest.raises(LlmResponseError, match="embedding response item is invalid"):
        test_embedding_model(LlmSettings(api_key="secret-key", retry_count=0))


def test_embedding_model_rejects_multiple_embedding_items(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                ]
            }

    def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr("moamong_app.llm_client.requests.post", fake_post)

    with pytest.raises(
        LlmResponseError,
        match="embedding response count does not match request",
    ):
        test_embedding_model(LlmSettings(api_key="secret-key", retry_count=0))


def test_llm_models_returns_combined_success_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(settings: LlmSettings) -> str:
        assert settings.model == "chat-model"
        return "{\"ok\": true}"

    def fake_embedding(settings: LlmSettings) -> int:
        assert settings.embedding_model == "embed-model"
        return 3

    monkeypatch.setattr("moamong_app.llm_client.test_chat_model", fake_chat)
    monkeypatch.setattr("moamong_app.llm_client.test_embedding_model", fake_embedding)

    result = test_llm_models(
        LlmSettings(
            model="chat-model",
            embedding_model="embed-model",
        )
    )

    assert result == ModelTestResult(
        chat_model="chat-model",
        embedding_model="embed-model",
        chat_ok=True,
        embedding_ok=True,
        chat_message="Received non-empty chat response",
        embedding_message="Received 3-dimension embedding",
    )


def test_llm_models_wraps_chat_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(settings: LlmSettings) -> str:
        raise LlmResponseError("chat denied")

    def fake_embedding(settings: LlmSettings) -> int:
        raise AssertionError("embedding test should not run")

    monkeypatch.setattr("moamong_app.llm_client.test_chat_model", fake_chat)
    monkeypatch.setattr("moamong_app.llm_client.test_embedding_model", fake_embedding)

    with pytest.raises(LlmResponseError, match="Chat model test failed: chat denied"):
        test_llm_models(LlmSettings(model="chat-model", embedding_model="embed-model"))


def test_llm_models_wraps_embedding_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(settings: LlmSettings) -> str:
        return "{\"ok\": true}"

    def fake_embedding(settings: LlmSettings) -> int:
        raise LlmResponseError("embedding denied")

    monkeypatch.setattr("moamong_app.llm_client.test_chat_model", fake_chat)
    monkeypatch.setattr("moamong_app.llm_client.test_embedding_model", fake_embedding)

    with pytest.raises(
        LlmResponseError,
        match="Embedding model test failed: embedding denied",
    ):
        test_llm_models(LlmSettings(model="chat-model", embedding_model="embed-model"))
