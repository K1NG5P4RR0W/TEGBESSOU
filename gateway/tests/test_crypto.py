from app.core import crypto


def test_encrypt_decrypt_roundtrip() -> None:
    secret = b"un-secret-totp"
    blob = crypto.encrypt(secret)
    assert blob != secret
    assert crypto.decrypt(blob) == secret


def test_two_encryptions_differ() -> None:
    # nonce aléatoire -> deux chiffrés distincts pour le même clair
    assert crypto.encrypt(b"x") != crypto.encrypt(b"x")
