# Moss — Mental Wellness Companion CLI

A polished terminal companion for mental wellness support. Uses your existing AI CLI login — no API keys needed.

Supports **Claude Code**, **Google Gemini CLI**, and **OpenAI Codex CLI** as interchangeable backends.

This package is the repo's reference terminal implementation of the broader prompt and safety guidance in the root documentation.

```
        \|/
       `-*-'
       (o o)   Moss
       /)_(\   mental wellness companion
        " "
```

The CLI now uses a mascot-led brand system: Moss shows up in the startup panel, assistant replies, and loading states so the interface feels like one coherent tool instead of generic Rich panels.

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd mental-wellness-prompts

# 2. Run the guided setup wizard
./moss
```

That is the launcher.

The launcher installs dependencies silently and, on first run, opens a guided setup wizard before the companion starts.

If you want Moss as an installable dependency instead of an embedded repo checkout:

```bash
python3 -m pip install -e .
moss
```

That installs the `moss` console entry point and exposes a small Python API under `moss_core`.

First run opens a guided setup wizard that covers provider/model choice, PangoClaw mode, storage location, identity selection, vault creation, and profile onboarding. On later runs, Moss uses the saved wizard defaults unless you override them or re-open the wizard.

## Why Conversations Here Feel Different

Moss is designed to be more useful than a stateless terminal wrapper around a model.

- **Local memory, not cloud memory** - conversation history, extracted facts, mood trends, and your generated profile stay on your machine, so continuity does not require a hosted account.
- **Encrypted at rest** - each local identity gets its own passphrase-protected vault instead of leaving the database on disk in plaintext.
- **Optional iCloud placement on macOS** - if you want backup/sync, Moss can place only the sealed encrypted vault files in iCloud Drive while keeping unlocked runtime files local.
- **Open source behavior** - the launcher, UI, memory system, safety rules, and prompt-shaping logic are in this repo, which means you can inspect the exact behavior and change it when it does not fit.
- **Provider freedom** - the same companion can run on Claude Code, Gemini CLI, or Codex CLI, so you can keep the experience and swap the model backend.
- **Human-readable personality while unlocked** - `SOUL.md` and `AGENTS.md` are still generated for the running session, but they are rebuilt inside the unlocked runtime instead of being left on disk between sessions.
- **Quiet by default** - background work is intentionally hidden so the UI stays calm, while live animated panels still show you that something is happening.
- **Built for repeated use** - the system remembers what helps, what does not, and what has been discussed before, which makes later conversations less repetitive and more grounded.

## Prerequisites

You need **one** of these CLI tools installed and authenticated:

| Provider | Install | Auth |
|----------|---------|------|
| **Claude Code** (default) | [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code) | `claude` — follow login prompts |
| **Gemini CLI** | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) | `gemini` — Google account login |
| **Codex CLI** | [github.com/openai/codex](https://github.com/openai/codex) | `codex` — OpenAI account login |

Python 3.9+ is required. Dependencies (`rich`, `chromadb`, `cryptography`) are installed automatically by the launcher or installed through `pip install -e .`.

## Usage

```bash
# Default: use saved wizard defaults, or walk first-run setup
./moss

# Re-open the guided startup wizard
./moss setup

# Run diagnostics only
./moss doctor

# Override the saved provider for this run
./moss --provider gemini
./moss --provider codex

# Pick a specific model
./moss -p claude -m sonnet
./moss -p gemini -m gemini-2.5-pro
./moss -p gemini -m gemini-3.1-pro-preview
./moss -p codex -m gpt-5.4-mini

# Force PangoClaw-governed side effects off for this run
./moss --no-pangoclaw

# Reset everything (wipes all identities, vaults, memory, history)
./moss --reset

# Redo the onboarding questions
./moss --re-onboard

# Skip AI-generated onboarding follow-up questions
./moss --no-dynamic-onboarding

# Disable the Python supervisor explicitly (embedding/dev only)
./moss --unsafe-disable-safety-supervisor
```

Or run directly with Python:

```bash
python3 -m wellness_cli --provider gemini --model gemini-2.5-flash
```

If you do not pass `--model`, Moss uses the saved wizard choice for that provider or asks you to choose one.

## Python Dependency Use

You can also consume Moss as a Python dependency instead of embedding this repo directly:

```python
from moss_core import MossFeatureFlags, build_chat_engine, build_dynamic_onboarding_generator
from moss_core import WellnessSafetySupervisor, NoOpSafetySupervisor
```

Recommended split:

- Use `moss_core` for reusable engine, provider, governance, and supervisor pieces.
- Use the `moss` console script or `python -m wellness_cli` for the packaged terminal app.

Feature toggles for embeddings:

- Dynamic onboarding follow-ups are optional through `MossFeatureFlags(enable_dynamic_onboarding_followups=False)`.
- The Python supervisor is pluggable through `build_chat_engine(..., safety_supervisor=...)`.
- If you intentionally disable it, `NoOpSafetySupervisor` is available for non-wellness embeddings and tests.

## Available Models (March 2026)

| Provider | Prompt default | Other options |
|----------|----------------|---------------|
| Claude | `opus` (claude-opus-4-6) | `sonnet` (claude-sonnet-4-6), `haiku` (claude-haiku-4-5) |
| Gemini | `gemini-3.1-pro-preview` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |
| Codex | `gpt-5.4` | `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.3-codex-spark` |

## In-Chat Commands

Once running, these slash commands are available:

| Command | What it does |
|---------|-------------|
| `/checkin` | Quick mood survey (4 questions) with visual health bars |
| `/deep` | Deep well-being survey (8 questions) |
| `/mood` | View mood history, sparkline trends, and analysis |
| `/soul` | View your generated personality profile |
| `/memory` | See what the companion remembers about you |
| `/stats` | Session and usage statistics |
| `/clear` | Start a fresh conversation (saves the current one first) |
| `/switch` | Re-lock the current identity, switch identities, and re-authenticate |
| `/export` | Export conversation history to plaintext `~/wellness_export.json` |
| `/name` | Update your display name |
| `/help` | Show the command menu |
| `/quit` | End session, save learnings, and exit |

## How It Works

### Architecture

```
┌──────────────┐     ┌────────────────────────────┐     ┌──────────────┐
│  CLI UI      │────▶│  Chat Engine              │────▶│  Provider    │
│  (Rich)      │     │  + Python safety          │     │  (claude/    │
│  modern UI   │◀────│  supervisor               │◀────│   gemini/    │
│  animations  │     │  + stream release guard   │     │   codex)     │
└──────────────┘     └─────────────┬──────────────┘     └──────────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
               ┌─────┴──────┐          ┌─────────┴─────────┐
               │ Encrypted  │          │ Governed side     │
               │ SQLite DB  │          │ effects via       │
               │ messages   │          │ PangoClaw sidecar │
               │ profile    │          │ policy gates +    │
               │ audit log  │          │ local audit trail │
               └─────┬──────┘          └─────────┬─────────┘
                     │                            │
               ┌─────┴─────┐                memory.extract_facts
               │ In-memory │                memory.summarize_session
               │ Chroma    │                profile.refine
               │ index     │                export.transcript
               └───────────┘                onboarding.followup_question
```

### Split Safety Architecture

Moss now uses a deliberate split:

- **Conversational safety stays inside Moss in Python.** `wellness_cli/safety_supervisor.py` classifies inbound user text, tracks session-level crisis state, and screens streamed assistant output before it reaches the terminal.
- **PangoClaw is only for governed side effects.** It does not sit in front of every conversation turn. It policy-checks and audits autonomous actions such as fact extraction, session summarization, profile refinement, onboarding follow-up generation, and plaintext transcript export.

That split matters. The main conversation path needs deterministic, low-latency wellness rules close to the UI and provider stream. Side effects need approval, auditability, and fail-closed behavior.

The Python supervisor does not call a local CLI LLM. It is local rule code plus session state. The local provider CLIs are still used for the main conversation and for governed background oneshot tasks.

### The Soul System

On first run, the companion asks 5 starter questions plus up to 2 AI-generated follow-ups based on your answers. From these, it builds two files for the unlocked runtime session:

- **SOUL.md** — Who the companion is and how it relates to you. Under 350 words. Includes your name, situation, what helps, what doesn't, and an auto-detected communication style (brief vs verbose, warm vs direct, experienced vs new to this).

- **AGENTS.md** — Operational rules. Response length limits, memory usage, crisis protocol, escalation triggers, formatting rules.

They stay human-readable while the app is running, and the underlying profile data is persisted inside the encrypted vault. The soul profile refines itself after each conversation based on what it learns.

### Memory

The companion remembers across sessions:

- **Facts** — things it learns about you (extracted by the AI after each session)
- **Session summaries** — what you talked about and key themes
- **Mood trends** — sparkline visualizations of your check-in scores over time
- **Semantic search** — an in-memory Chroma index is rebuilt from the encrypted database on unlock to include relevant past conversations as context

### Crisis Detection

Client-side regex patterns (sub-1ms) still scan every message for crisis language across direct and indirect indicators. False-positive filtering catches idioms like "killing it" or "to die for." When triggered, crisis resources appear immediately in a high-visibility alert panel.

The companion does **not** attempt crisis intervention. It provides resources and stays present.

After a crisis turn, Moss keeps the session in a stricter follow-up state. In that mode, the Python supervisor blocks unsafe drift such as diagnosis, medication advice, dependency framing, prompt leakage, tool syntax, and crisis-assessment language before it reaches the terminal.

### Running With Or Without PangoClaw

With PangoClaw available:

```bash
export PANGOCLAW_SOCKET=/tmp/pangoclaw.sock
./moss
```

Moss talks to the local sidecar over HTTP on the Unix socket and uses the current contract through `wellness_cli/governance.py`. The routes Moss uses today are:

- `GET /status`
- `POST /session/start`
- `POST /session/end`
- `POST /gate/before-tool-call`
- `POST /gate/after-tool-call`
- `POST /gate/message-sending`

`governance.py` is the only translation layer. Main conversational safety still lives in `wellness_cli/safety_supervisor.py`.

The sidecar is local-first. It relies on Unix socket filesystem permissions on the developer machine rather than a shared production control plane. If this project later needs shared or production governance, that should point to Glacis Shield instead of stretching the local sidecar model.

Without PangoClaw:

```bash
./moss --no-pangoclaw
```

The chat path still works. Governed side effects fail closed instead:

- onboarding follow-up question generation is skipped
- fact extraction and session summarization are skipped
- profile refinement is skipped
- `/export` is blocked

You can also choose this mode in the guided setup wizard. If you omit `--no-pangoclaw`, Moss uses the wizard's saved preference and the configured socket path.

## Data Storage

Encrypted local state is stored at `~/.wellness_companion/`:

```
~/.wellness_companion/
├── users.json         # Identity registry
└── users/
    ├── default/
    │   ├── vault.json # Vault metadata (KDF params, salt, version)
    │   └── vault.bin  # Encrypted SQLite payload
    └── joe/
        ├── vault.json
        └── vault.bin
```

`SOUL.md`, `AGENTS.md`, and the live SQLite file exist only inside the unlocked runtime directory during the session and are removed when that identity's vault is sealed again.

Each identity has its own password. Switching identities re-locks the current vault and prompts for the target identity's password before opening it.

Nothing is sent anywhere except to the AI provider you choose (via its local CLI). No telemetry, no cloud sync, no hosted accounts.

`/export` is intentionally different: it writes plaintext JSON outside the vault as an explicit user action, and it now goes through the governed side-effect path before anything is written.

There is currently no password reset or recovery flow. If you forget an identity's password, that identity's encrypted data cannot be recovered.

On macOS, you can opt into storing the sealed encrypted vault files in iCloud Drive instead:

```
~/Library/Mobile Documents/com~apple~CloudDocs/Moss Vaults/
```

Only the encrypted vault files live there. The unlocked runtime database, `SOUL.md`, and `AGENTS.md` stay in a local temporary directory. If you use iCloud, avoid opening the same identity on two Macs at the same time.

To wipe everything: `./moss --reset`

## Project Structure

```
wellness_cli/
├── __init__.py        # Package marker
├── __main__.py        # Entry point, command handling, main loop
├── cli.py             # Terminal UI (Rich), animations, branded conversation panels
├── chat_engine.py     # Provider-agnostic conversation engine
├── safety_supervisor.py # Python-native conversational safety + crisis state
├── governance.py      # PangoClaw sidecar client + governed side-effect runner
├── runtime.py         # Reusable factory + feature-toggle helpers
├── providers.py       # Claude/Gemini/Codex CLI abstraction layer
├── paths.py           # Runtime-aware storage path helpers
├── soul.py            # SOUL.md + AGENTS.md generation and refinement
├── memory.py          # ChromaDB vector memory + fact extraction
├── vault.py           # Passphrase-derived local encryption vault
├── surveys.py         # Mood check-in questionnaires
└── db.py              # SQLite persistence layer
```

```
moss_core/
└── __init__.py        # Dependency-friendly public import namespace
```

## Important Disclaimers

This is a **supportive companion**, not therapy. It does not diagnose, prescribe, or treat. It does not replace professional mental health care. If you're in crisis, please contact a professional:

- **US**: 988 (Suicide & Crisis Lifeline) or text HOME to 741741
- **UK**: 116 123 (Samaritans)
- **CA**: 1-833-456-4566
- **AU**: 13 11 14

See `safety_crisis_resources.md` in the parent repo for the full list of resources across 29 countries.

## License

Open source. Originally developed for [Yara AI](https://github.com) through 12+ months of systematic testing. Released freely for public benefit.

In memory of Chris Paley-Smith and all those fighting for mental wellness and positivity.
