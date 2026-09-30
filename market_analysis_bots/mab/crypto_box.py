"""Authenticated encryption for small secrets with the Python standard library only.

Construction (encrypt-then-MAC, both keys derived from one 32-byte master key per context):
    enc_key = HMAC-SHA256(master, "jarvus/enc/" + context)
    mac_key = HMAC-SHA256(master, "jarvus/mac/" + context)
    keystream block i = HMAC-SHA256(enc_key, nonce || i as 4 bytes, big-endian)      (a PRF in counter mode)
    ciphertext = plaintext XOR keystream
    tag = HMAC-SHA256(mac_key, version || nonce || len(aad) || aad || ciphertext)
    blob = base64(version || nonce(16 random bytes) || ciphertext || tag)

HMAC-SHA256 is a pseudorandom function, so the counter-mode keystream is a standard stream cipher; a fresh
random nonce per message and a MAC checked in constant time before decryption make it an authenticated
encryption scheme. The associated data (the secret's name) binds a blob to its slot: a ciphertext copied to a
different name fails to open. Only small values (API keys, tokens) are stored this way.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct

VERSION = b"\x01"
NONCE = 16
TAG = 32


class DecryptError(ValueError):
    pass


def _keys(master: bytes, context: bytes):
    if len(master) != 32:
        raise ValueError("master key must be 32 bytes")
    return (hmac.new(master, b"jarvus/enc/" + context, hashlib.sha256).digest(),
            hmac.new(master, b"jarvus/mac/" + context, hashlib.sha256).digest())


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hmac.new(key, nonce + struct.pack(">I", i), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def seal(master: bytes, plaintext: bytes, aad: bytes = b"", context: bytes = b"secrets") -> str:
    ek, mk = _keys(master, context)
    nonce = os.urandom(NONCE)
    ct = bytes(a ^ b for a, b in zip(plaintext, _stream(ek, nonce, len(plaintext))))
    tag = hmac.new(mk, VERSION + nonce + struct.pack(">I", len(aad)) + aad + ct, hashlib.sha256).digest()
    return base64.b64encode(VERSION + nonce + ct + tag).decode()


def open_(master: bytes, blob: str, aad: bytes = b"", context: bytes = b"secrets") -> bytes:
    try:
        raw = base64.b64decode(blob.encode(), validate=True)
    except (ValueError, TypeError) as e:
        raise DecryptError("not a sealed value") from e
    if len(raw) < 1 + NONCE + TAG or raw[:1] != VERSION:
        raise DecryptError("unknown or truncated sealed value")
    nonce, ct, tag = raw[1:1 + NONCE], raw[1 + NONCE:-TAG], raw[-TAG:]
    ek, mk = _keys(master, context)
    want = hmac.new(mk, VERSION + nonce + struct.pack(">I", len(aad)) + aad + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, want):
        raise DecryptError("authentication failed: wrong key, wrong slot, or tampered value")
    return bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct))))
