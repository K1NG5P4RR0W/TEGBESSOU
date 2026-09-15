import uuid

import jwt as jwtlib
import pytest

from app.security import tokens


def test_access_roundtrip() -> None:
    uid = uuid.uuid4()
    tok = tokens.create_access(uid, "lead")
    payload = tokens.decode(tok, expected_type="access")
    assert payload["sub"] == str(uid)
    assert payload["role"] == "lead"


def test_wrong_type_rejected() -> None:
    tok = tokens.create_refresh(uuid.uuid4(), "admin")
    with pytest.raises(jwtlib.InvalidTokenError):
        tokens.decode(tok, expected_type="access")
