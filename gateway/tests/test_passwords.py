from app.security.passwords import hash_password, verify_password


def test_hash_is_not_plaintext_and_verifies() -> None:
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert verify_password(h, "s3cret!") is True
    assert verify_password(h, "mauvais") is False
