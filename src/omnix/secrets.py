from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets as secure_random
from pathlib import Path

from .config import data_dir


def _secret_path() -> Path:
    return data_dir() / "secrets.json"


def _dpapi_protect(value: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    import ctypes
    import ctypes.wintypes as wt

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    output = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(Blob(len(value), source)), None, None, None, None, 0, ctypes.byref(output)):
        return None
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _dpapi_unprotect(value: bytes) -> bytes | None:
    if os.name != "nt":
        return None
    import ctypes
    import ctypes.wintypes as wt

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    output = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(Blob(len(value), source)), None, None, None, None, 0, ctypes.byref(output)):
        return None
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _fallback_key() -> bytes:
    master = os.environ.get("OMNIX_MASTER_KEY")
    if not master:
        raise RuntimeError("OMNIX_MASTER_KEY is required for encrypted secrets outside Windows DPAPI")
    return hashlib.pbkdf2_hmac("sha256", master.encode(), b"omnix-secret-store", 200_000, 32)


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    for index in range(0, len(data), 32):
        block = hashlib.sha256(key + nonce + index.to_bytes(8, "big")).digest()
        out.extend(a ^ b for a, b in zip(data[index:index + 32], block))
    return bytes(out)


def set_secret(name: str, value: str) -> None:
    if not name or not value:
        raise ValueError("secret name and value are required")
    payload = value.encode()
    protected = _dpapi_protect(payload)
    record = {"kind": "dpapi", "value": base64.b64encode(protected).decode()} if protected else None
    if record is None:
        nonce = secure_random.token_bytes(16)
        key = _fallback_key()
        ciphertext = _xor_stream(payload, key, nonce)
        tag = hashlib.sha256(key + nonce + ciphertext).digest()
        record = {"kind": "fallback", "nonce": base64.b64encode(nonce).decode(), "value": base64.b64encode(ciphertext).decode(), "tag": base64.b64encode(tag).decode()}
    path = _secret_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[name] = record
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def get_secret(name: str) -> str | None:
    path = _secret_path()
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8")).get(name)
    if not record:
        return None
    if record["kind"] == "dpapi":
        raw = _dpapi_unprotect(base64.b64decode(record["value"]))
        if raw is None:
            raise RuntimeError("Windows DPAPI could not decrypt the secret")
        return raw.decode()
    nonce = base64.b64decode(record["nonce"])
    ciphertext = base64.b64decode(record["value"])
    key = _fallback_key()
    expected = hashlib.sha256(key + nonce + ciphertext).digest()
    if not hmac.compare_digest(expected, base64.b64decode(record["tag"])):
        raise RuntimeError("Secret integrity check failed")
    return _xor_stream(ciphertext, key, nonce).decode()


def has_secret(name: str) -> bool:
    return get_secret(name) is not None
