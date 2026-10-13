"""Keep secrets out of plain-text config files.

On Windows the access token is encrypted with **DPAPI** (`CryptProtectData`),
which ties the ciphertext to the current user account: another user, or a copy
of the config file, cannot decrypt it. On other platforms (development) we fall
back to plain text and say so.

Values are stored as ``dpapi:v1:<base64>`` so a plain value from an older
config keeps working (and gets re-encrypted on the next save).
"""

import base64
import ctypes
import sys

PREFIX = "dpapi:v1:"
_ENTROPY = b"vozlab-config-v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def available() -> bool:
    """True when DPAPI can be used (i.e. we are on Windows)."""
    return sys.platform.startswith("win")


def _blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _bytes(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _encrypt(raw: bytes) -> bytes:
    """DPAPI-encrypt bytes (Windows only; tests replace this)."""
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = _blob(raw)
    blob_entropy = _blob(_ENTROPY)
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), "VozLab",
        ctypes.byref(blob_entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(f"CryptProtectData failed (error {kernel32.GetLastError()})")
    try:
        return _bytes(blob_out)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _decrypt(raw: bytes) -> bytes:
    """DPAPI-decrypt bytes (Windows only; tests replace this)."""
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in = _blob(raw)
    blob_entropy = _blob(_ENTROPY)
    blob_out = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None,
        ctypes.byref(blob_entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed (error {kernel32.GetLastError()})")
    try:
        return _bytes(blob_out)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(text: str) -> str:
    """Encrypt `text`. Returns it unchanged when DPAPI is unavailable."""
    if not text or not available():
        return text
    if is_protected(text):
        return text
    return PREFIX + base64.b64encode(_encrypt(text.encode("utf-8"))).decode("ascii")


def unprotect(value: str) -> str:
    """Decrypt a value produced by `protect`. Plain values pass through."""
    if not value or not is_protected(value):
        return value
    if not available():
        raise OSError("this value was encrypted on Windows (DPAPI) and cannot be "
                      "read on this machine")
    return _decrypt(base64.b64decode(value[len(PREFIX):])).decode("utf-8")


def is_protected(value: str) -> bool:
    return bool(value) and value.startswith(PREFIX)
