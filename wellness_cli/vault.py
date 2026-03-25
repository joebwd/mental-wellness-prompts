"""
Local passphrase-protected vault for sensitive wellness data.
"""

import base64
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .paths import (
    AGENTS_FILENAME,
    DB_FILENAME,
    RUNTIME_DIR_ENV,
    SOUL_FILENAME,
    VAULT_DATA_FILENAME,
    VAULT_META_FILENAME,
    get_home_dir,
)


KDF_N = 2**14
KDF_R = 8
KDF_P = 1
KDF_LENGTH = 32
SALT_SIZE = 16
NONCE_SIZE = 12
VAULT_VERSION = 1
RUNTIME_MARKER_FILENAME = "runtime.json"
VAULT_AAD = b"MOSS-VAULT-v1"
IDENTITIES_DIRNAME = "users"
REGISTRY_FILENAME = "users.json"
DEFAULT_IDENTITY_ID = "default"


class VaultError(Exception):
    """Base vault error."""


class InvalidPassphraseError(VaultError):
    """Raised when the provided passphrase cannot decrypt the vault."""


@dataclass
class VaultSession:
    runtime_dir: str
    key: bytes

    @property
    def db_path(self) -> str:
        return os.path.join(self.runtime_dir, DB_FILENAME)

    def install_env(self):
        os.environ[RUNTIME_DIR_ENV] = self.runtime_dir


