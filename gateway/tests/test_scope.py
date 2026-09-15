from app.security.scope import Decision, ScopeRule, evaluate, extract_host


def r(kind: str, value: str, disposition: str, chain: str | None = None) -> ScopeRule:
    return ScopeRule(kind=kind, value=value, disposition=disposition, chain=chain)


def test_default_deny_when_no_rule() -> None:
    assert evaluate("example.com", []).allowed is False


def test_in_scope_domain_apex_and_subdomain() -> None:
    rules = [r("domain", "example.com", "in_scope")]
    assert evaluate("example.com", rules).allowed is True
    assert evaluate("api.example.com", rules).allowed is True
    assert evaluate("evil.com", rules).allowed is False


def test_wildcard_matches_subdomains_only() -> None:
    rules = [r("domain", "*.example.com", "in_scope")]
    assert evaluate("a.example.com", rules).allowed is True
    assert evaluate("example.com", rules).allowed is False


def test_exclusion_wins_over_in_scope() -> None:
    rules = [
        r("domain", "example.com", "in_scope"),
        r("domain", "secret.example.com", "exclusion"),
    ]
    assert evaluate("secret.example.com", rules).allowed is False
    assert evaluate("public.example.com", rules).allowed is True


def test_out_of_scope_blocks() -> None:
    rules = [
        r("domain", "*.example.com", "in_scope"),
        r("domain", "admin.example.com", "out_of_scope"),
    ]
    assert evaluate("admin.example.com", rules).allowed is False


def test_ip_and_cidr() -> None:
    rules = [r("cidr", "10.0.0.0/24", "in_scope"), r("ip", "192.168.1.5", "in_scope")]
    assert evaluate("10.0.0.42", rules).allowed is True
    assert evaluate("10.0.1.42", rules).allowed is False
    assert evaluate("192.168.1.5", rules).allowed is True


def test_url_target_host_is_extracted() -> None:
    rules = [r("domain", "example.com", "in_scope")]
    assert evaluate("https://api.example.com:8443/login?x=1", rules).allowed is True


def test_contract_scope_with_chain() -> None:
    addr = "0x" + "a" * 40
    rules = [r("contract", addr, "in_scope", "ethereum")]
    assert evaluate(addr, rules, chain="ethereum").allowed is True
    assert evaluate(addr, rules, chain="polygon").allowed is False


def test_extract_host_variants() -> None:
    assert extract_host("https://a.b.com/x") == "a.b.com"
    assert extract_host("a.b.com:8080") == "a.b.com"
    assert extract_host("A.B.COM.") == "a.b.com"


def test_decision_is_frozen_dataclass() -> None:
    d = Decision(True, "ok")
    assert d.allowed and d.reason == "ok"
