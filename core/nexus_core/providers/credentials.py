"""NEXUS Secure Local Credential Storage (Windows Credential Manager + Protected Vault)."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import sys
from typing import Any

from core.nexus_core.errors import ValidationError

_ENV_PREFIX = "env://"
_WINCRED_PREFIX = "wincred://"
_VAULT_PREFIX = "vault://"
_RAW_KEY_HINTS = ("sk-", "aiza")


class _WindowsCredentialVault:
    """Minimal ctypes binding to Windows advapi32 CredReadW / CredWriteW / CredDeleteW."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    @classmethod
    def is_supported(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def read(cls, target_name: str) -> str | None:
        if not cls.is_supported():
            return None

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.c_uint32),
                ("Type", ctypes.c_uint32),
                ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", ctypes.c_uint32),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", ctypes.c_uint32),
                ("AttributeCount", ctypes.c_uint32),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p),
                ("UserName", ctypes.c_wchar_p),
            ]

        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        cred_ptr = ctypes.POINTER(CREDENTIALW)()
        ok = advapi32.CredReadW(target_name, cls.CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr))
        if not ok:
            return None
        try:
            cred = cred_ptr.contents
            raw = bytes(cred.CredentialBlob[: cred.CredentialBlobSize])
            return raw.decode("utf-16-le")
        finally:
            advapi32.CredFree(cred_ptr)

    @classmethod
    def write(cls, target_name: str, secret: str) -> None:
        if not cls.is_supported():
            raise RuntimeError("Windows Credential Manager is only available on win32.")

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.c_uint32),
                ("Type", ctypes.c_uint32),
                ("TargetName", ctypes.c_wchar_p),
                ("Comment", ctypes.c_wchar_p),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", ctypes.c_uint32),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", ctypes.c_uint32),
                ("AttributeCount", ctypes.c_uint32),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.c_wchar_p),
                ("UserName", ctypes.c_wchar_p),
            ]

        encoded = secret.encode("utf-16-le")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        cred = CREDENTIALW()
        cred.Type = cls.CRED_TYPE_GENERIC
        cred.TargetName = target_name
        cred.CredentialBlobSize = len(encoded)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = cls.CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "nexus-daemon"

        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        ok = advapi32.CredWriteW(ctypes.byref(cred), 0)
        if not ok:
            raise OSError("Windows CredWriteW failed.")

    @classmethod
    def delete(cls, target_name: str) -> None:
        if not cls.is_supported():
            return
        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        advapi32.CredDeleteW(target_name, cls.CRED_TYPE_GENERIC, 0)


class CredentialStore:
    """Resolves and stores API secrets without ever exposing them to logs or SQLite."""

    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = (
            Path(vault_path).expanduser().resolve()
            if vault_path is not None
            else (Path.home() / ".nexus" / "secrets.vault.json").resolve()
        )

    @staticmethod
    def validate_credential_ref(credential_ref: str) -> str:
        cleaned = credential_ref.strip()
        if not cleaned:
            raise ValidationError("credentialRef cannot be empty.")
        lowered = cleaned.lower()
        if any(lowered.startswith(prefix) for prefix in _RAW_KEY_HINTS):
            raise ValidationError(
                "credentialRef must be a vault/env URI reference, never a raw API key."
            )
        if not (
            cleaned.startswith(_ENV_PREFIX)
            or cleaned.startswith(_WINCRED_PREFIX)
            or cleaned.startswith(_VAULT_PREFIX)
        ):
            raise ValidationError(
                "credentialRef must use env://, wincred://, or vault:// scheme.",
                details={"credentialRef": cleaned},
            )
        return cleaned

    def _load_vault_file(self) -> dict[str, str]:
        if not self.vault_path.exists():
            return {}
        try:
            data = json.loads(self.vault_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save_vault_file(self, data: dict[str, str]) -> None:
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self.vault_path, 0o600)
        except OSError:
            pass

    def resolve_secret(self, credential_ref: str) -> str | None:
        """Resolves a secret strictly inside backend memory; never serialize its return value."""
        ref = self.validate_credential_ref(credential_ref)
        if ref.startswith(_ENV_PREFIX):
            env_name = ref[len(_ENV_PREFIX) :].strip()
            val = os.environ.get(env_name, "").strip()
            return val or None

        if ref.startswith(_WINCRED_PREFIX):
            target = ref[len(_WINCRED_PREFIX) :].strip()
            if _WindowsCredentialVault.is_supported():
                win_val = _WindowsCredentialVault.read(target)
                if win_val:
                    return win_val.strip()
            vault = self._load_vault_file()
            return vault.get(ref) or None

        vault = self._load_vault_file()
        return vault.get(ref) or None

    def store_secret(self, credential_ref: str, secret_value: str) -> str:
        """Stores a secret in OS vault / restricted file; returns backend description only."""
        ref = self.validate_credential_ref(credential_ref)
        secret = secret_value.strip()
        if not secret:
            raise ValidationError("Secret value cannot be empty.")
        if ref.startswith(_ENV_PREFIX):
            raise ValidationError(
                "env:// references are managed by process environment variables, not written to disk."
            )

        if ref.startswith(_WINCRED_PREFIX) and _WindowsCredentialVault.is_supported():
            target = ref[len(_WINCRED_PREFIX) :].strip()
            _WindowsCredentialVault.write(target, secret)
            return "Windows Credential Manager (advapi32)"

        vault = self._load_vault_file()
        vault[ref] = secret
        self._save_vault_file(vault)
        return "Local Restricted Vault (0600)"

    def delete_secret(self, credential_ref: str) -> bool:
        ref = self.validate_credential_ref(credential_ref)
        removed = False
        if ref.startswith(_WINCRED_PREFIX) and _WindowsCredentialVault.is_supported():
            target = ref[len(_WINCRED_PREFIX) :].strip()
            _WindowsCredentialVault.delete(target)
            removed = True
        vault = self._load_vault_file()
        if ref in vault:
            del vault[ref]
            self._save_vault_file(vault)
            removed = True
        return removed

    def describe_credential(self, credential_ref: str) -> dict[str, Any]:
        """Returns safe, non-secret status metadata about a credential reference."""
        ref = self.validate_credential_ref(credential_ref)
        configured = self.resolve_secret(ref) is not None
        if ref.startswith(_ENV_PREFIX):
            backend = "Environment Variable"
        elif ref.startswith(_WINCRED_PREFIX):
            backend = (
                "Windows Credential Manager"
                if _WindowsCredentialVault.is_supported()
                else "Local Restricted Vault (wincred fallback)"
            )
        else:
            backend = "Local Restricted Vault"
        return {
            "credentialRef": ref,
            "credentialConfigured": configured,
            "credentialBackend": backend,
        }
