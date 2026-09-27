import json

import pytest

from app.wrappers.base import WrapperResult
from app.wrappers.httpx import HttpxWrapper, InvalidTargetError

SAMPLE = "\n".join(
    [
        '{"url":"https://api.example.com","host":"api.example.com","status_code":200,'
        '"title":"API","tech":["nginx","OpenResty"],"webserver":"nginx"}',
        '{"url":"https://mail.example.com","status_code":403,"title":"Forbidden"}',
        '{"url":"https://api.example.com","status_code":200}',
        "",
        "pas-du-json",
        '{"sans_url_ni_host":"x"}',
    ]
)


def test_build_args_basic() -> None:
    args = HttpxWrapper().build_args("Example.com")
    assert args[:5] == ["httpx", "-u", "example.com", "-json", "-silent"]
    assert "example.com" in args


def test_build_args_flags_toggle() -> None:
    args = HttpxWrapper(tech_detect=False, title=False).build_args("example.com")
    assert "-tech-detect" not in args
    assert "-title" not in args
    assert "-status-code" in args


def test_build_args_is_a_list_no_shell() -> None:
    assert isinstance(HttpxWrapper().build_args("example.com"), list)


def test_build_args_bounds_time_on_unreachable_targets() -> None:
    args = HttpxWrapper().build_args("example.com")
    assert "-timeout" in args
    assert args[args.index("-timeout") + 1] == "7"
    assert "-retries" in args
    assert args[args.index("-retries") + 1] == "0"
    assert "-include-response-header" in args


def test_build_args_timeout_and_retries_are_configurable() -> None:
    args = HttpxWrapper(timeout=3, retries=1).build_args("example.com")
    assert args[args.index("-timeout") + 1] == "3"
    assert args[args.index("-retries") + 1] == "1"


def test_build_args_rejects_bad_targets() -> None:
    w = HttpxWrapper()
    for bad in ["", "not a host", "a;rm -rf /", "http://x", "example"]:
        with pytest.raises(InvalidTargetError):
            w.build_args(bad)


def test_parse_dedupes_and_keeps_metadata() -> None:
    result = HttpxWrapper().parse(SAMPLE, "Example.com")
    assert isinstance(result, WrapperResult)
    assert result.tool == "httpx"
    assert result.target == "example.com"
    values = sorted(i.value for i in result.items)
    assert values == ["https://api.example.com", "https://mail.example.com"]
    assert all(i.kind == "host" for i in result.items)
    api = next(i for i in result.items if i.value == "https://api.example.com")
    assert api.metadata["status_code"] == 200
    assert api.metadata["title"] == "API"
    assert api.metadata["tech"] == ["nginx", "OpenResty"]
    assert api.metadata["webserver"] == "nginx"


def test_parse_falls_back_to_host_when_no_url() -> None:
    out = '{"host":"only-host.example.com","status_code":200}'
    r = HttpxWrapper().parse(out, "example.com")
    assert [i.value for i in r.items] == ["only-host.example.com"]


def test_parse_empty() -> None:
    assert HttpxWrapper().parse("", "example.com").items == []


def test_parse_discards_sas_denial_via_header() -> None:
    out = json.dumps(
        {
            "url": "http://example.org",
            "host": "example.org",
            "status_code": 403,
            "webserver": "nginx/1.27.5",
            "content_length": 153,
            "raw_header": "HTTP/1.1 403 Forbidden\r\nServer: nginx/1.27.5\r\n"
            "X-Egress-Denied: 1\r\nContent-Length: 153\r\n\r\n",
        }
    )
    result = HttpxWrapper().parse(out, "example.org")
    assert result.items == []


def test_parse_discards_sas_denial_via_signature_fallback() -> None:
    """Repli signature : même sans X-Egress-Denied dans raw_header (en-tête
    non émis/capturé), le triplet (webserver, status_code, content_length)
    exact du refus nginx suffit à écarter l'entrée."""
    out = json.dumps(
        {
            "url": "http://example.org",
            "host": "example.org",
            "status_code": 403,
            "webserver": "nginx/1.27.5",
            "content_length": 153,
        }
    )
    result = HttpxWrapper().parse(out, "example.org")
    assert result.items == []


def test_parse_keeps_real_403_that_does_not_match_sas_signature() -> None:
    """Un vrai 403 de la cible (webserver différent, ou content_length
    différent) n'est PAS un refus du sas et doit rester persisté."""
    out = json.dumps(
        {
            "url": "https://mail.example.com",
            "status_code": 403,
            "webserver": "Apache",
            "content_length": 512,
        }
    )
    result = HttpxWrapper().parse(out, "example.com")
    assert [i.value for i in result.items] == ["https://mail.example.com"]
