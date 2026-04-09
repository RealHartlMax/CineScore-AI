from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _path_setup import ensure_src_path

ensure_src_path()

from cinescore_ai.secrets import EncryptedFileSecretStore, InMemorySecretStore, create_secret_store


class _FakeKeyringBackend:
    def __init__(self, priority: int) -> None:
        self.priority = priority


class _FakeKeyringErrors:
    class PasswordDeleteError(Exception):
        pass


class _FakeKeyringModule:
    errors = _FakeKeyringErrors

    def __init__(self, priority: int = 1) -> None:
        self._backend = _FakeKeyringBackend(priority=priority)
        self._secrets: dict[tuple[str, str], str] = {}

    def get_keyring(self) -> _FakeKeyringBackend:
        return self._backend

    def get_password(self, service_name: str, key: str) -> str | None:
        return self._secrets.get((service_name, key))

    def set_password(self, service_name: str, key: str, value: str) -> None:
        self._secrets[(service_name, key)] = value

    def delete_password(self, service_name: str, key: str) -> None:
        if (service_name, key) not in self._secrets:
            raise self.errors.PasswordDeleteError("missing")
        del self._secrets[(service_name, key)]


class SecretStoreTests(unittest.TestCase):
    def test_in_memory_secret_store_roundtrip(self) -> None:
        store = InMemorySecretStore()

        store.set_secret("alpha", "bravo")

        self.assertEqual(store.get_secret("alpha"), "bravo")
        self.assertFalse(store.is_persistent)

        store.delete_secret("alpha")

        self.assertIsNone(store.get_secret("alpha"))

    def test_create_secret_store_uses_keyring_when_backend_is_available(self) -> None:
        store = create_secret_store(service_name="Test Service", keyring_module=_FakeKeyringModule())

        store.set_secret("api", "token")

        self.assertTrue(store.is_persistent)
        self.assertEqual(store.get_secret("api"), "token")

    def test_create_secret_store_falls_back_when_backend_is_unavailable(self) -> None:
        store = create_secret_store(service_name="Test Service", keyring_module=_FakeKeyringModule(priority=0))

        self.assertIsInstance(store, (InMemorySecretStore, EncryptedFileSecretStore))

    def test_encrypted_file_secret_store_roundtrip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = EncryptedFileSecretStore(
                file_path=Path(temp_dir) / "secrets.json",
                backend_name="TestEncrypted",
                encrypt_value=lambda value: f"enc::{value[::-1]}",
                decrypt_value=lambda value: value.removeprefix("enc::")[::-1],
            )

            store.set_secret("api", "token-123")

            self.assertTrue(store.is_persistent)
            self.assertEqual(store.backend_name, "TestEncrypted")
            self.assertEqual(store.get_secret("api"), "token-123")
            self.assertNotIn("token-123", (Path(temp_dir) / "secrets.json").read_text(encoding="utf-8"))
