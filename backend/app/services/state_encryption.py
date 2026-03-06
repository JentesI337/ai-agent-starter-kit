"""SEC (OE-08): Application-level encryption-at-rest for state store.

Provides AES-256-GCM encryption using the ``cryptography`` library when available,
with a transparent fallback to base64 obfuscation + HMAC integrity when the
``cryptography`` package is not installed (POC/development mode).

Configuration:
- ``STATE_ENCRYPTION_KEY``: 32-byte hex-encoded key for AES-256-GCM.
  If not set, a per-process ephemeral key is generated (data won't survive restarts).
- ``STATE_ENCRYPTION_ENABLED``: Set to ``false`` to disable encryption entirely.

Also provides HMAC-based integrity protection for policy files.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Any

# Try to use real cryptography if available
_HAS_CRYPTOGRAPHY = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


def _load_encryption_key() -> bytes:
    """Load or generate the encryption key."""
    raw = os.getenv("STATE_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            key = bytes.fromhex(raw)
            if len(key) == 32:
                return key
        except ValueError:
            pass
    # Generate ephemeral key — data won't survive process restart
    return secrets.token_bytes(32)


def _is_encryption_enabled() -> bool:
    return os.getenv("STATE_ENCRYPTION_ENABLED", "true").strip().lower() not in ("0", "false", "no")


_ENCRYPTION_KEY: bytes = _load_encryption_key()
_ENCRYPTION_ENABLED: bool = _is_encryption_enabled()

# Prefix markers to identify encrypted data
_ENCRYPTED_PREFIX = "ENC:v1:"
_OBFUSCATED_PREFIX = "OBF:v1:"


def encrypt_state(plaintext: str) -> str:
    """Encrypt a state string for at-rest storage.

    Returns a prefixed string that can be decrypted with ``decrypt_state()``.
    """
    if not _ENCRYPTION_ENABLED or not plaintext:
        return plaintext

    data = plaintext.encode("utf-8")

    if _HAS_CRYPTOGRAPHY:
        nonce = secrets.token_bytes(12)  # 96-bit nonce for AES-GCM
        aesgcm = AESGCM(_ENCRYPTION_KEY)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        encoded = base64.b64encode(nonce + ciphertext).decode("ascii")
        return f"{_ENCRYPTED_PREFIX}{encoded}"
    else:
        # Fallback: XOR obfuscation + HMAC integrity (not cryptographically strong)
        key_stream = _derive_key_stream(len(data))
        obfuscated = bytes(a ^ b for a, b in zip(data, key_stream))
        mac = hmac.new(_ENCRYPTION_KEY, obfuscated, hashlib.sha256).hexdigest()[:16]
        encoded = base64.b64encode(obfuscated).decode("ascii")
        return f"{_OBFUSCATED_PREFIX}{mac}:{encoded}"


def decrypt_state(ciphertext: str) -> str:
    """Decrypt a state string encrypted with ``encrypt_state()``.

    Returns plaintext. Raises ValueError if integrity check fails.
    """
    if not ciphertext:
        return ciphertext

    if ciphertext.startswith(_ENCRYPTED_PREFIX):
        if not _HAS_CRYPTOGRAPHY:
            raise ValueError("Cannot decrypt AES-GCM data without 'cryptography' package installed")
        raw = base64.b64decode(ciphertext[len(_ENCRYPTED_PREFIX):])
        nonce = raw[:12]
        ct = raw[12:]
        aesgcm = AESGCM(_ENCRYPTION_KEY)
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return plaintext.decode("utf-8")

    if ciphertext.startswith(_OBFUSCATED_PREFIX):
        remainder = ciphertext[len(_OBFUSCATED_PREFIX):]
        mac, encoded = remainder.split(":", 1)
        obfuscated = base64.b64decode(encoded)
        # Verify HMAC integrity
        expected_mac = hmac.new(_ENCRYPTION_KEY, obfuscated, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("State integrity check failed — data may have been tampered with")
        key_stream = _derive_key_stream(len(obfuscated))
        plaintext = bytes(a ^ b for a, b in zip(obfuscated, key_stream))
        return plaintext.decode("utf-8")

    # Not encrypted — return as-is (backward compatible)
    return ciphertext


def _derive_key_stream(length: int) -> bytes:
    """Derive a repeatable key stream from the encryption key using HKDF-like expansion."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hashlib.sha256(_ENCRYPTION_KEY + counter.to_bytes(4, "big")).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


# ---------------------------------------------------------------------------
# Policy file HMAC integrity
# ---------------------------------------------------------------------------

_POLICY_HMAC_KEY: bytes = os.getenv(
    "POLICY_HMAC_KEY", ""
).encode("utf-8") or _ENCRYPTION_KEY


def sign_policy_file(content: str) -> str:
    """Add HMAC signature to policy file content.

    Returns content with ``# HMAC: <signature>`` appended.
    """
    signature = hmac.new(
        _POLICY_HMAC_KEY,
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{content}\n# HMAC: {signature}"


def verify_policy_file(content: str) -> tuple[str, bool]:
    """Verify HMAC signature on policy file content.

    Returns ``(content_without_signature, is_valid)``.
    If no signature is found, returns ``(content, False)``.
    """
    lines = content.rstrip().split("\n")
    if not lines:
        return content, False

    last_line = lines[-1].strip()
    if not last_line.startswith("# HMAC: "):
        return content, False

    claimed_sig = last_line[len("# HMAC: "):].strip()
    original = "\n".join(lines[:-1])
    expected_sig = hmac.new(
        _POLICY_HMAC_KEY,
        original.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return original, hmac.compare_digest(claimed_sig, expected_sig)