class VaultManager:
    """Manage the encrypted local data vault."""

    def __init__(self, home_dir: Optional[str] = None):
        self.home_dir = os.path.expanduser(home_dir or get_home_dir())
        self.meta_path = os.path.join(self.home_dir, VAULT_META_FILENAME)
        self.data_path = os.path.join(self.home_dir, VAULT_DATA_FILENAME)
        self.runtime_marker_path = os.path.join(self.home_dir, RUNTIME_MARKER_FILENAME)

    def has_vault(self) -> bool:
        return os.path.exists(self.meta_path) and os.path.exists(self.data_path)

    def has_legacy_plaintext(self, legacy_dir: Optional[str] = None) -> bool:
        return any(os.path.exists(path) for path in self._legacy_paths(legacy_dir))

    def reset(self):
        self.cleanup_stale_runtime()
        shutil.rmtree(self.home_dir, ignore_errors=True)

    def cleanup_stale_runtime(self):
        if not os.path.exists(self.runtime_marker_path):
            return
        try:
            marker = json.loads(self._read_text(self.runtime_marker_path))
        except Exception:
            marker = {}

        runtime_dir = marker.get("runtime_dir")
        if runtime_dir and os.path.isdir(runtime_dir):
            shutil.rmtree(runtime_dir, ignore_errors=True)
        self._remove_file(self.runtime_marker_path)

    def create(
        self,
        passphrase: str,
        migrate_legacy: bool = False,
        legacy_dir: Optional[str] = None,
    ) -> VaultSession:
        if self.has_vault():
            raise VaultError("Vault already exists.")

        self.cleanup_stale_runtime()
        self._ensure_home()

        salt = os.urandom(SALT_SIZE)
        meta = {
            "version": VAULT_VERSION,
            "kdf": {
                "name": "scrypt",
                "salt_b64": base64.b64encode(salt).decode("ascii"),
                "n": KDF_N,
                "r": KDF_R,
                "p": KDF_P,
                "length": KDF_LENGTH,
            },
            "cipher": {
                "name": "AESGCM",
                "nonce_bytes": NONCE_SIZE,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.meta_path, meta)

        session = VaultSession(
            runtime_dir=self._make_runtime_dir(),
            key=self._derive_key(passphrase, salt),
        )
        session.install_env()
        self._write_runtime_marker(session.runtime_dir)

        legacy_base = os.path.expanduser(legacy_dir or self.home_dir)
        legacy_db = os.path.join(legacy_base, DB_FILENAME)
        if migrate_legacy and os.path.exists(legacy_db):
            shutil.copy2(legacy_db, session.db_path)
            os.chmod(session.db_path, stat.S_IRUSR | stat.S_IWUSR)
        else:
            self._initialize_empty_db(session.db_path)

        self.lock(session)

        if migrate_legacy:
            self._cleanup_legacy_plaintext(legacy_base)

        session = self.unlock(passphrase)
        return session

    def unlock(self, passphrase: str) -> VaultSession:
        if not self.has_vault():
            raise VaultError("No vault is configured yet.")

        self.cleanup_stale_runtime()
        meta = self._load_meta()
        salt = base64.b64decode(meta["kdf"]["salt_b64"])
        key = self._derive_key(passphrase, salt)
        ciphertext = self._read_bytes(self.data_path)

        try:
            plaintext = self._decrypt(ciphertext, key)
        except InvalidTag as exc:
            raise InvalidPassphraseError("That vault password did not unlock the local data.") from exc

        session = VaultSession(runtime_dir=self._make_runtime_dir(), key=key)
        session.install_env()
        self._write_runtime_marker(session.runtime_dir)

        with open(session.db_path, "wb") as handle:
            handle.write(plaintext)
        os.chmod(session.db_path, stat.S_IRUSR | stat.S_IWUSR)
        return session

    def lock(self, session: VaultSession):
        runtime_dir = session.runtime_dir
        db_path = session.db_path

        if not os.path.isdir(runtime_dir):
            self._remove_runtime_marker()
            os.environ.pop(RUNTIME_DIR_ENV, None)
            return

        if not os.path.exists(db_path):
            self._initialize_empty_db(db_path)

        plaintext = self._read_bytes(db_path)
        ciphertext = self._encrypt(plaintext, session.key)
        self._write_bytes(self.data_path, ciphertext)

        shutil.rmtree(runtime_dir, ignore_errors=True)
        self._remove_runtime_marker()
        if os.environ.get(RUNTIME_DIR_ENV) == runtime_dir:
            os.environ.pop(RUNTIME_DIR_ENV, None)

    def _load_meta(self) -> dict:
        return json.loads(self._read_text(self.meta_path))

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        kdf = Scrypt(
            salt=salt,
            length=KDF_LENGTH,
            n=KDF_N,
            r=KDF_R,
            p=KDF_P,
        )
        return kdf.derive(passphrase.encode("utf-8"))

    def _encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, VAULT_AAD)
        return nonce + ciphertext

    def _decrypt(self, blob: bytes, key: bytes) -> bytes:
        nonce = blob[:NONCE_SIZE]
        ciphertext = blob[NONCE_SIZE:]
        return AESGCM(key).decrypt(nonce, ciphertext, VAULT_AAD)

    def _ensure_home(self):
        os.makedirs(self.home_dir, exist_ok=True)
        os.chmod(self.home_dir, stat.S_IRWXU)

    def _make_runtime_dir(self) -> str:
        runtime_dir = tempfile.mkdtemp(prefix="moss_vault_")
        os.chmod(runtime_dir, stat.S_IRWXU)
        return runtime_dir

    def _initialize_empty_db(self, db_path: str):
        conn = sqlite3.connect(db_path)
        conn.close()
        os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

    def _write_runtime_marker(self, runtime_dir: str):
        self._ensure_home()
        self._write_json(
            self.runtime_marker_path,
            {
                "runtime_dir": runtime_dir,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _remove_runtime_marker(self):
        self._remove_file(self.runtime_marker_path)

    def _legacy_paths(self, legacy_dir: Optional[str] = None) -> list[str]:
        base_dir = os.path.expanduser(legacy_dir or self.home_dir)
        return [
            os.path.join(base_dir, DB_FILENAME),
            os.path.join(base_dir, "chroma"),
            os.path.join(base_dir, SOUL_FILENAME),
            os.path.join(base_dir, AGENTS_FILENAME),
        ]

    def _cleanup_legacy_plaintext(self, legacy_dir: Optional[str] = None):
        for path in self._legacy_paths(legacy_dir):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                self._remove_file(path)

    def _write_json(self, path: str, payload: dict):
        self._write_text(path, json.dumps(payload, indent=2) + "\n")

    def _write_text(self, path: str, text: str):
        self._write_bytes(path, text.encode("utf-8"))

    def _write_bytes(self, path: str, data: bytes):
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "wb") as handle:
            handle.write(data)
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)

    def _read_text(self, path: str) -> str:
        return self._read_bytes(path).decode("utf-8")

    def _read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def _remove_file(self, path: str):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@dataclass
