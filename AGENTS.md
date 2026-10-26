# AI Agent Instructions for Eclipse Workspace

## 🏷️ Repository Identity & Distinction
- **Eclipse (`https://github.com/InsomniacZero/Eclipse`) [THIS WORKSPACE]**:
  - The public, standalone Gemini Web, Claude & frontier AI gateway repository.
  - Fully built and developed by InsomniacZero.
  - Heavy focus on user-friendliness, streamlined pure-Python architecture (`StarletteGateway` / zero Rust compilation on mobile), unified Control Center & Playground UI, and SillyTavern / Janitor AI character roleplay integration.
  - **Invariant**: Eclipse is completely decoupled from private parent projects. All runtime code lives purely in `eclipse/`.

---

## ⚠️ Essential Project Rules
1. **NO GIT PUSH**: Never push code or tokens to GitHub (`git push` is forbidden unless explicitly asked by the user).
2. **NO BROWSER / CHROME AUTOMATION**: Do not open Chrome or use browser subagents unless explicitly instructed.
3. **PREFER REPO CLI (`./start.sh` or `start.bat`)**: When checking accounts, verifying quotas/limits, testing models, or checking status, **DO NOT** write multi-line Python scratch scripts or raw curl commands. **Always use the built-in CLI tool (`./start.sh` / `start.bat`)**.
4. **PORT 5000 INVARIANT**: Eclipse listens on port `5000` (`http://localhost:5000/v1`). Never hardcode or conflict with other port configurations.
5. **ZERO RUST BUILD TOOLCHAINS ON MOBILE**: Eclipse runs on pure Python with `StarletteGateway` and `uvicorn`. Never add `pydantic` or `fastapi` to `requirements.txt`. Startup dependency checks must verify pure packages (`starlette, uvicorn, httpx`) so phone installation completes in 3–5 seconds without Cargo/Rust compilation.
6. **ARCHITECTURE MANUAL**: Consult [ARCHITECTURE.md](ARCHITECTURE.md) for the full architectural blueprint, request lifecycle, engine protocol specifications, and data flow pipelines.
7. **CANONICAL DUAL-LAUNCHER INVARIANT**: Strictly two launchers: `./start.sh` (Unix/macOS/Termux) and `start.bat` (Windows). `start.command` is only a macOS double-click shim that executes `start.sh`.

---

## ⚙️ Core Architectural & Operational Doctrines

### 1. The Clockwork Cog Doctrine (Systemic Dependency Awareness)
Every file, prompt, schema, and engine in this codebase is an interlocking gear.
- **Before modifying any component**, trace its upstream callers and downstream consumers (e.g. modifying a model name affects `MODELS_CATALOG`, `resolve_model_provider`, engine configs, and the frontend selector; modifying a database schema affects migrations, serializers, and sync loops).
- Never treat any script or file as an isolated silo. Think, trace, and verify dependencies across the entire pipeline.

