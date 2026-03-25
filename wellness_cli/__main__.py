"""
Main entry point for Moss — ties together chat engine, memory, surveys, soul profile, and CLI.

Supports multiple AI backends: Claude Code, Gemini CLI, Codex CLI.
No API keys needed — each provider uses its own local CLI authentication.

Usage:
    ./moss                                           # prompts for provider default model
    ./moss --provider gemini                         # use Gemini CLI
    ./moss --provider codex                          # use OpenAI Codex CLI
    ./moss --provider claude --model sonnet
    ./moss --provider gemini --model gemini-2.5-pro
    ./moss --reset                                   # clear all stored data
    python -m wellness_cli --provider gemini         # direct module entry
"""

import argparse
import importlib
import json
import os
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from .db import WellnessDB, MoodEntry
from .governance import GovernedWellnessActions, PangoClawSidecarClient
from .memory import MemoryStore
from .chat_engine import ChatEngine, detect_crisis
from .paths import (
    HOME_DIR_ENV,
    get_default_icloud_home_dir,
    get_default_local_home_dir,
    get_plain_export_path,
    icloud_drive_available,
    load_startup_preferences,
    load_storage_choice,
    reset_all_storage_state,
    save_startup_preferences,
    save_storage_choice,
    storage_has_state,
)
from .providers import get_provider, detect_available_providers, PROVIDERS, MODEL_ALIASES
from .runtime import MossFeatureFlags, build_chat_engine, build_dynamic_onboarding_generator
from .soul import SoulProfile, ONBOARDING_QUESTIONS
from .surveys import QUICK_CHECKIN, DEEP_CHECKIN, interpret_scores
from .vault import DEFAULT_IDENTITY_ID, IdentityManager, IdentityRecord, InvalidPassphraseError
from . import cli


def _build_governed_actions(
    db: WellnessDB,
    pangoclaw_mode: str = "auto",
    socket_path: Optional[str] = None,
) -> GovernedWellnessActions:
    """Create the narrow PangoClaw-backed governance wrapper."""
    if pangoclaw_mode == "off":
        socket_path = os.path.join("/tmp", f"moss-pangoclaw-disabled-{os.getpid()}-{uuid.uuid4().hex}.sock")
    return GovernedWellnessActions(
        db=db,
        client=PangoClawSidecarClient(socket_path=socket_path),
    )


# ── Provider defaults ─────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "claude": "opus",
    "gemini": "gemini-3.1-pro-preview",
    "codex":  "gpt-5.4",
}

PROVIDER_INSTALL_HINTS = {
    "claude": "https://docs.anthropic.com/en/docs/claude-code",
    "gemini": "https://github.com/google-gemini/gemini-cli",
    "codex": "https://github.com/openai/codex",
}

