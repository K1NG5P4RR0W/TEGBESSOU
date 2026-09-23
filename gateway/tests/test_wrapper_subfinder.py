import pytest

from app.wrappers.base import WrapperResult
from app.wrappers.subfinder import InvalidTargetError, SubfinderWrapper

# Sortie JSON lines réaliste de subfinder, avec pièges : doublon, ligne vide,
# ligne non-JSON, objet sans "host", casse mixte.
SAMPLE = "\n".join(
    [
        '{"host":"api.example.com","source":"crtsh"}',
        '{"host":"mail.example.com","source":"dnsdumpster"}',
        '{"host":"api.example.com","source":"autre"}',
        "",
        "ceci-nest-pas-du-json",
        '{"sans_host":"x"}',
        '{"host":"WWW.example.com"}',
    ]
)


def test_build_args_basic() -> None:
    w = SubfinderWrapper()
    assert w.build_args("Example.com") == ["subfinder", "-d", "example.com", "-silent", "-json"]


def test_build_args_flags() -> None:
    args = SubfinderWrapper(all_sources=True, recursive=True).build_args("example.com")
    assert "-all" in args
    assert "-recursive" in args


def test_build_args_is_a_list_no_shell() -> None:
    # La cible est un élément séparé du tableau : pas d'interpolation, pas de shell.
    args = SubfinderWrapper().build_args("example.com")
    assert isinstance(args, list)
    assert "example.com" in args


def test_build_args_rejects_bad_targets() -> None:
    w = SubfinderWrapper()
    for bad in ["", "not a domain", "http://x.com", "a;rm -rf /", "127.0.0.1", "example"]:
        with pytest.raises(InvalidTargetError):
            w.build_args(bad)


def test_parse_dedupes_normalizes_and_keeps_source() -> None:
    result = SubfinderWrapper().parse(SAMPLE, "Example.com")
    assert isinstance(result, WrapperResult)
    assert result.tool == "subfinder"
    assert result.target == "example.com"
    values = sorted(i.value for i in result.items)
    assert values == ["api.example.com", "mail.example.com", "www.example.com"]
    assert all(i.kind == "subdomain" for i in result.items)
    api = next(i for i in result.items if i.value == "api.example.com")
    assert api.metadata["source"] == "crtsh"  # première occurrence conservée


def test_parse_empty() -> None:
    assert SubfinderWrapper().parse("", "example.com").items == []


def test_parse_tolerates_garbage() -> None:
    out = 'garbage\n{bad}\n{"host":"x.example.com"}'
    r = SubfinderWrapper().parse(out, "example.com")
    assert [i.value for i in r.items] == ["x.example.com"]
