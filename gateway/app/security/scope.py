"""Scope Enforcer (§13.2, §14).

Décide si une cible est autorisée pour un engagement, à partir de sa liste
blanche (scope_entries). Règles :
  - une exclusion / un out_of_scope l'emporte toujours (deny wins) ;
  - sinon, il faut une règle in_scope qui correspond ;
  - à défaut : refus (default deny).
La logique pure (evaluate) est testable sans base ; enforce_scope l'applique
et journalise toute violation.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ScopeEntry
from app.security.audit import append_audit

_ETH_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")


class ScopeViolationError(Exception):
    """Levée quand une cible est hors périmètre."""


@dataclass(frozen=True)
class ScopeRule:
    kind: str  # domain|ip|cidr|contract
    value: str
    disposition: str  # in_scope|out_of_scope|exclusion
    chain: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    matched: str | None = None


def extract_host(target: str) -> str:
    t = target.strip()
    if "://" in t:
        parsed = urlparse(t)
        host = parsed.hostname or ""
    else:
        host = t.split("/", 1)[0]
        # retire un éventuel port (mais pas pour une adresse de contrat)
        if not _ETH_ADDR.match(host) and host.count(":") == 1:
            host = host.split(":", 1)[0]
    return host.rstrip(".").lower()


def classify(host: str, chain: str | None) -> str:
    if chain is not None or _ETH_ADDR.match(host):
        return "contract"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "domain"
    return "ip"


def _domain_matches(entry_value: str, host: str) -> bool:
    entry = entry_value.rstrip(".").lower()
    if entry.startswith("*."):
        base = entry[2:]
        return host.endswith("." + base)
    return host == entry or host.endswith("." + entry)


def _rule_matches(rule: ScopeRule, host: str, kind: str, chain: str | None) -> bool:
    if rule.kind == "domain" and kind == "domain":
        return _domain_matches(rule.value, host)
    if rule.kind == "ip" and kind == "ip":
        return rule.value == host
    if rule.kind == "cidr" and kind == "ip":
        try:
            return ipaddress.ip_address(host) in ipaddress.ip_network(rule.value, strict=False)
        except ValueError:
            return False
    if rule.kind == "contract" and kind == "contract":
        same_addr = rule.value.lower() == host.lower()
        same_chain = rule.chain is None or rule.chain == chain
        return same_addr and same_chain
    return False


def evaluate(target: str, rules: Sequence[ScopeRule], chain: str | None = None) -> Decision:
    host = extract_host(target)
    if not host:
        return Decision(False, "cible vide ou illisible")
    kind = classify(host, chain)
    for rule in rules:
        if rule.disposition in ("exclusion", "out_of_scope") and _rule_matches(
            rule, host, kind, chain
        ):
            return Decision(False, f"cible exclue par la règle « {rule.value} »", rule.value)
    for rule in rules:
        if rule.disposition == "in_scope" and _rule_matches(rule, host, kind, chain):
            return Decision(True, f"cible autorisée par la règle « {rule.value} »", rule.value)
    return Decision(False, "hors périmètre : aucune règle in_scope ne correspond")


async def enforce_scope(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    target: str,
    chain: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Decision:
    """Charge le périmètre de l'engagement, évalue la cible, journalise si refus.

    Retourne la décision si autorisée ; lève ScopeViolationError sinon.
    """
    rows = (
        await session.scalars(select(ScopeEntry).where(ScopeEntry.engagement_id == engagement_id))
    ).all()
    rules = [
        ScopeRule(kind=r.kind, value=r.value, disposition=r.disposition, chain=r.chain)
        for r in rows
    ]
    decision = evaluate(target, rules, chain)
    if not decision.allowed:
        await append_audit(
            session,
            action="scope.violation",
            actor_id=actor_id,
            engagement_id=engagement_id,
            target=target,
            params={"reason": decision.reason},
        )
        await session.commit()
        raise ScopeViolationError(decision.reason)
    return decision
