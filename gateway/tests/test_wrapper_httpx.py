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
