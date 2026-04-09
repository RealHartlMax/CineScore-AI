from __future__ import annotations

from abc import ABC, abstractmethod
from base64 import b64decode, b64encode
import json
import sys
from typing import Any
from pathlib import Path

from cinescore_ai.paths import get_config_directory

try:
    import keyring
    from keyring.errors import KeyringError, NoKeyringError
except ImportError:  # pragma: no cover - depends on local environment
    keyring = None  # type: ignore[assignment]

    class KeyringError(Exception):
        pass

    class NoKeyringError(Exception):
        pass


GEMINI_API_KEY_SECRET = "gemini_api_key"


def get_audio_provider_secret_name(provider_name: str) -> str:
    return f"audio_provider_api_key::{provider_name}"


class SecretStore(ABC):
    @property
    @abstractmethod
    def backend_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_persistent(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_secret(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set_secret(self, key: str, value: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_secret(self, key: str) -> None:
        raise NotImplementedError


class InMemorySecretStore(SecretStore):
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    @property
    def backend_name(self) -> str:
        return "InMemory"

    @property
    def is_persistent(self) -> bool:
        return False

    def get_secret(self, key: str) -> str | None:
        return self._values.get(key)

    def set_secret(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete_secret(self, key: str) -> None:
        self._values.pop(key, None)


class KeyringSecretStore(SecretStore):
    def __init__(self, service_name: str, keyring_module: Any) -> None:
        self._service_name = service_name
        self._keyring = keyring_module
        self._backend_name = keyring_module.get_keyring().__class__.__name__

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def is_persistent(self) -> bool:
        return True

    def get_secret(self, key: str) -> str | None:
        return self._keyring.get_password(self._service_name, key)

    def set_secret(self, key: str, value: str) -> None:
        self._keyring.set_password(self._service_name, key, value)

    def delete_secret(self, key: str) -> None:
        try:
            self._keyring.delete_password(self._service_name, key)
        except self._keyring.errors.PasswordDeleteError:  # type: ignore[attr-defined]
            return


class EncryptedFileSecretStore(SecretStore):
    def __init__(
        self,
        file_path: Path,
        backend_name: str,
        encrypt_value,
        decrypt_value,
    ) -> None:
        self._file_path = file_path
        self._backend_name = backend_name
        self._encrypt_value = encrypt_value
        self._decrypt_value = decrypt_value

    @property
    def backend_name(self) -> str:
        return self._backend_name

    @property
    def is_persistent(self) -> bool:
        return True

    def get_secret(self, key: str) -> str | None:
        payload = self._read_payload()
        encrypted_value = payload.get(key)
        if not isinstance(encrypted_value, str):
            return None
        try:
            return self._decrypt_value(encrypted_value)
        except Exception:
            return None

    def set_secret(self, key: str, value: str) -> None:
        payload = self._read_payload()
        payload[key] = self._encrypt_value(value)
        self._write_payload(payload)

    def delete_secret(self, key: str) -> None:
        payload = self._read_payload()
        payload.pop(key, None)
        self._write_payload(payload)

    def _read_payload(self) -> dict[str, str]:
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_payload(self, payload: dict[str, str]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_secret_store(service_name: str = "CineScore AI", keyring_module: Any | None = None) -> SecretStore:
    module = keyring_module if keyring_module is not None else keyring
    if module is None:
        windows_store = _build_windows_secret_store()
        return windows_store or InMemorySecretStore()

    try:
        backend = module.get_keyring()
        priority = getattr(backend, "priority", None)
        if priority is not None and priority <= 0:
            windows_store = _build_windows_secret_store()
            return windows_store or InMemorySecretStore()
        return KeyringSecretStore(service_name=service_name, keyring_module=module)
    except (KeyringError, NoKeyringError, RuntimeError):
        windows_store = _build_windows_secret_store()
        return windows_store or InMemorySecretStore()


def _build_windows_secret_store() -> SecretStore | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        encrypt_value, decrypt_value = _build_windows_dpapi_codec()
    except Exception:
        return None
    return EncryptedFileSecretStore(
        file_path=get_config_directory() / "secrets.dpapi.json",
        backend_name="Windows DPAPI",
        encrypt_value=encrypt_value,
        decrypt_value=decrypt_value,
    )


def _build_windows_dpapi_codec():
    import ctypes
    from ctypes import wintypes

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    def protect(value: str) -> str:
        raw = value.encode("utf-8")
        if not raw:
            return ""
        source_buffer = ctypes.create_string_buffer(raw)
        source_blob = DATA_BLOB(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
        target_blob = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(source_blob),
            "CineScore AI",
            None,
            None,
            None,
            0,
            ctypes.byref(target_blob),
        ):
            raise OSError(ctypes.get_last_error())
        try:
            encrypted = ctypes.string_at(target_blob.pbData, target_blob.cbData)
        finally:
            kernel32.LocalFree(target_blob.pbData)
        return b64encode(encrypted).decode("ascii")

    def unprotect(value: str) -> str:
        if not value:
            return ""
        encrypted = b64decode(value.encode("ascii"))
        source_buffer = ctypes.create_string_buffer(encrypted)
        source_blob = DATA_BLOB(len(encrypted), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
        target_blob = DATA_BLOB()
        description = wintypes.LPWSTR()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(source_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            0,
            ctypes.byref(target_blob),
        ):
            raise OSError(ctypes.get_last_error())
        try:
            decrypted = ctypes.string_at(target_blob.pbData, target_blob.cbData)
        finally:
            kernel32.LocalFree(target_blob.pbData)
            if description:
                kernel32.LocalFree(description)
        return decrypted.decode("utf-8")

    return protect, unprotect
