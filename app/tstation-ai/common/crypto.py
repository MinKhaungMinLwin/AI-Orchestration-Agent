"""
Chat content encryption (AES-256-GCM).

Two backends, selected by settings.CHAT_ENCRYPTION_MODE:

- "local": single AES-256 key from CHAT_ENCRYPTION_LOCAL_KEY (base64).
  Use for dev / local. Format: "enc:v1L:<b64url(nonce|tag|ciphertext)>"

- "kms":   AWS KMS envelope encryption. Each ciphertext embeds its own encrypted
  DEK; a process-wide DEK is cached for DEK_CACHE_TTL seconds to avoid per-message
  KMS calls. Use for stag / prod.
  Format: "enc:v1K:<b64url(dek_len(2B)|enc_dek|nonce|tag|ciphertext)>"

Migration safety: decrypt() returns the input unchanged if it does not start with
an "enc:v1*:" prefix, so existing plaintext Redis values keep working until they
expire under the 1-week chat history TTL.
"""

import base64
import logging
import os
import struct
import threading
import time
from typing import Optional, Protocol

from Crypto.Cipher import AES

from config.env import settings

logger = logging.getLogger(__name__)

GCM_NONCE_LEN = 12
GCM_TAG_LEN = 16
PREFIX_LOCAL = "enc:v1L:"
PREFIX_KMS = "enc:v1K:"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


class CryptoBackend(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, value: str) -> str: ...


