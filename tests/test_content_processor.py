import pytest

from core_api.domains.agent.core.content_processor import _unwrap_json_content


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            "```json\n{\n  \"summary\": \"value\"\n}\n```",
            "{\n  \"summary\": \"value\"\n}",
        ),
        (
            "```json\r\n{\r\n  \"summary\": \"value\"\r\n}\r\n```",
            "{\n  \"summary\": \"value\"\n}",
        ),
        (
            "json\n{\n  \"summary\": \"value\"\n}\n",
            "{\n  \"summary\": \"value\"\n}",
        ),
        (
            "{\n  \"summary\": \"value\"\n}",
            "{\n  \"summary\": \"value\"\n}",
        ),
    ],
)
def test_unwrap_json_content(payload: str, expected: str) -> None:
    cleaned = _unwrap_json_content(payload)
    assert cleaned == expected
