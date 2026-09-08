import pytest

from freqpanda_execution.crypto import (
    EncryptionNotConfigured,
    decrypt_secret,
    encrypt_secret,
    generate_master_key,
)


@pytest.fixture
def master_key(monkeypatch):
    key = generate_master_key()
    monkeypatch.setenv("EXECUTION_MASTER_KEY", key)
    return key


def test_generate_master_key_produces_a_usable_fernet_key():
    key = generate_master_key()
    assert isinstance(key, str)
    assert len(key) > 0


def test_encrypt_then_decrypt_roundtrips(master_key):
    ciphertext = encrypt_secret("super-secret-api-key")
    assert ciphertext != "super-secret-api-key"
    assert decrypt_secret(ciphertext) == "super-secret-api-key"


def test_encrypt_never_returns_the_plaintext_verbatim(master_key):
    secret = "my-api-secret-value"
    ciphertext = encrypt_secret(secret)
    assert secret not in ciphertext


def test_encrypt_raises_when_master_key_is_not_set(monkeypatch):
    monkeypatch.delenv("EXECUTION_MASTER_KEY", raising=False)
    with pytest.raises(EncryptionNotConfigured):
        encrypt_secret("anything")


def test_decrypt_raises_when_master_key_is_not_set(monkeypatch):
    monkeypatch.delenv("EXECUTION_MASTER_KEY", raising=False)
    with pytest.raises(EncryptionNotConfigured):
        decrypt_secret("anything")


def test_decrypt_raises_on_invalid_master_key_format(monkeypatch):
    monkeypatch.setenv("EXECUTION_MASTER_KEY", "not-a-valid-fernet-key")
    with pytest.raises(EncryptionNotConfigured):
        encrypt_secret("anything")


def test_decrypt_raises_with_the_wrong_key(monkeypatch):
    monkeypatch.setenv("EXECUTION_MASTER_KEY", generate_master_key())
    ciphertext = encrypt_secret("a-secret")

    monkeypatch.setenv("EXECUTION_MASTER_KEY", generate_master_key())
    with pytest.raises(EncryptionNotConfigured):
        decrypt_secret(ciphertext)


def test_decrypt_raises_on_tampered_ciphertext(master_key):
    ciphertext = encrypt_secret("a-secret")
    tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
    with pytest.raises(EncryptionNotConfigured):
        decrypt_secret(tampered)
