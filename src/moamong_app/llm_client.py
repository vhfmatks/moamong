from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from moamong_app.keyword_fetcher import SITE_DISPLAY_NAMES
from moamong_app.models import CategoryCandidate, GeneratedRow, LlmSettings, ProductRow


class LlmResponseError(RuntimeError):
    """Raised when the LLM response cannot be used safely."""


@dataclass(frozen=True)
class AvailableModels:
    llm_models: list[str]
    embedding_models: list[str]
    all_models: list[str]


@dataclass(frozen=True)
class ModelTestResult:
    chat_model: str
    embedding_model: str
    chat_ok: bool
    embedding_ok: bool
    chat_message: str
    embedding_message: str


def fetch_available_models(settings: LlmSettings) -> AvailableModels:
    url = f"{settings.base_url.rstrip('/')}/models"
    headers = {}
    if settings.api_key.strip():
        headers["Authorization"] = f"Bearer {settings.api_key}"

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=settings.timeout_seconds,
        )
        _raise_for_status(response)
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LlmResponseError(f"model lookup failed: {exc}") from exc

    model_ids = _extract_model_ids(payload)
    if not model_ids:
        raise LlmResponseError("model lookup returned no usable model IDs")

    embedding_models = [
        model_id for model_id in model_ids if _looks_like_embedding_model(model_id)
    ]
    llm_models = [
        model_id for model_id in model_ids if model_id not in embedding_models
    ]
    return AvailableModels(
        llm_models=llm_models or model_ids,
        embedding_models=embedding_models or model_ids,
        all_models=model_ids,
    )


def test_llm_models(settings: LlmSettings) -> ModelTestResult:
    try:
        test_chat_model(settings)
    except LlmResponseError as exc:
        raise LlmResponseError(f"Chat model test failed: {exc}") from exc

    try:
        embedding_dimension = test_embedding_model(settings)
    except LlmResponseError as exc:
        raise LlmResponseError(f"Embedding model test failed: {exc}") from exc

    return ModelTestResult(
        chat_model=settings.model,
        embedding_model=settings.embedding_model,
        chat_ok=True,
        embedding_ok=True,
        chat_message="Received non-empty chat response",
        embedding_message=f"Received {embedding_dimension}-dimension embedding",
    )


def test_chat_model(settings: LlmSettings) -> str:
    if not settings.api_key.strip():
        raise LlmResponseError("API key is required for chat model test")
    if not settings.model.strip():
        raise LlmResponseError("chat model is required")

    payload = {
        "model": settings.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return only strict JSON."},
            {"role": "user", "content": "Return {\"ok\": true}."},
        ],
    }
    content = _chat_completion_content(settings, payload).strip()
    if not content:
        raise LlmResponseError("chat model test returned empty content")
    return content


def test_embedding_model(settings: LlmSettings) -> int:
    if not settings.api_key.strip():
        raise LlmResponseError("API key is required for embedding model test")
    if not settings.embedding_model.strip():
        raise LlmResponseError("embedding model is required")

    url = f"{settings.base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embedding_model, "input": ["테스트"]}

    last_error: Exception | None = None
    attempts = max(1, settings.retry_count + 1)
    for _ in range(attempts):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.timeout_seconds,
            )
            _raise_for_status(response)
            return len(_extract_single_embedding(response.json()))
        except (requests.RequestException, LlmResponseError, ValueError) as exc:
            last_error = exc

    raise LlmResponseError(f"embedding model test failed: {last_error}") from last_error


test_llm_models.__test__ = False
test_chat_model.__test__ = False
test_embedding_model.__test__ = False