class LocalKeyBackend:
    """AES-256-GCM with a single static key. Dev / local only."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError(f"AES-256 key must be 32 bytes, got {len(key)}")
        self._key = key

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(GCM_NONCE_LEN)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
        return PREFIX_LOCAL + _b64e(nonce + tag + ct)

    def decrypt(self, value: str) -> str:
        body = _b64d(value[len(PREFIX_LOCAL):])
        nonce = body[:GCM_NONCE_LEN]
        tag = body[GCM_NONCE_LEN:GCM_NONCE_LEN + GCM_TAG_LEN]
        ct = body[GCM_NONCE_LEN + GCM_TAG_LEN:]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode("utf-8")


class KmsEnvelopeBackend:
    """AWS KMS envelope encryption with a cached DEK.

    Encrypt: reuses one DEK per process for DEK_CACHE_TTL seconds.
    Decrypt: caches up to DECRYPT_CACHE_MAX (encrypted_dek -> plaintext_dek).
    Each ciphertext carries its own encrypted DEK so multi-instance / key-rotation
    decryption keeps working without coordination.
    """

    DEK_CACHE_TTL = 300  # seconds
    DECRYPT_CACHE_MAX = 256

    def __init__(self, key_id: str, region: Optional[str] = None):
        import boto3  # type: ignore

        self._kms = boto3.client("kms", region_name=region)
        self._key_id = key_id
        self._lock = threading.Lock()
        self._enc_dek: Optional[tuple[bytes, bytes, float]] = None  # (plain, enc, exp)
        self._dec_cache: dict[bytes, bytes] = {}
        self._dec_order: list[bytes] = []

    def _get_enc_dek(self) -> tuple[bytes, bytes]:
        with self._lock:
            now = time.time()
            if self._enc_dek and now < self._enc_dek[2]:
                return self._enc_dek[0], self._enc_dek[1]
        resp = self._kms.generate_data_key(KeyId=self._key_id, KeySpec="AES_256")
        plain, enc = resp["Plaintext"], resp["CiphertextBlob"]
        with self._lock:
            self._enc_dek = (plain, enc, time.time() + self.DEK_CACHE_TTL)
        return plain, enc

    def _decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        with self._lock:
            cached = self._dec_cache.get(encrypted_dek)
        if cached is not None:
            return cached
        resp = self._kms.decrypt(CiphertextBlob=encrypted_dek)
        plain = resp["Plaintext"]
        with self._lock:
            if encrypted_dek not in self._dec_cache:
                self._dec_cache[encrypted_dek] = plain
                self._dec_order.append(encrypted_dek)
                while len(self._dec_order) > self.DECRYPT_CACHE_MAX:
                    self._dec_cache.pop(self._dec_order.pop(0), None)
        return plain

    def encrypt(self, plaintext: str) -> str:
        dek_plain, dek_enc = self._get_enc_dek()
        nonce = os.urandom(GCM_NONCE_LEN)
        cipher = AES.new(dek_plain, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
        body = struct.pack(">H", len(dek_enc)) + dek_enc + nonce + tag + ct
        return PREFIX_KMS + _b64e(body)

    def decrypt(self, value: str) -> str:
        body = _b64d(value[len(PREFIX_KMS):])
        (dek_len,) = struct.unpack(">H", body[:2])
        offset = 2
        dek_enc = body[offset:offset + dek_len]
        offset += dek_len
        nonce = body[offset:offset + GCM_NONCE_LEN]
        offset += GCM_NONCE_LEN
        tag = body[offset:offset + GCM_TAG_LEN]
        offset += GCM_TAG_LEN
        ct = body[offset:]
        dek_plain = self._decrypt_dek(dek_enc)
        cipher = AES.new(dek_plain, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode("utf-8")


class CryptoService:
    """Public API. Pass-through when backend is None (encryption disabled).

    Decrypt always inspects the prefix and returns input unchanged for legacy
    plaintext, so existing data and disabled rollouts both stay safe.
    """

    def __init__(self, backend: Optional[CryptoBackend]):
        self._backend = backend

    @property
    def enabled(self) -> bool:
        return self._backend is not None

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        if plaintext is None or plaintext == "":
            return plaintext
        if self._backend is None:
            return plaintext
        try:
            return self._backend.encrypt(plaintext)
        except Exception as exc:
            logger.error(f"[CRYPTO] encrypt failed: {exc}")
            raise RuntimeError("Chat encryption failed") from exc

    def decrypt(self, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            return value
        if not (value.startswith(PREFIX_LOCAL) or value.startswith(PREFIX_KMS)):
            return value  # legacy plaintext - return as-is for migration window
        if self._backend is None:
            logger.error("[CRYPTO] encrypted value found but backend disabled")
            return value
        try:
            return self._backend.decrypt(value)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[CRYPTO] decrypt failed: {exc}")
            return value


_crypto_service: Optional[CryptoService] = None


def get_crypto_service() -> CryptoService:
    """Singleton; pass-through if CHAT_ENCRYPTION_ENABLED is False."""
    global _crypto_service
    if _crypto_service is not None:
        return _crypto_service

    enabled = getattr(settings, "CHAT_ENCRYPTION_ENABLED", False)
    if not enabled:
        logger.warning("[CRYPTO] Chat encryption is DISABLED (pass-through)")
        _crypto_service = CryptoService(backend=None)
        return _crypto_service

    mode = getattr(settings, "CHAT_ENCRYPTION_MODE", "local")
    backend: Optional[CryptoBackend]

    if mode == "local":
        key_b64 = getattr(settings, "CHAT_ENCRYPTION_LOCAL_KEY", "")
        if not key_b64:
            raise RuntimeError(
                "CHAT_ENCRYPTION_ENABLED=True with mode=local but "
                "CHAT_ENCRYPTION_LOCAL_KEY is empty. Generate one with: "
                'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
            )
        backend = LocalKeyBackend(base64.b64decode(key_b64))
        logger.info("[CRYPTO] Local-key backend initialized (AES-256-GCM)")

    elif mode == "kms":
        key_id = getattr(settings, "CHAT_ENCRYPTION_KMS_KEY_ID", "")
        if not key_id:
            raise RuntimeError(
                "CHAT_ENCRYPTION_ENABLED=True with mode=kms but CHAT_ENCRYPTION_KMS_KEY_ID is empty"
            )
        region = getattr(settings, "AWS_DEFAULT_REGION", None)
        backend = KmsEnvelopeBackend(key_id=key_id, region=region)
        logger.info(f"[CRYPTO] KMS envelope backend initialized (key={key_id})")

    else:
        raise RuntimeError(f"Unknown CHAT_ENCRYPTION_MODE: {mode!r} (expected 'local' or 'kms')")

    _crypto_service = CryptoService(backend=backend)
    return _crypto_service


def reset_crypto_service_for_tests() -> None:
    """Reset singleton (test-only)."""
    global _crypto_service
    _crypto_service = None
