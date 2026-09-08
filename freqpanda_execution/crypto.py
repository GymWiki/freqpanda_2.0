"""Encryption for exchange API credentials at rest.

Uses Fernet (`cryptography.fernet`) -- symmetric authenticated encryption
(AES-128-CBC + HMAC-SHA256, versioned and timestamped tokens). This is
deliberately boring: credentials are a case of "one operator, encrypt at
rest, decrypt in-process to make a signed request" -- not a multi-party or
public-key scenario, so a well-audited symmetric scheme is the right tool,
not a reason to reach for anything more exotic.

The master key (`EXECUTION_MASTER_KEY`) lives only in the process
environment -- generated once, handed to the API and bot-supervisor
processes via their env, and **never** written to the database, a log
line, or a repo. Losing it makes every stored credential permanently
undecryptable; that is the intended failure mode of "the key is not stored
next to the data it protects", not a bug. See the phase-7 README for
generation and rotation.

Nothing in this module ever logs or returns a decrypted secret except the
one call site that needs it to authenticate a CCXT exchange instance
(`freqpanda_execution.broker.LiveBroker`) -- and that call site holds it
only in a local variable, passed straight into the CCXT client, never
printed.
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken

MASTER_KEY_ENV_VAR = "EXECUTION_MASTER_KEY"


class EncryptionNotConfigured(RuntimeError):
    pass


def generate_master_key() -> str:
    """A new base64 urlsafe 32-byte key, suitable for `EXECUTION_MASTER_KEY`.
    Run once at setup time (see the README) -- not called by the app itself.
    """
    return Fernet.generate_key().decode()


def _get_fernet() -> Fernet:
    key = os.environ.get(MASTER_KEY_ENV_VAR)
    if not key:
        raise EncryptionNotConfigured(
            f"{MASTER_KEY_ENV_VAR} is not set -- generate one with "
            "freqpanda_execution.crypto.generate_master_key() and set it in the "
            "environment of every process that reads/writes exchange credentials."
        )
    try:
        return Fernet(key.encode())
    except (ValueError, base64.binascii.Error) as exc:
        raise EncryptionNotConfigured(f"{MASTER_KEY_ENV_VAR} is not a valid Fernet key") from exc


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionNotConfigured(
            "Could not decrypt credential -- wrong EXECUTION_MASTER_KEY, or the "
            "ciphertext was tampered with/corrupted."
        ) from exc