def parse_generated_row(text: str) -> GeneratedRow:
    raw_response = text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmResponseError(f"invalid JSON response: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise LlmResponseError("response must be a JSON object")

    required_fields = [
        "product_name",
        "keywords",
        "mycate",
        "mycate_name",
        "confidence",
    ]
    for field in required_fields:
        if field not in data:
            raise LlmResponseError(f"missing required field: {field}")

    product_name = _required_string(data, "product_name")
    mycate = _required_string(data, "mycate")
    mycate_name = _required_string(data, "mycate_name")
    keywords = _required_keywords(data["keywords"])
    confidence = _required_confidence(data["confidence"])

    review_reason = data.get("review_reason", "")
    if review_reason is None:
        review_reason = ""
    if not isinstance(review_reason, str):
        raise LlmResponseError("review_reason must be a string")

    return GeneratedRow(
        product_name=product_name,
        keywords=keywords,
        mycate=mycate,
        mycate_name=mycate_name,
        confidence=confidence,
        review_reason=review_reason.strip(),
        raw_response=raw_response,
    )


def parse_generated_product_keywords(text: str) -> GeneratedRow:
    raw_response = text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmResponseError(f"invalid JSON response: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise LlmResponseError("response must be a JSON object")

    for field in ("product_name", "keywords"):
        if field not in data:
            raise LlmResponseError(f"missing required field: {field}")

    review_reason = data.get("review_reason", "")
    if review_reason is None:
        review_reason = ""
    if not isinstance(review_reason, str):
        raise LlmResponseError("review_reason must be a string")

    return GeneratedRow(
        product_name=_required_string(data, "product_name"),
        keywords=_required_keywords(data["keywords"]),
        review_reason=review_reason.strip(),
        raw_response=raw_response,
    )


def parse_site_search_keyword(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmResponseError(f"invalid JSON response: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise LlmResponseError("response must be a JSON object")

    keyword = data.get("search_keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise LlmResponseError("search_keyword must be a non-empty string")
    return keyword.strip()


class OpenAICompatibleClient:
    def __init__(self, settings: LlmSettings) -> None:
        self.settings = settings

    def generate(
        self,
        row: ProductRow,
        candidates: list[CategoryCandidate],
    ) -> GeneratedRow:
        prompt = _build_prompt(row, candidates)
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate strict JSON for Korean product category mapping."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

        content = _chat_completion_content(self.settings, payload)
        generated = parse_generated_row(content)
        return _validate_candidate_choice(generated, candidates)

    def generate_product_keywords(
        self,
        row: ProductRow,
        site_keywords: dict[str, list[str]],
    ) -> GeneratedRow:
        prompt = _build_product_keyword_prompt(row, site_keywords)
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Korean ecommerce SEO and conversion specialist. "
                        "Generate strict JSON for product names and search keywords."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

        return parse_generated_product_keywords(
            _chat_completion_content(self.settings, payload)
        )

    def generate_site_search_keyword(self, row: ProductRow) -> str:
        prompt = _build_site_search_keyword_prompt(row)
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate strict JSON for Korean ecommerce search keyword extraction."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

        return parse_site_search_keyword(_chat_completion_content(self.settings, payload))


def _chat_completion_content(settings: LlmSettings, payload: dict[str, Any]) -> str:
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    attempts = max(1, settings.retry_count + 1)
    for _ in range(attempts):
        current_payload = dict(payload)
        while True:
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=current_payload,
                    timeout=settings.timeout_seconds,
                )
                _raise_for_status(response)
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise LlmResponseError("message content must be a string")
                return content
            except LlmResponseError as exc:
                if (
                    "response_format" in current_payload
                    and _is_response_format_unsupported(exc)
                ):
                    current_payload = {
                        key: value
                        for key, value in current_payload.items()
                        if key != "response_format"
                    }
                    continue
                last_error = exc
                break
            except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = exc
                break

    raise LlmResponseError(f"LLM request failed: {last_error}") from last_error


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = _response_error_details(response)
        if details:
            raise LlmResponseError(f"{exc}; {details}") from exc
        raise LlmResponseError(str(exc)) from exc


def _response_error_details(response: requests.Response) -> str:
    text = getattr(response, "text", "")
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text.strip()

    if not isinstance(payload, dict):
        return text.strip()
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return text.strip()


def _is_response_format_unsupported(error: LlmResponseError) -> bool:
    message = str(error).lower()
    return "response_format" in message and (
        "not supported" in message or "unsupported" in message
    )


def _extract_single_embedding(payload: Any) -> list[float]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise LlmResponseError("embedding response must contain a data list")

    data = payload["data"]
    if not data:
        raise LlmResponseError("embedding response must contain at least one item")
    if len(data) != 1:
        raise LlmResponseError("embedding response count does not match request")

    item = data[0]
    if not isinstance(item, dict):
        raise LlmResponseError("embedding response item is invalid")

    embedding = item.get("embedding")
    if (
        not isinstance(embedding, list)
        or not embedding
        or any(
            isinstance(value, bool) or not isinstance(value, int | float)
            for value in embedding
        )
    ):
        raise LlmResponseError("embedding response item is invalid")

    return [float(value) for value in embedding]


def _build_prompt(row: ProductRow, candidates: list[CategoryCandidate]) -> str:
    candidate_lines = "\n".join(
        f"- {candidate.category.mycate}: {candidate.category.name} (score: {candidate.score:.3f})"
        for candidate in candidates
    )
    if not candidate_lines:
        candidate_lines = "- No candidates provided"

    return "\n".join(
        [
            "Return only a strict JSON object with keys: product_name, keywords, mycate, mycate_name, confidence, review_reason.",
            "Rules:",
            "- product_name must be the cleaned Korean product name.",
            "- keywords must contain 10-20 Korean search keywords.",
            "- keywords must be a non-empty JSON array of non-empty strings.",
            "- mycate must be selected only from the candidate category codes below.",
            "- mycate_name must match the selected candidate category name.",
            "- confidence must be a number from 0 to 1.",
            "",
            "Source row:",
            f"- 상품코드: {row.text('상품코드')}",
            f"- 상품명: {row.text('상품명')}",
            f"- 원본상품명(참고용): {row.text('원본상품명(참고용)')}",
            f"- 옵션명: {row.text('옵션명')}",
            f"- 키워드: {row.text('키워드')}",
            f"- 마이카테: {row.text('마이카테')}",
            "",
            "Candidate categories:",
            candidate_lines,
        ]
    )


def _build_product_keyword_prompt(
    row: ProductRow,
    site_keywords: dict[str, list[str]],
) -> str:
    site_lines = []
    for site, keywords in site_keywords.items():
        display_name = SITE_DISPLAY_NAMES.get(site, site)
        keyword_text = ", ".join(keyword for keyword in keywords if keyword.strip())
        site_lines.append(f"- {display_name}: {keyword_text or '(none)'}")
    if not site_lines:
        site_lines.append("- (none)")

    return "\n".join(
        [
            "Return only a strict JSON object with keys: product_name, keywords, review_reason.",
            "",
            "Business goal:",
            "- 상품명과 키워드는 판매량에 직접 영향을 준다.",
            "- Optimize for Korean shopping 검색 노출, click-through, and 구매 전환.",
            "- Use shopping-site suggestions as demand signals, not as text to copy blindly.",
            "",
            "Product name rules:",
            "- product_name must be a clean Korean store-facing product name.",
            "- Put the core product identity first, then the strongest use-case or buyer-intent phrase.",
            "- Include high-intent words naturally; do not make the title look like a keyword dump.",
            "- Prefer standard Korean spelling in product_name.",
            "- Do not invent unsupported 브랜드, model names, materials, sizes, medical effects, certifications, or specs.",
            "- Do not use exaggerated claims or 과장 expressions such as best, guaranteed, cure, official, premium unless the source proves them.",
            "",
            "Keyword rules:",
            "- keywords must contain 20-30 Korean search keywords.",
            "- keywords must be a non-empty JSON array of non-empty strings.",
            "- Prioritize 대표 키워드 that directly identify the product.",
            "- Add 롱테일 keywords that combine product + use case, place, buyer, problem, or purchase intent.",
            "- Prefer keywords repeated across multiple sites or strongly related to the original product name.",
            "- Include common spacing variants and typo variants only in keywords, not product_name.",
            "- Remove unrelated broad terms, competitor brands, and low-purchase-intent words.",
            "- Avoid duplicate meanings unless the spelling/search form is meaningfully different.",
            "- Put the highest sales-potential keywords first.",
            "",
            "Output constraints:",
            "- Do not return category fields.",
            "- Do not include markdown, comments, or extra text outside JSON.",
            "",
            "Source row:",
            f"- 상품코드: {row.text('상품코드')}",
            f"- 상품명: {row.text('상품명')}",
            f"- 원본상품명(참고용): {row.text('원본상품명(참고용)')}",
            f"- 옵션명: {row.text('옵션명')}",
            f"- 기존 키워드: {row.text('키워드')}",
            "",
            "Shopping-site keyword suggestions:",
            *site_lines,
        ]
    )


def _build_site_search_keyword_prompt(row: ProductRow) -> str:
    return "\n".join(
        [
            "Return only a strict JSON object with keys: search_keyword, alternatives, review_reason.",
            "Rules:",
            "- search_keyword must be one concise Korean search query for shopping-site autocomplete APIs.",
            "- Prefer the actual object name buyers would search for.",
            "- Use 원본상품명(참고용) as the primary source and 상품명/옵션명 only as supporting context.",
            "- Remove pack counts, quantities, marketing words, and low-value descriptors when they hurt search recall.",
            "- Keep meaningful attributes such as shape, usage, and key object nouns when they distinguish the product.",
            "- alternatives must contain 2-5 shorter fallback queries.",
            "- Do not include commas or explanations in search_keyword.",
            "",
            "Examples:",
            "- 공예용 하트모양 비즈 부자재 10p -> 하트 비즈",
            "- 화장실 청소용 변기 스프레이건 거치대 -> 스프레이건 거치대",
            "- PC 디저트볼(아이스볼) -> 디저트볼",
            "- 물빠짐도마 -> 물빠짐 도마",
            "",
            "Source row:",
            f"- 상품코드: {row.text('상품코드')}",
            f"- 상품명: {row.text('상품명')}",
            f"- 원본상품명(참고용): {row.text('원본상품명(참고용)')}",
            f"- 옵션명: {row.text('옵션명')}",
            f"- 기존 키워드: {row.text('키워드')}",
        ]
    )


def _validate_candidate_choice(
    generated: GeneratedRow,
    candidates: list[CategoryCandidate],
) -> GeneratedRow:
    candidate_by_code = {
        candidate.category.mycate: candidate.category
        for candidate in candidates
    }
    selected = candidate_by_code.get(generated.mycate)
    if selected is None:
        raise LlmResponseError(
            f"mycate must be one of the supplied candidates: {generated.mycate}"
        )
    if generated.mycate_name != selected.name:
        generated.mycate_name = selected.name
    return generated


def _extract_model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    model_ids = {
        item["id"].strip()
        for item in data
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    }
    return sorted(model_ids)


def _looks_like_embedding_model(model_id: str) -> bool:
    normalized = model_id.lower()
    return "embed" in normalized or "embedding" in normalized


def _required_string(data: dict[str, Any], field: str) -> str:
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        raise LlmResponseError(f"{field} must be a non-empty string")
    return value.strip()


def _required_keywords(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LlmResponseError("keywords must be a non-empty list")

    keywords: list[str] = []
    for keyword in value:
        if not isinstance(keyword, str) or not keyword.strip():
            raise LlmResponseError("keywords must contain only non-empty strings")
        keywords.append(keyword.strip())
    return keywords


def _required_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LlmResponseError("confidence must be numeric")
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise LlmResponseError("confidence must be between 0 and 1")
    return confidence