class IdentityRecord:
    id: str
    label: str
    created_at: str
    last_used_at: Optional[str] = None


class IdentityManager:
    """Track multiple local identities, each backed by its own encrypted vault."""

    def __init__(self, app_home: Optional[str] = None):
        self.app_home = os.path.expanduser(app_home or get_home_dir())
        self.identities_dir = os.path.join(self.app_home, IDENTITIES_DIRNAME)
        self.registry_path = os.path.join(self.app_home, REGISTRY_FILENAME)
        self._migrate_legacy_layout()

    def reset(self):
        shutil.rmtree(self.app_home, ignore_errors=True)

    def list_identities(self) -> list[IdentityRecord]:
        data = self._load_registry()
        records = [IdentityRecord(**row) for row in data]
        return sorted(records, key=lambda item: (item.last_used_at or "", item.created_at), reverse=True)

    def get_identity(self, identity_id: str) -> Optional[IdentityRecord]:
        for record in self.list_identities():
            if record.id == identity_id:
                return record
        return None

    def create_identity(self, label: str) -> IdentityRecord:
        label = " ".join(label.split()).strip() or "User"
        record = IdentityRecord(
            id=self._allocate_identity_id(label),
            label=label,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_used_at=None,
        )
        data = self._load_registry()
        data.append(asdict(record))
        self._store_registry(data)
        os.makedirs(self.identity_dir(record.id), exist_ok=True)
        return record

    def touch(self, identity_id: str):
        data = self._load_registry()
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for row in data:
            if row["id"] == identity_id:
                row["last_used_at"] = now
                changed = True
                break
        if changed:
            self._store_registry(data)

    def get_vault(self, identity_id: str) -> VaultManager:
        return VaultManager(home_dir=self.identity_dir(identity_id))

    def identity_dir(self, identity_id: str) -> str:
        return os.path.join(self.identities_dir, identity_id)

    def has_root_plaintext_legacy(self) -> bool:
        root_vault = VaultManager(home_dir=self.app_home)
        return root_vault.has_legacy_plaintext(self.app_home)

    def ensure_default_identity_for_root_plaintext(self) -> IdentityRecord:
        existing = self.list_identities()
        if existing:
            return existing[0]
        record = IdentityRecord(
            id=DEFAULT_IDENTITY_ID,
            label="Default",
            created_at=datetime.now(timezone.utc).isoformat(),
            last_used_at=None,
        )
        self._store_registry([asdict(record)])
        os.makedirs(self.identity_dir(record.id), exist_ok=True)
        return record

    def _migrate_legacy_layout(self):
        if os.path.exists(self.registry_path):
            return

        root_meta = os.path.join(self.app_home, VAULT_META_FILENAME)
        root_data = os.path.join(self.app_home, VAULT_DATA_FILENAME)
        root_marker = os.path.join(self.app_home, RUNTIME_MARKER_FILENAME)
        if not (os.path.exists(root_meta) and os.path.exists(root_data)):
            return

        os.makedirs(self.identities_dir, exist_ok=True)
        default_dir = self.identity_dir(DEFAULT_IDENTITY_ID)
        os.makedirs(default_dir, exist_ok=True)

        for filename in (VAULT_META_FILENAME, VAULT_DATA_FILENAME, RUNTIME_MARKER_FILENAME):
            src = os.path.join(self.app_home, filename)
            if os.path.exists(src):
                shutil.move(src, os.path.join(default_dir, filename))

        record = IdentityRecord(
            id=DEFAULT_IDENTITY_ID,
            label="Default",
            created_at=datetime.now(timezone.utc).isoformat(),
            last_used_at=None,
        )
        self._store_registry([asdict(record)])

    def _allocate_identity_id(self, label: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "user"
        used = {record.id for record in self.list_identities()}
        if base not in used:
            return base
        suffix = 2
        while f"{base}-{suffix}" in used:
            suffix += 1
        return f"{base}-{suffix}"

    def _load_registry(self) -> list[dict]:
        try:
            with open(self.registry_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return []

    def _store_registry(self, rows: list[dict]):
        os.makedirs(self.identities_dir, exist_ok=True)
        tmp_path = f"{self.registry_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, self.registry_path)
