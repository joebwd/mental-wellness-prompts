"""
Runtime-aware storage paths for the local vault.
"""

import json
import os
import platform
import shutil
from typing import Any, Dict, Optional


DEFAULT_HOME_DIR = os.path.expanduser("~/.wellness_companion")
DEFAULT_LOCAL_HOME_DIR = DEFAULT_HOME_DIR
DEFAULT_ICLOUD_ROOT = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
DEFAULT_ICLOUD_HOME_DIR = os.path.join(DEFAULT_ICLOUD_ROOT, "Moss Vaults")
DEFAULT_BOOTSTRAP_CONFIG_PATH = os.path.expanduser("~/.moss_storage.json")
HOME_DIR_ENV = "MOSS_HOME_DIR"
LOCAL_HOME_DIR_ENV = "MOSS_LOCAL_HOME_DIR"
BOOTSTRAP_CONFIG_ENV = "MOSS_BOOTSTRAP_CONFIG"
ICLOUD_HOME_DIR_ENV = "MOSS_ICLOUD_HOME_DIR"
RUNTIME_DIR_ENV = "MOSS_RUNTIME_DIR"

DB_FILENAME = "wellness.db"
SOUL_FILENAME = "SOUL.md"
AGENTS_FILENAME = "AGENTS.md"
VAULT_META_FILENAME = "vault.json"
VAULT_DATA_FILENAME = "vault.bin"
EXPORT_FILENAME = "wellness_export.json"
STORAGE_REGISTRY_FILENAME = "users.json"


def get_default_local_home_dir() -> str:
    return os.path.expanduser(os.environ.get(LOCAL_HOME_DIR_ENV, DEFAULT_LOCAL_HOME_DIR))


def get_default_icloud_home_dir() -> str:
    return os.path.expanduser(os.environ.get(ICLOUD_HOME_DIR_ENV, DEFAULT_ICLOUD_HOME_DIR))


def get_bootstrap_config_path() -> str:
    return os.path.expanduser(os.environ.get(BOOTSTRAP_CONFIG_ENV, DEFAULT_BOOTSTRAP_CONFIG_PATH))


def _load_bootstrap_payload() -> Optional[Dict[str, Any]]:
    path = get_bootstrap_config_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    return payload if isinstance(payload, dict) else None


def _write_bootstrap_payload(payload: Dict[str, Any]) -> None:
    path = get_bootstrap_config_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def load_storage_choice() -> Optional[Dict[str, Any]]:
    """Read the non-sensitive bootstrap config that points to the chosen storage home."""
    payload = _load_bootstrap_payload()
    if not payload:
        return None

    home_dir = payload.get("home_dir")
    if not home_dir:
        return None

    return {
        "version": payload.get("version", 1),
        "kind": payload.get("kind", "custom"),
        "home_dir": os.path.expanduser(home_dir),
    }


def save_storage_choice(home_dir: str, kind: str) -> None:
    """Persist the selected storage location so startup can find the vaults again."""
    payload = _load_bootstrap_payload() or {}
    payload.update({
        "version": 1,
        "kind": kind,
        "home_dir": os.path.expanduser(home_dir),
    })
    _write_bootstrap_payload(payload)


def load_startup_preferences() -> Optional[Dict[str, Any]]:
    """Read persisted startup choices such as provider and PangoClaw mode."""
    payload = _load_bootstrap_payload()
    if not payload:
        return None

    startup = payload.get("startup")
    if not isinstance(startup, dict):
        return None

    provider = startup.get("provider")
    if provider not in {"claude", "gemini", "codex"}:
        provider = None

    model = startup.get("model")
    if not isinstance(model, str) or not model.strip():
        model = None

    pangoclaw_mode = startup.get("pangoclaw_mode")
    if pangoclaw_mode not in {"auto", "off"}:
        pangoclaw_mode = "auto"

    if not provider and not model and pangoclaw_mode == "auto":
        return None

    return {
        "provider": provider,
        "model": model,
        "pangoclaw_mode": pangoclaw_mode,
    }


def save_startup_preferences(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    pangoclaw_mode: str = "auto",
) -> None:
    """Persist non-sensitive startup preferences for the wizard and launcher."""
    payload = _load_bootstrap_payload() or {}
    startup = payload.get("startup") if isinstance(payload.get("startup"), dict) else {}

    if provider:
        startup["provider"] = provider
    else:
        startup.pop("provider", None)

    if model:
        startup["model"] = model
    else:
        startup.pop("model", None)

    startup["pangoclaw_mode"] = pangoclaw_mode if pangoclaw_mode in {"auto", "off"} else "auto"
    payload["version"] = 1
    payload["startup"] = startup
    _write_bootstrap_payload(payload)


def clear_storage_choice() -> None:
    try:
        os.remove(get_bootstrap_config_path())
    except FileNotFoundError:
        pass


def is_macos() -> bool:
    return platform.system() == "Darwin"


def icloud_drive_available() -> bool:
    """Return True when iCloud Drive is available for placing sealed vault files."""
    if not is_macos():
        return False
    return os.path.isdir(os.path.dirname(get_default_icloud_home_dir()))


def storage_has_state(home_dir: str) -> bool:
    """Detect whether a storage home already contains app data or legacy plaintext files."""
    base_dir = os.path.expanduser(home_dir)
    markers = (
        STORAGE_REGISTRY_FILENAME,
        "users",
        VAULT_META_FILENAME,
        VAULT_DATA_FILENAME,
        DB_FILENAME,
        "chroma",
        SOUL_FILENAME,
        AGENTS_FILENAME,
    )
    return any(os.path.exists(os.path.join(base_dir, marker)) for marker in markers)


def _iter_known_storage_dirs() -> list[str]:
    candidates = [get_default_local_home_dir(), get_default_icloud_home_dir()]
    choice = load_storage_choice()
    if choice:
        candidates.append(choice["home_dir"])
    env_home = os.environ.get(HOME_DIR_ENV)
    if env_home:
        candidates.append(os.path.expanduser(env_home))

    seen = set()
    unique = []
    for candidate in candidates:
        expanded = os.path.expanduser(candidate)
        if expanded in seen:
            continue
        seen.add(expanded)
        unique.append(expanded)
    return unique


def reset_all_storage_state() -> None:
    """Remove all known local/iCloud vault stores and the bootstrap pointer."""
    for path in _iter_known_storage_dirs():
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    clear_storage_choice()


def get_home_dir() -> str:
    """Persistent app home for vault metadata and ciphertext."""
    override = os.environ.get(HOME_DIR_ENV)
    if override:
        return os.path.expanduser(override)

    choice = load_storage_choice()
    if choice:
        return choice["home_dir"]

    return get_default_local_home_dir()


def get_runtime_dir() -> str:
    """Unlocked runtime directory used while the app is running."""
    return os.path.expanduser(os.environ.get(RUNTIME_DIR_ENV, get_home_dir()))


def home_path(*parts: str) -> str:
    return os.path.join(get_home_dir(), *parts)


def runtime_path(*parts: str) -> str:
    return os.path.join(get_runtime_dir(), *parts)


def get_db_path() -> str:
    return runtime_path(DB_FILENAME)


def get_soul_path() -> str:
    return runtime_path(SOUL_FILENAME)


def get_agents_path() -> str:
    return runtime_path(AGENTS_FILENAME)


def get_vault_meta_path() -> str:
    return home_path(VAULT_META_FILENAME)


def get_vault_data_path() -> str:
    return home_path(VAULT_DATA_FILENAME)


def get_plain_export_path() -> str:
    return os.path.expanduser(os.path.join("~", EXPORT_FILENAME))