PROVIDER_MODEL_OPTIONS = {
    "claude": [
        {"value": "opus", "label": "Opus", "detail": "Best Claude quality for the richest replies"},
        {"value": "sonnet", "label": "Sonnet", "detail": "Balanced quality and speed"},
        {"value": "haiku", "label": "Haiku", "detail": "Fastest Claude option"},
    ],
    "gemini": [
        {"value": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview", "detail": "Best Gemini quality"},
        {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "detail": "Strong quality with broader availability"},
        {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "detail": "Faster and cheaper"},
        {"value": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite", "detail": "Lightest Gemini option"},
    ],
    "codex": [
        {"value": "gpt-5.4", "label": "GPT-5.4", "detail": "Best OpenAI model in this CLI"},
        {"value": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "detail": "Faster and cheaper"},
        {"value": "gpt-5.3-codex", "label": "GPT-5.3 Codex", "detail": "Coding-tuned fallback"},
        {"value": "gpt-5.3-codex-spark", "label": "GPT-5.3 Codex Spark", "detail": "Fastest OpenAI option"},
    ],
}


def _resolve_model(provider_name: str, requested_model: Optional[str]) -> str:
    """Return explicit model or ask the user to choose one."""
    if requested_model:
        return requested_model

    default_model = PROVIDER_DEFAULTS.get(provider_name)
    options = PROVIDER_MODEL_OPTIONS.get(provider_name, [])
    if not default_model or not options or not sys.stdin.isatty():
        return default_model

    return cli.choose_model(provider_name, options, default=default_model)


def _matching_model_default(provider_name: str, candidate: Optional[str]) -> str:
    values = {row["value"] for row in PROVIDER_MODEL_OPTIONS.get(provider_name, [])}
    if candidate and candidate in values:
        return candidate
    return PROVIDER_DEFAULTS[provider_name]


def _collect_provider_wizard_rows() -> list[dict]:
    rows = []
    for name in PROVIDERS:
        binary = shutil.which(name)
        row = {
            "value": name,
            "installed": bool(binary),
            "available": False,
            "detail": "",
            "fix": PROVIDER_INSTALL_HINTS.get(name, ""),
        }
        if binary:
            try:
                provider = get_provider(name)
                auth_err = provider.check_auth()
            except Exception as exc:
                auth_err = str(exc)

            if auth_err:
                row["detail"] = auth_err[:120]
            else:
                row["available"] = True
                row["detail"] = "ready"
        rows.append(row)
    return rows


def _pangoclaw_status(socket_path: Optional[str] = None) -> tuple[str, object]:
    client = PangoClawSidecarClient(socket_path=socket_path)
    return client.socket_path, client.status(force=True)


def _run_startup_wizard(
    *,
    requested_provider: Optional[str],
    requested_model: Optional[str],
    pangoclaw_mode: str,
    pangoclaw_socket: Optional[str],
) -> dict:
    cli.show_startup_wizard_intro()

    provider_rows = _collect_provider_wizard_rows()
    provider_name = cli.choose_provider(
        provider_rows,
        default=requested_provider or "claude",
    )
    if not provider_name:
        cli.show_notice(
            "No authenticated provider CLI is ready yet. Run ./moss doctor after installing and logging into one.",
            tone="danger",
        )
        raise SystemExit(1)

    model_default = _matching_model_default(provider_name, requested_model)
    model = cli.choose_model(provider_name, PROVIDER_MODEL_OPTIONS[provider_name], default=model_default)

    socket_path, status = _pangoclaw_status(pangoclaw_socket)
    pangoclaw_mode = cli.choose_pangoclaw_mode(
        socket_path,
        {"ready": status.ready, "reason": status.reason},
        default=pangoclaw_mode,
    )

    save_startup_preferences(
        provider=provider_name,
        model=model,
        pangoclaw_mode=pangoclaw_mode,
    )
    return {
        "provider": provider_name,
        "model": model,
        "pangoclaw_mode": pangoclaw_mode,
    }


def _configure_storage_home() -> str:
    """Pick the persistent storage home for sealed vault files."""
    override = os.environ.get(HOME_DIR_ENV)
    if override:
        return os.path.expanduser(override)

    existing_choice = load_storage_choice()
    if existing_choice:
        return existing_choice["home_dir"]

    local_home = get_default_local_home_dir()
    icloud_home = get_default_icloud_home_dir()
    local_has_state = storage_has_state(local_home)
    icloud_ready = icloud_drive_available()
    icloud_has_state = icloud_ready and storage_has_state(icloud_home)

    if local_has_state and not icloud_has_state:
        save_storage_choice(local_home, kind="local")
        return local_home

    if icloud_has_state and not local_has_state:
        save_storage_choice(icloud_home, kind="icloud")
        return icloud_home

    if icloud_ready:
        choice = cli.choose_storage_location(
            local_home,
            icloud_home,
            local_has_data=local_has_state,
            icloud_has_data=icloud_has_state,
        )
        selected_home = icloud_home if choice == "2" else local_home
        selected_kind = "icloud" if choice == "2" else "local"
        save_storage_choice(selected_home, kind=selected_kind)
        if selected_kind == "icloud":
            cli.show_notice(
                "Encrypted vault files will live in iCloud Drive. Unlocked runtime files still stay local to this Mac.",
                tone="muted",
            )
        else:
            cli.show_notice("Encrypted vault files will stay local to this Mac.", tone="muted")
        return selected_home

    save_storage_choice(local_home, kind="local")
    return local_home


def _choose_identity(identity_manager: IdentityManager, auto_select_single: bool = False) -> IdentityRecord:
    identities = identity_manager.list_identities()

    if identities:
        if len(identities) == 1 and auto_select_single:
            return identities[0]

        choice = cli.choose_identity([{
            "id": identity.id,
            "label": identity.label,
            "created_at": identity.created_at,
            "last_used_at": identity.last_used_at,
        } for identity in identities])
        if choice != "0":
            return identities[int(choice) - 1]

    elif identity_manager.has_root_plaintext_legacy():
        return identity_manager.ensure_default_identity_for_root_plaintext()

    label = cli.prompt_text("identity name", default="Default")
    return identity_manager.create_identity(label)


def _unlock_or_create_vault(
    identity_manager: IdentityManager,
    identity: IdentityRecord,
):
    vault = identity_manager.get_vault(identity.id)
    display_identity = cli.safe_identity_label(identity.label)
    migrate_legacy = (
        identity.id == DEFAULT_IDENTITY_ID
        and not vault.has_vault()
        and identity_manager.has_root_plaintext_legacy()
    )

    if vault.has_vault():
        if display_identity:
            cli.show_notice(f"Unlock {display_identity}'s local encrypted vault to continue.", tone="muted")
        else:
            cli.show_notice("Unlock this identity's local encrypted vault to continue.", tone="muted")
        while True:
            try:
                passphrase = cli.prompt_secret("vault password")
                session = vault.unlock(passphrase)
                cli.show_notice("Local vault unlocked.", tone="success")
                identity_manager.touch(identity.id)
                return session
            except InvalidPassphraseError as exc:
                cli.show_notice(str(exc), tone="danger")
            except (KeyboardInterrupt, EOFError):
                raise SystemExit(1)

    if migrate_legacy:
        if display_identity:
            cli.show_notice(
                f"Existing local data found for {display_identity}. Create a vault password to seal it into encrypted storage.",
                tone="warning",
            )
        else:
            cli.show_notice(
                "Existing local data found for this identity. Create a vault password to seal it into encrypted storage.",
                tone="warning",
            )
    else:
        if display_identity:
            cli.show_notice(f"Create a vault password for {display_identity}.", tone="warning")
        else:
            cli.show_notice("Create a vault password for this identity.", tone="warning")
    cli.show_notice("If you forget this password, this identity's data cannot be recovered.", tone="danger")

    try:
        passphrase = cli.prompt_secret("vault password", confirm=True)
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(1)

    session = vault.create(
        passphrase,
        migrate_legacy=migrate_legacy,
        legacy_dir=identity_manager.app_home if migrate_legacy else None,
    )
    if migrate_legacy:
        cli.show_notice("Previous local files were migrated into the encrypted vault.", tone="success")
    else:
        cli.show_notice("Local encrypted vault created.", tone="success")
    identity_manager.touch(identity.id)
    return session


# ── Setup / Doctor ────────────────────────────────────────────────────

_REQUIRED_PACKAGES = ("rich", "chromadb", "cryptography")


def _run_setup():
    """Pre-flight diagnostics: deps, providers, auth, isolation."""
    cli.show_banner()
    checks = []

    # 1. Python dependencies
    for pkg in _REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            checks.append({"name": f"python: {pkg}", "ok": True, "detail": "installed"})
        except ImportError:
            checks.append({
                "name": f"python: {pkg}", "ok": False,
                "detail": "missing",
                "fix": f"pip install {pkg}",
            })

    # 2. Provider CLIs
    provider_found = {}
    for name, cls in PROVIDERS.items():
        binary = shutil.which(name)
        if binary:
            checks.append({"name": f"cli: {name}", "ok": True, "detail": binary})
            provider_found[name] = True
        else:
            checks.append({
                "name": f"cli: {name}", "ok": False,
                "detail": "not found",
                "fix": PROVIDER_INSTALL_HINTS.get(name, f"Install the {name} CLI"),
            })

    # 3. Auth check for available providers
    for name in provider_found:
        try:
            provider = get_provider(name)
            err = provider.check_auth()
            if err:
                checks.append({
                    "name": f"auth: {name}", "ok": False,
                    "detail": err[:80],
                    "fix": err,
                })
            else:
                checks.append({"name": f"auth: {name}", "ok": True, "detail": "authenticated"})
        except Exception as e:
            checks.append({
                "name": f"auth: {name}", "ok": False,
                "detail": str(e)[:80],
            })

    # 4. Working directory isolation — use the first available provider to
    #    check what cwd the subprocess would actually run from.
    cwd = None
    for name in provider_found:
        try:
            cwd = get_provider(name)._working_dir()
            break
        except Exception:
            pass
    if cwd is None:
        import tempfile
        cwd = os.path.join(tempfile.gettempdir(), "moss-runtime")
    # Walk up checking for CLAUDE.md
    leaked = False
    check_dir = cwd
    while check_dir and check_dir != os.path.dirname(check_dir):
        if os.path.exists(os.path.join(check_dir, "CLAUDE.md")):
            leaked = True
            break
        check_dir = os.path.dirname(check_dir)

    if leaked:
        checks.append({
            "name": "isolation: CLAUDE.md",
            "ok": False,
            "detail": f"found in {check_dir}",
            "fix": "Provider subprocess cwd has CLAUDE.md in ancestry — system prompt may be overridden",
        })
    else:
        checks.append({"name": "isolation: CLAUDE.md", "ok": True, "detail": f"clean ({cwd})"})

    # 5. Storage
    choice = load_storage_choice()
    if choice:
        home = choice["home_dir"]
        kind = choice.get("kind", "custom")
        exists = os.path.isdir(home)
        checks.append({
            "name": f"storage: {kind}",
            "ok": exists,
            "detail": home if exists else f"{home} (missing)",
        })
    else:
        checks.append({
            "name": "storage",
            "ok": True,
            "detail": "not configured yet (will prompt on first run)",
        })

    # 6. Optional PangoClaw sidecar visibility
    socket_path, status = _pangoclaw_status()
    checks.append({
        "name": "pangoclaw (optional)",
        "ok": True,
        "detail": socket_path if status.ready else f"{socket_path} ({status.reason or 'not ready'})",
    })

    cli.show_setup_result(checks)
    return 0 if all(c["ok"] for c in checks) else 1


def main():
    provider_names = ", ".join(PROVIDERS.keys())
    model_names = ", ".join(MODEL_ALIASES.keys())
    prog_name = os.path.basename(sys.argv[0])
    if prog_name == "__main__.py":
        prog_name = "moss"

    parser = argparse.ArgumentParser(
        prog=prog_name,
        description="Moss — mental wellness companion in your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""commands:
  ./moss setup                        # guided startup wizard
  ./moss doctor                       # check deps, providers, auth
  ./moss                              # start chat with saved defaults

providers: {provider_names}
model shortcuts: {model_names}

examples:
  ./moss                              # uses wizard defaults, or walks first-run setup
  ./moss setup                        # revisit provider, PangoClaw, and onboarding
  ./moss --provider codex             # override the saved provider for this run
  ./moss --no-pangoclaw               # force sidecar-governed effects off for this run
  ./moss -p claude -m sonnet          # claude sonnet for this run
  ./moss -p gemini -m gemini-3.1-pro-preview  # latest gemini"""
    )
    parser.add_argument("command", nargs="?", default=None,
                        help="Subcommand: setup (guided wizard), doctor (diagnostics)")
    parser.add_argument("--provider", "-p", default=None,
                        choices=list(PROVIDERS.keys()),
                        help="AI backend to use for this run")
    parser.add_argument("--model", "-m", default=None,
                        help="Model name (skips the interactive model picker)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset all data and start fresh")
    parser.add_argument("--re-onboard", action="store_true",
                        help="Re-run the onboarding questions")
    parser.add_argument("--wizard", action="store_true",
                        help="Force the guided startup wizard before chat")
    parser.add_argument("--no-dynamic-onboarding", action="store_true",
                        help="Use only the fixed onboarding questions")
    parser.add_argument("--no-pangoclaw", action="store_true",
                        help="Disable the PangoClaw sidecar for this run")
    parser.add_argument("--pangoclaw-socket", default=None,
                        help="Unix socket path for the local PangoClaw sidecar")
    parser.add_argument("--unsafe-disable-safety-supervisor", action="store_true",
                        help="Disable the Python chat safety supervisor for embedding/development")
    args = parser.parse_args()

    if args.command not in {None, "setup", "doctor"}:
        parser.error(f"unknown command: {args.command}")

    if args.command == "doctor":
        return _run_setup()

    if args.reset:
        reset_all_storage_state()

    startup_prefs = load_startup_preferences() or {}
    provider_name = args.provider or startup_prefs.get("provider") or "claude"
    saved_model = startup_prefs.get("model") if startup_prefs.get("provider") == provider_name else None
    pangoclaw_mode = "off" if args.no_pangoclaw else startup_prefs.get("pangoclaw_mode", "auto")
    wizard_requested = args.command == "setup" or args.wizard or not startup_prefs

    if wizard_requested:
        wizard_state = _run_startup_wizard(
            requested_provider=provider_name,
            requested_model=args.model or saved_model,
            pangoclaw_mode=pangoclaw_mode,
            pangoclaw_socket=args.pangoclaw_socket,
        )
        provider_name = wizard_state["provider"]
        model = wizard_state["model"]
        pangoclaw_mode = wizard_state["pangoclaw_mode"]
        cli.show_banner()
    else:
        model = _resolve_model(provider_name, args.model or saved_model)
        cli.show_banner()

    feature_flags = MossFeatureFlags(
        enable_dynamic_onboarding_followups=not args.no_dynamic_onboarding,
        enable_safety_supervisor=not args.unsafe_disable_safety_supervisor,
    )
    storage_home = _configure_storage_home()
    identity_manager = IdentityManager(app_home=storage_home)
    current_identity = _choose_identity(identity_manager, auto_select_single=True)
    active_identity_label = cli.safe_identity_label(current_identity.label)
    if active_identity_label:
        cli.show_notice(f"Active identity: {active_identity_label}", tone="muted")
    else:
        cli.show_notice("Active identity selected.", tone="muted")
    current_vault = identity_manager.get_vault(current_identity.id)
    vault_session = _unlock_or_create_vault(identity_manager, current_identity)

    db = None
    try:
        db = WellnessDB()
        memory = MemoryStore(db)
        soul = SoulProfile(db)
        governed_actions = _build_governed_actions(
            db,
            pangoclaw_mode=pangoclaw_mode,
            socket_path=args.pangoclaw_socket,
        )

        try:
            provider = get_provider(provider_name, model)
        except FileNotFoundError as e:
            cli.console.print()
            cli.show_notice(str(e), tone="danger")
            available = detect_available_providers()
            if available:
                cli.show_notice(
                    f"Available on this system: {', '.join(available)}",
                    tone="muted",
                )
            cli.console.print()
            return 1

        # ── Auth pre-flight ────────────────────────────────────────
        auth_err = provider.check_auth()
        if auth_err:
            cli.console.print()
            cli.show_notice(auth_err, tone="danger")
            cli.console.print()
            return 1

        engine = build_chat_engine(
            db=db,
            memory=memory,
            provider=provider,
            soul_profile=soul,
            governed_actions=governed_actions,
            feature_flags=feature_flags,
        )

        cli.show_provider_status(provider.name, provider.model)
        if not feature_flags.enable_safety_supervisor:
            cli.show_notice(
                "Python safety supervisor disabled. Use this only for non-wellness embedding or test flows.",
                tone="danger",
            )
        if pangoclaw_mode == "off":
            cli.show_notice(
                "PangoClaw disabled: governed follow-ups, memory refinement, and /export are paused.",
                tone="warning",
            )
        elif not governed_actions.available:
            cli.show_notice(
                "PangoClaw unavailable: governed follow-ups, memory refinement, and /export are paused.",
                tone="warning",
            )

        # ── Onboarding (first time or re-onboard) ────────────────────
        should_re_onboard = args.re_onboard
        if wizard_requested and soul.exists and not should_re_onboard:
            should_re_onboard = cli.choose_profile_start(soul.name) == "re_onboard"

        if not soul.exists or should_re_onboard:
            dynamic_gen = build_dynamic_onboarding_generator(
                engine,
                governed_actions,
                feature_flags=feature_flags,
            )
            answers = cli.run_onboarding(ONBOARDING_QUESTIONS, dynamic_generator=dynamic_gen)
            if answers.get("name"):
                soul.store_onboarding(answers)
                cli.show_notice("Profile saved inside the encrypted vault.", tone="success")
            else:
                cli.show_notice("Run with --re-onboard anytime if you want to revisit setup.", tone="muted")
            import time
            time.sleep(0.5)
            cli.clear_screen()
            cli.show_banner()
            cli.show_provider_status(provider.name, provider.model)
            if soul.exists:
                cli.show_soul_loaded(soul.name)
        else:
            if wizard_requested:
                cli.clear_screen()
                cli.show_banner()
                cli.show_provider_status(provider.name, provider.model)
            stats = db.get_stats()
            cli.show_returning_welcome(stats, soul.name)
            cli.show_soul_loaded(soul.name)
            if not wizard_requested:
                cli.show_notice("Use ./moss setup anytime to revisit provider, PangoClaw, and onboarding.", tone="muted")

        # ── Session setup ─────────────────────────────────────────────
        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        engine.start_session(session_id)
        governed_actions.start_session(session_id)

        mood_start = None
        mood_end = None

        # ── Main Loop ────────────────────────────────────────────────
        try:
            while True:
                user_input = cli.get_user_input()
                if not user_input:
                    continue

                text = user_input.strip()

                # ── Commands ─────────────────────────────────────────
                if text.startswith("/"):
                    cmd = text.lower().split()[0]

                    if cmd in ("/quit", "/exit", "/q"):
                        _end_session(engine, db, soul, session_id, mood_start, mood_end, governed_actions)
                        break

                    elif cmd in ("/help", "/h"):
                        cli.show_help()
                        continue

                    elif cmd == "/checkin":
                        scores = cli.run_survey(QUICK_CHECKIN, "Quick Check-In")
                        if scores is None:
                            continue
                        cli.show_survey_results(scores)
                        _save_mood(db, session_id, scores)
                        if mood_start is None:
                            mood_start = scores.get("overall")
                        mood_end = scores.get("overall")
                        interp = interpret_scores(scores)
                        engine.messages.append({
                            "role": "user",
                            "content": (
                                f"[I just did a mood check-in. Results: "
                                f"overall={scores.get('overall')}/10, "
                                f"energy={scores.get('energy')}/10, "
                                f"anxiety={scores.get('anxiety')}/10, "
                                f"sleep={scores.get('sleep_quality')}/10. "
                                f"The interpretation was: {interp}]"
                            ),
                        })
                        engine.messages.append({
                            "role": "assistant",
                            "content": f"Thanks for checking in. {interp} What would you like to talk about?",
                        })
                        continue

                    elif cmd == "/deep":
                        scores = cli.run_survey(DEEP_CHECKIN, "Deep Well-Being Check")
                        if scores is None:
                            continue
                        cli.show_survey_results(scores)
                        _save_mood(db, session_id, scores)
                        if mood_start is None:
                            mood_start = scores.get("overall")
                        mood_end = scores.get("overall")
                        continue

                    elif cmd == "/mood":
                        moods = db.get_recent_moods(14)
                        cli.show_mood_history(moods)
                        continue

                    elif cmd == "/memory":
                        cli.show_memory(db)
                        continue

                    elif cmd == "/soul":
                        soul_text = soul.to_prompt_block()
                        if soul_text:
                            cli.show_text_panel("Soul Profile", soul_text, tone="accent")
                        else:
                            cli.show_notice("No soul profile yet. Run with --re-onboard to set one up.", tone="muted")
                        continue

                    elif cmd == "/stats":
                        cli.show_stats(db.get_stats())
                        continue

                    elif cmd == "/clear":
                        _end_session(engine, db, soul, session_id, mood_start, mood_end, governed_actions)
                        db.close()
                        db = WellnessDB()
                        memory = MemoryStore(db)
                        soul = SoulProfile(db)
                        governed_actions = _build_governed_actions(
                            db,
                            pangoclaw_mode=pangoclaw_mode,
                            socket_path=args.pangoclaw_socket,
                        )
                        provider = get_provider(provider_name, model)
                        engine = build_chat_engine(
                            db=db,
                            memory=memory,
                            provider=provider,
                            soul_profile=soul,
                            governed_actions=governed_actions,
                            feature_flags=feature_flags,
                        )
                        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
                        engine.start_session(session_id)
                        governed_actions.start_session(session_id)
                        mood_start = None
                        mood_end = None
                        cli.clear_screen()
                        cli.show_banner()
                        cli.show_provider_status(provider.name, provider.model)
                        cli.show_notice("New conversation started.", tone="success")
                        continue

                    elif cmd == "/switch":
                        _end_session(engine, db, soul, session_id, mood_start, mood_end, governed_actions)
                        db.close()
                        current_vault.lock(vault_session)
                        cli.clear_screen()
                        cli.show_banner()
                        cli.show_notice("Current identity locked. Choose another identity to continue.", tone="muted")
                        next_identity = _choose_identity(identity_manager)
                        next_vault = identity_manager.get_vault(next_identity.id)
                        next_session = _unlock_or_create_vault(identity_manager, next_identity)
                        current_identity = next_identity
                        current_vault = next_vault
                        vault_session = next_session
                        active_identity_label = cli.safe_identity_label(current_identity.label)
                        if active_identity_label:
                            cli.show_notice(f"Active identity: {active_identity_label}", tone="muted")
                        else:
                            cli.show_notice("Active identity selected.", tone="muted")
                        db = WellnessDB()
                        memory = MemoryStore(db)
                        soul = SoulProfile(db)
                        governed_actions = _build_governed_actions(
                            db,
                            pangoclaw_mode=pangoclaw_mode,
                            socket_path=args.pangoclaw_socket,
                        )
                        provider = get_provider(provider_name, model)
                        engine = build_chat_engine(
                            db=db,
                            memory=memory,
                            provider=provider,
                            soul_profile=soul,
                            governed_actions=governed_actions,
                            feature_flags=feature_flags,
                        )
                        if not soul.exists:
                            dynamic_gen = build_dynamic_onboarding_generator(
                                engine,
                                governed_actions,
                                feature_flags=feature_flags,
                            )
                            answers = cli.run_onboarding(ONBOARDING_QUESTIONS, dynamic_generator=dynamic_gen)
                            if answers.get("name"):
                                soul.store_onboarding(answers)
                                cli.show_notice("Profile saved inside the encrypted vault.", tone="success")
                            cli.clear_screen()
                            cli.show_banner()
                        else:
                            cli.show_returning_welcome(db.get_stats(), soul.name)
                        cli.show_provider_status(provider.name, provider.model)
                        if soul.exists:
                            cli.show_soul_loaded(soul.name)
                        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
                        engine.start_session(session_id)
                        governed_actions.start_session(session_id)
                        mood_start = None
                        mood_end = None
                        continue

                    elif cmd == "/export":
                        _export(db, governed_actions)
                        continue

                    elif cmd == "/name":
                        parts = text.split(maxsplit=1)
                        if len(parts) > 1:
                            db.set_profile("name", parts[1])
                            cli.show_notice(f"Got it, {parts[1]}.", tone="warning")
                        else:
                            cli.show_notice("Usage: /name YourName", tone="muted")
                        continue

                    else:
                        cli.show_notice("Unknown command. Use /help for options.", tone="muted")
                        continue

                # ── Crisis detection (client-side) ────────────────────
                if detect_crisis(text):
                    cli.show_crisis_banner()

                # ── Chat ──────────────────────────────────────────────
                cli.show_user_message(text, name=soul.name)
                cli.stream_ai_response(
                    engine.send_message(text),
                    on_interrupt=engine.cancel_pending_response,
                )

                # ── Autosave every 4 turns ────────────────────────────
                turn_count = engine.get_message_count() // 2
                if turn_count >= 4 and turn_count % 4 == 0:
                    threading.Thread(
                        target=_autosave_background,
                        args=(engine, db, soul, session_id, mood_start, mood_end, governed_actions),
                        daemon=True,
                    ).start()

        except KeyboardInterrupt:
            cli.console.print()
            _end_session(engine, db, soul, session_id, mood_start, mood_end, governed_actions)
        return 0
    finally:
        if db is not None:
            db.close()
        current_vault.lock(vault_session)


def _save_mood(db: WellnessDB, session_id: str, scores: dict):
    """Save mood survey results."""
    now = datetime.now(timezone.utc).isoformat()
    entry = MoodEntry(
        id=None,
        session_id=session_id,
        timestamp=now,
        overall=scores.get("overall", 5),
        energy=scores.get("energy", 5),
        anxiety=scores.get("anxiety", 5),
        sleep_quality=scores.get("sleep_quality", 5),
        notes=json.dumps({k: v for k, v in scores.items()
                          if k not in ("overall", "energy", "anxiety", "sleep_quality")}),
    )
    db.save_mood(entry)


_autosave_lock = threading.Lock()


def _autosave_background(
    engine: ChatEngine,
    db: WellnessDB,
    soul: SoulProfile,
    session_id: str,
    mood_start,
    mood_end,
    governed_actions: GovernedWellnessActions,
):
    """Run fact extraction + profile refinement in a background thread."""
    if not _autosave_lock.acquire(blocking=False):
        return  # another autosave already running
    try:
        cli.show_autosave_start()
        session_results = engine.end_session(mood_start=mood_start, mood_end=mood_end)
        profile_updated = soul.refine_from_conversation(
            engine.messages,
            engine._call_oneshot,
            governed_actions=governed_actions,
            session_id=session_id,
            crisis_stage=engine.safety.crisis_state.stage.value,
        )
        if any(session_results.values()) or profile_updated:
            cli.show_autosave_done()
        else:
            cli.show_notice("Governed autosave skipped or denied by policy.", tone="muted")
    except Exception:
        pass  # autosave is best-effort
    finally:
        _autosave_lock.release()


def _end_session(
    engine: ChatEngine,
    db: WellnessDB,
    soul: SoulProfile,
    session_id: str,
    mood_start,
    mood_end,
    governed_actions: GovernedWellnessActions,
):
    """Process learnings and refine the profile before vault lock."""
    engine.cancel_pending_response()

    # Wait for any in-flight autosave to finish before final save
    _autosave_lock.acquire()
    _autosave_lock.release()

    if engine.get_message_count() >= 4:
        cli.show_processing()
        session_results = engine.end_session(mood_start=mood_start, mood_end=mood_end)

        cli.show_processing("Updating profile from this conversation...")
        profile_updated = soul.refine_from_conversation(
            engine.messages,
            engine._call_oneshot,
            governed_actions=governed_actions,
            session_id=session_id,
            crisis_stage=engine.safety.crisis_state.stage.value,
        )
        if not any(session_results.values()) and not profile_updated:
            cli.show_notice("Governed session learnings skipped or denied by policy.", tone="warning")

    governed_actions.end_session(session_id)
    cli.show_session_end()


def _export(db: WellnessDB, governed_actions: GovernedWellnessActions):
    """Export conversation history to a plaintext JSON file outside the vault."""
    export_path = get_plain_export_path()
    cli.show_notice("Export writes plaintext JSON outside the encrypted vault.", tone="warning")
    messages = db.get_recent_messages(500)
    data = [{
        "session": m.session_id,
        "role": m.role,
        "content": m.content,
        "timestamp": m.timestamp,
        "crisis_flag": m.crisis_flag,
    } for m in messages]

    result = governed_actions.export_transcript(export_path=export_path, messages=data)
    if not result.executed:
        prefix = "Export failed" if result.decision.status == "error" else "Export blocked"
        cli.show_notice(f"{prefix}: {result.decision.reason}", tone="danger")
        return

    cli.show_notice(f"Exported {len(data)} messages to {export_path}", tone="success")


if __name__ == "__main__":
    raise SystemExit(main())