### 2. The Root Cause Excision Doctrine (No Pink Elephant Patch Bloat)
- **The Chronic Failure Mode**: When an agent introduces a flawed behavior or buggy condition and the user complains, the agent piles on a negative constraint ("Anti-X Patch", e.g. *"Do NOT stare", "Never do X"* or negative prompt conditionals).
- **The Pink Elephant Problem**: Stating negative constraints forces the unwanted concept directly into an LLM's active attention window, doubles token bloat, and leaves brittle band-aids over flawed foundations.
- **The Mandatory Protocol**:
  1. Locate the **original root cause** line or faulty logic.
  2. **DELETE IT ENTIRELY.**
  3. Rewrite the behavior with **clean, positive, intentional grounding** (state what the system *should* do, not what it shouldn't).
  4. Zero negative patch clutter or layered band-aids.

### 3. Deterministic Ground Truth (Zero Hallucinated Metrics)
- Never guess, estimate, or state token counts, quotas, or response timings from thin air.
- Word counts $\neq$ BPE token counts (special tokens, punctuation, and markdown inflate tokens by 1.3–1.7x).
- Run deterministic tools (`tools/count_tokens.py`, `./start.sh limits`, or live CLI queries) to verify exact numbers before concluding a task.

### 4. Anti-Sycophancy & Technical Pushback
- You are strictly forbidden from acting as a passive "yes-man" or blindly implementing flawed instructions.
- If an instruction is **contradictory**, **technically harmful**, or **architecturally corrupting**:
  1. Politely and firmly challenge the premise.
  2. Clearly explain the technical conflict and what components will break.
  3. Prescribe the clean, robust architectural refactoring to achieve the user's underlying goal.

### 5. Strict Real-Live Verification (No Fake Simulations)
- NEVER test fixes or claim endpoints work using `--simulate` when verifying live provider functionality.
- Execute real upstream requests using `./start.sh chat "<prompt>" -m <model>` to confirm real HTTP transport, cookie auth, response tokens, and media downloads.

### 6. The 5-Step Pre-Flight Verification Checklist
Before concluding any feature, fix, or prompt change:
1. **Source Ground Truth**: Check actual novel canon, official API docs, or live server contracts.
2. **Dependency Trace**: Verify all linked files (configs, catalogs, frontend handlers, database queries).
3. **Syntax & AST Validation**: Run `node --check <file>.js` or `python3 -m py_compile <file>.py`.
4. **Deterministic Measurement**: Audit token counts, response codes, and schemas deterministically.
5. **Regression Check**: Ensure existing launchers, CLI subcommands, and desktop/mobile layouts remain unbroken.

---

## 🚀 Eclipse Unified CLI (`./start.sh` / `start.bat`) Reference

The unified CLI tool is located in the repository root:
`./start.sh` (Unix/macOS/Termux) or `start.bat` (Windows)

```bash
# 1. Inspect Fleet Status & Database Vault
./start.sh status                    # Live status of all providers & accounts summary
./start.sh status --json             # Compact JSON output for scripting

# 2. Live Limits & Quotas Across Providers
./start.sh limits                    # Real-time limits & remaining quotas
./start.sh limits --json             # Structured JSON limits payload

# 3. Account Vault Management (SQLite)
./start.sh accounts                  # List all stacked accounts across providers
./start.sh accounts gemini           # Filter accounts by provider (gemini, antigravity, etc.)
./start.sh import <path_or_json>     # Import credentials dump into SQLite vault
./start.sh export [backup.json]      # Export portable credential vault to JSON
./start.sh autofetch gemini          # 1-Click auto-discovery of Gemini cookies from local browsers
./start.sh login                     # 1-Click Google OAuth login

# 4. Fast Live Model Inference & Testing (Authentic upstream calls)
./start.sh chat "What is 2+2?" -m gemini-4-argon              # Quick streaming chat test
./start.sh chat "Hello" -m gemini-3.8-flash                  # Gemini Flash test

# 5. Gateway Server Control (Eclipse Gateway :5000)
./start.sh                         # Linux / macOS / Termux
start.bat                          # Windows (native cmd/powershell)
./start.sh restart                 # Clean port 5000 reclaim and gateway restart

# 6. Cloud Tunnel & Native Remote Mobile Access (ngrok)
./start.sh tunnel                  # Inspect tunnel state & public HTTPS URL
./start.sh tunnel start            # Expose gateway securely to the internet
./start.sh tunnel stop             # Stop active public tunnel
./start.sh tunnel install          # Auto-install native ngrok binary (Phone Termux / PC)
./start.sh tunnel token <token>    # Set ngrok authtoken
```

---

## 📝 Engineering Lessons & Post-Mortem Playbook

### 1. Authentication, Tokens & Cookies
- **Google Gemini Authentication**: Requires `__Secure-1PSID` and `__Secure-1PSIDTS`. Extract `SNlM0e` XSRF token and `bl` build label from `/app`. Attach `Authorization: SAPISIDHASH <ts>_<sha1>` derived from `SAPISID`. Sort vault accounts `ORDER BY id DESC` so newest credentials take priority. Validate sessions via `/app` extraction instead of parameterless `batchexecute`.
- **1-Click Browser Auto-Discovery**: Auto-fetch searches Chrome, Brave, Edge, Chromium, and Firefox SQLite cookie vaults (`Cookies` / `cookies.sqlite`), decrypts OS-level keys (`DPAPI` on Windows, `peanuts` on Linux, Keychain on macOS), and validates credentials with upstream Google before saving to the SQLite vault.
- **cURL Header Dump & Token Ingestion Defense**: In `eclipse/db.py` (`parse_credential`), specifically detect cURL commands and extract solely the `Cookie:` header value, rejecting arbitrary HTTP header lines (`-H "..."`) to prevent database vault pollution from phantom accounts.
- **Zhipu GLM Guest Sessions & 429 Healer**: Anonymous guest mode requires zero credentials. When encountering HTTP 429 upstream rate limits, catch the exception, discard the exhausted guest token, and immediately re-generate a new session token to guarantee uninterrupted chat stream flow.

### 2. Gateway Security & Sandbox Invariants
- **Access Control**: Keep `eclipse/security.py` as the open gateway policy allowing seamless connections from JanitorAI, SillyTavern, and custom clients.
- **Artifact Sandboxing**: GenUI blocks (`※genui※`) must route through `eclipse/artifacts.py` to `<antArtifact>`. The artifact iframe must **never** have `allow-same-origin`. Storage APIs run through `withSandboxShims()`. Secrets must be encrypted via `eclipse/vault.py`—never store raw tokens in the `identifier` column.
- **Route Table Immutability**: Starlette compiles its route handlers into internal data structures at application instantiation. Modifying routes on `@app` requires a clean gateway restart (`./start.sh restart`), as module hot-reloading does not re-bind Starlette route tables.

### 3. Termux, Mobile & OS Compatibility
- **Zero Rust Compilation**: Keep `requirements.txt` strictly pure Python (`starlette, uvicorn, httpx`). Never introduce `pydantic` or `fastapi` which trigger `cargo` compilations on Termux.
- **Architecture Mismatch**: On Android Termux, 64-bit kernels (`aarch64`) often run 32-bit userlands (`armhf`). Always verify ELF runnable status (`ngrok version`) before executing downloaded binaries.
- **Windows Batch Traps**: Never use raw unescaped parentheses inside `if (...)` blocks in `.bat` files. Use square brackets `[v22+]` or escape them `^)`. Escape ampersands `^&`.
- **Responsive CLI**: Avoid rigid fixed-width text frames (`"=" * 66`) that wrap and shatter on narrow mobile terminals. Use clean indentation and soft status dots. Silence Uvicorn HTTP access logs by default to prevent stdout pollution.
