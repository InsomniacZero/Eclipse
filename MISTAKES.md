# AI Agent Mistakes Log & Architectural Invariants for Eclipse

This document is a persistent record of past failures, UI/UX missteps, technical lessons, and strict architectural rules for AI agents and developers working on the **Eclipse** codebase.

> **Mandatory Agent Rule:** Consult this file before making changes. Whenever you encounter a bug, receive a correction from the user, or solve a tricky edge case, **you must update this file with the new mistake, rationale, and preventative rule.**

---

## 🚫 1. Absolute Workspace & Repository Boundaries

### 1.1 Never Push to GitHub Unless Explicitly Commanded
- **Mistake**: Automatically running `git push` or syncing branches to GitHub without direct instructions.
- **Rule**: `git push` is **strictly forbidden** unless the user explicitly commands it in their prompt. All commits stay local until commanded.

### 1.2 Leave the `TAVERN/` Directory Untouched
- **Mistake**: Modifying files inside `/home/insomniac/Desktop/UNI/Apps/Gemini Web2Api/Eclipse/TAVERN` while implementing integration.
- **Rule**: The existing `TAVERN/` folder is sacred and must remain untouched. Any code, assets, or concepts ported to Eclipse must live entirely within `eclipse/`.

### 1.3 Zero Legacy Dependencies
- **Mistake**: Importing, executing, or referencing files in `legacy/` at runtime.
- **Rule**: `legacy/` is purely for read-only reference. All runtime engines, routers, and assets must be self-contained in `eclipse/`.

---

## 🛡️ 2. The "Zero-Pollution" Optional Feature Rule

### 2.1 Tavern Integration Must Never Hinder or Break Base Eclipse
- **Mistake**: Tightly coupling new features (like Tavern roleplay or visual novels) into core gateway routines, causing the main playground or server to crash or slow down if Tavern assets are absent.
- **Rule**: **Tavern is 100% optional.**
  - If a user only wants the Claude-style Playground, the Control Center, or the OpenAI-compatible Gateway (`:9000/v1`), they must experience **zero performance degradation, zero UI clutter, and zero breaking changes**.
  - Backend routes for Tavern must be cleanly encapsulated in an isolated module (e.g. `eclipse/tavern.py`), mounted safely under `/api/tavern/...`.
  - Frontend components for Tavern must live in `eclipse/static/tavern/` and only mount when the user explicitly navigates to the `🏰 Tavern` tab.
  - Failures in character card parsing or avatar storage must fail gracefully with localized error banners and never crash the main Gateway process.

---

## 🎨 3. UI, Typography & Design Invariants

### 3.1 Never Use Personal Names in Generic UI
- **Mistake**: Using the user's personal name (e.g. "Anirban") in welcome headers, dialogue prompts, or greeting cards.
- **Rule**: Always use neutral, stylish branding or customizable placeholders (e.g. "Welcome back", "How can I help you today?", or dynamic persona names).

### 3.2 Do Not Shrink Font Sizes to Fix Container Overflow
- **Mistake**: Making text smaller on long dialogue options or action chips to force them onto one line, which looked weird, unbalanced, and hard to read.
- **Rule**: Keep text sizing consistent. If text is long, widen the container or allow natural horizontal/flex breathing room instead of arbitrarily shrinking typography.

### 3.3 Eliminate Jittery Popups and Abrupt Transforms
- **Mistake**: Having sidebars or menus popup jittery from the bottom or snap without easing.
- **Rule**: Use smooth, hardware-accelerated transitions (`cubic-bezier(0.16, 1, 0.3, 1)`, `transform: translateX(...)`). The sidebar must slide smoothly from the side, with hover previews staying fluid.

### 3.4 Button & Pill Hover Clipping
- **Mistake**: Placing action buttons inside containers with `overflow: hidden` where subtle scale-ups (`transform: scale(1.02)`) or top borders get clipped at the container edge.
- **Rule**: Ensure parent containers have adequate vertical padding (`padding: 4px 0` or `overflow: visible`) so elevated or transformed buttons have full breathing room.

### 3.5 Consistent Color Tokens & Subtle Contrasts
- **Mistake**: Using mismatched backgrounds or harsh borders on dropdowns and selectors.
- **Rule**: The model selector background must match the chatbox container background (`--bg-input`), highlighting with a subtle greyish tint only on hover. Never use high-contrast outlines when a soft subtle highlight is required.

---

## ⚡ 4. Developer Velocity: Zero-Build vs. Heavy Toolchains

### 4.1 Avoiding TypeScript & Vite Build Bloat in Eclipse
- **Mistake**: Pulling heavy TypeScript/Vite/npm build chains into Eclipse's frontend, requiring multi-minute builds, broken typecheck barriers, and complex hot-reload configurations just to tweak a button.
- **Rule**: Keep Eclipse frontend **pure vanilla ES6+ and CSS**:
  - Zero compilation step.
  - Edit a file → press F5 in browser → instantly live in 5 milliseconds.
  - Native browser `import` / `export` ES modules for clean code splitting.
  - All character parsing (SillyTavern PNG chunks, JSON schemas) implemented in lightweight, browser-native JavaScript (`DataView`, `TextDecoder`).

---

## ⚙️ 5. Gateway & Engine Technical Pitfalls

### 5.1 Incomplete Model Discovery (Surface-Level Research)
- **Mistake**: In the DeepSeek integration, research stopped at legacy V3/R1 endpoints, missing newer V4 / V4.1 releases until pointed out.
- **Rule**: Always perform targeted web searches for current-year releases, aliases, and reasoning flags before cataloging models in `eclipse/providers.py`.

### 5.2 Strict One-File Engine Architecture
- **Mistake**: Adding auxiliary files (`deepseek_pow.js`, `deepseek_pow.py`) into `eclipse/engines/`.
- **Rule**: Every provider must have **strictly ONE file** in `eclipse/engines/<provider>.py`. Inline helper scripts, WASM loaders, or PoW routines directly within that module.

### 5.3 Git Ignore Safeguards for Binaries & Data
- **Mistake**: Placing `.wasm` or font files in directories that were globally ignored in `.gitignore`, causing deployments on fresh clones to fail.
- **Rule**: Whitelist required runtime assets explicitly in `.gitignore` (e.g. `!eclipse/data/*.wasm`, `.otf` fonts), while keeping large temporary archives (`*.zip`) excluded.

### 5.4 Outdated Client Headers
- **Mistake**: Copying legacy Android client headers (`DeepSeek/1.0.13 Android/35`) causing APIs to return `CLIENT_VERSION_TOO_LOW`.
- **Rule**: Emulate modern browser client headers (`x-client-platform: web`, latest Chrome/Firefox user agents).

### 5.5 Avoid Self-Recursive Reverse-Proxy Loops
- **Mistake**: Leaving an upstream fetch inside an engine worker that forwarded back to its own listening port, causing an infinite loop.
- **Rule**: Engine files are the backend implementations themselves; they must execute native logic or forward to upstream provider domains, never to their own local port.

### 5.6 Zero Rust Toolchain & Lean Mobile Python Dependencies (No Pydantic/FastAPI)
- **Mistake**: Inadvertently adding `fastapi` and `pydantic` to `requirements.txt` or startup checks. On Android (Termux), `pip install pydantic` pulls `pydantic-core`, which requires compiling Rust with `cargo`, hanging for hours or failing entirely on phones.
- **Rule**: Eclipse runs on pure Python with `StarletteGateway` and `uvicorn`. Neither `pydantic` nor `fastapi` is required. Never add `pydantic`, `fastapi`, or any package requiring a Rust/C build toolchain to `requirements.txt`. Startup checks in `start.sh` must strictly verify lightweight pure packages (`starlette, uvicorn, httpx`) so installation completes in 3–5 seconds on phones.

### 5.7 Android Termux Userspace vs. Kernel Architecture Detection for Native Binaries
- **Mistake**: Relying solely on `uname -m` or `platform.machine()` to choose native binaries (e.g. ngrok) on Android Termux. On many devices, a 64-bit kernel (`aarch64`) hosts a 32-bit Termux userspace (`arm` / `armhf`). Attempting to execute a 64-bit ELF binary on a 32-bit userspace crashes with `[Errno 8] Exec format error`. Furthermore, checking file existence or `os.access(path, os.X_OK)` returns `True` even for mismatched ELF architectures.
- **Rule**: Never trust kernel architecture or executable bits alone on Android/Termux:
  1. Detect userspace architecture via `dpkg --print-architecture` and pointer width (`sys.maxsize > 2**32`).
  2. Every candidate binary must pass `is_binary_runnable` (`ngrok version`) before being accepted or executed.
  3. Implement automatic architecture fallback (e.g. if `arm64` triggers `Exec format error`, immediately fetch and verify 32-bit `arm`).
  4. Auto-detect and purge corrupted or mismatched binaries from `$PREFIX/bin/` and `eclipse/bin/` on startup.

### 5.8 Windows Batch Parenthesis & Special Character Escaping
- **Mistake**: Placing raw parentheses inside CMD `if (...)` blocks in Windows `.bat` scripts (e.g. `echo Please install Node.js (v22+)` or `echo (first-time setup)`). In `cmd.exe`, an unescaped closing parenthesis `)` prematurely closes the `if` block, throwing `... was unexpected at this time`.
- **Rule**: Never place unescaped parentheses inside `if (...)` blocks in Windows batch files. Use square brackets `[v22+]` or escape them with a caret `^)`. Always escape ampersands `^&` in echo statements so CMD does not parse them as command separators.

---

## 🔄 6. Maintenance & Error Log

Whenever an issue is identified or a user corrects a behavior, log the entry below:

- **2026-09-20 (UI Typography & Claude Parity)**: Replaced generic system sans fonts with official Anthropic webfonts (`Anthropic Sans` & `Anthropic Serif`) and aligned tokens with Claude's visual polish.
- **2026-09-20 (Dialogue Chip Overflow)**: Fixed dialogue suggestion chips by widening the prompt chip container and preventing text shrink hacks.
- **2026-09-21 (Tavern Integration Boundaries)**: Established rule that `TAVERN/` remains untouched, Tavern integration in Eclipse is 100% optional, and the frontend will use pure zero-build vanilla JS/CSS to avoid Vite/TypeScript build delays.
- **2026-09-23 (Product Identity & Naming Invariant)**:
  - *Mistake*: Naming features "Claude Artifact System" or adopting 3rd-party product names.
  - *Rule*: We are building **Eclipse**, not Claude or any external vendor. All features and future products must be explicitly branded as **Eclipse** (e.g. **Eclipse Artifacts**, **Eclipse Workbench**, **Eclipse Gateway**). Never brand internal features under another company's name.
- **2026-09-23 (React Artifact Sandbox Compilation & Babel DOM Scanner Avoidance)**:
  - *Mistake*: Relying on Babel Standalone's automatic in-browser DOM scanner (`<script type="text/babel">`) with `data-presets`. When Babel encountered unstripped imports, attribute strings, or redeclared variables, its internal script runner crashed with `Uncaught TypeError: "" is not a function`.
  - *Rule*: Never rely on Babel Standalone's in-browser `<script type="text/babel">` automatic scanner. Instead, always use **programmatic compilation** inside a standard `<script>` tag:
    1. Pass the sanitized source code safely via `JSON.stringify(code).replace(/<\/script/gi, '<\\/script')`.
    2. Directly invoke `Babel.transform(rawCode, { presets: ['react'] }).code` inside a `try / catch` block.
    3. Instantiate and mount the resulting component via `new Function(...)` with provided React hooks, helper utilities (`cn`, `clsx`, `twMerge`), Lucide Icon SVG proxies, and motion stubs.
- **2026-09-23 (React Artifact Sandbox `srcdoc` Iframe Opaque Origin & Error Boundary Positioning)**:
  - *Mistake*: The artifact preview `<iframe>` used `sandbox="allow-scripts allow-forms allow-modals"` without `allow-same-origin`. In Chromium/WebKit, an `about:srcdoc` document with an opaque origin (`null`) fails to resolve relative paths like `/static/vendor/react.min.js`, throwing `net::ERR_UNKNOWN_URL_SCHEME` and failing script loads. Compounding the issue, the `#error-boundary` container was placed *after* `<div id="root"></div>` with `min-height: 100vh`, pushing initialization errors completely below the fold so the user only saw a pitch-black screen.
  - *Rule*: Inject `<base href="${window.location.origin}/"/>` into the iframe `<head>`, point scripts to absolute origin paths with CDN `onerror` fallbacks, and anchor `#error-boundary` at `position: fixed; top: 16px; left: 16px; right: 16px; z-index: 999999;` so any runtime or syntax error is immediately visible above the fold.
  - *Superseded (2026-09-26 security audit)*: `allow-same-origin` must **not** be used. Combined with `allow-scripts` it gives model-generated code the dashboard's origin, letting a prompt-injected artifact call `/api/cookies/export`. The `<base href>` alone fixes path resolution; `withSandboxShims()` supplies in-memory `localStorage`/`sessionStorage`.
- **2026-09-23 (ChatGPT Canvas `※genui※` Raw Dump Conversion to Eclipse Artifacts)**:
  - *Mistake*: When prompting ChatGPT models (`gpt-5.6-sol`, `chatgpt`) for interactive CSS or web applications, the model outputted OpenAI's internal Canvas format: `※genui※{"app_block":{"title":"...","content":"..."}}※`. Because neither the backend nor frontend intercepted this delimiter, the raw JSON payload was dumped into the user's chat message bubble.
  - *Rule*: Universal GenUI interceptor must always be active in `eclipse/artifacts.py` and `eclipse/static/app.js`: automatically extract the `app_block` JSON (or streaming partial matches), extract the title and HTML/CSS/JS content, and convert it into `<antArtifact identifier="..." type="text/html" title="...">...` so that any interactive app emitted by ChatGPT renders as a first-class Eclipse Artifact with live preview and code inspection tabs.
- **2026-09-23 (Fatal Unescaped Newline in Template Literal Script Generation & Parent Globals Fallback)**:
  - *Mistake*: In `buildReactSandboxHtml`, the string `'React Component Render Error:\n'` was written inside a multiline template string literal. At runtime in `app.js`, `\n` was interpolated into the HTML string as a literal raw newline inside single quotes (`'...'`), resulting in a fatal `Uncaught SyntaxError: Invalid or unexpected token` during the browser's initial `<script>` tag parsing inside `srcdoc`. Because this happened during script parsing before execution, `waitForDependencies`, `window.onerror`, and `#error-boundary` never ran, rendering a completely blank screen.
  - *Rule*: Never place unescaped `\n` inside quoted string literals within template literal HTML/JS generators. Always use `\\n` or plain strings without newlines. Pre-load React, ReactDOM, and Babel in `index.html` so `srcdoc` iframes can immediately access `window.parent.React` / `window.parent.Babel` on tick 0, eliminating cross-origin script blocks, CDN failures, and 3MB parse delays.
- **2026-09-23 (GitHub HTTPS 100MB Packfile Timeout & HTTP 408 / Curl 22 Error)**:
  - *Mistake*: Attempting to commit bundled binary wallpaper directories (`TAVERN/seed/backgrounds/*.png` at 80MB) along with source code caused the total Git commit packfile to hit ~100MB, triggering `error: RPC failed; HTTP 408 curl 22 The requested URL returned error: 408` and connection termination on GitHub.
  - *Rule*: Never commit heavy binary wallpaper directories or media caches directly to GitHub over HTTPS. Keep repositories lean: commit only source code, config, vector icons, and essential fonts (~7MB total). Heavy visual novel backgrounds and user data (`data/`, `node_modules/`, `avatars/`) must stay excluded via `.gitignore`.
- **2026-09-23 (Git Untracking Pitfall for Already Tracked Local Docs)**:
  - *Mistake*: Expecting that simply adding previously-committed files (like `AGENTS.md` and `DESIGN-SYS.md`) to `.gitignore` would stop Git from pushing them.
  - *Rule*: `.gitignore` only applies to *untracked* files. For any file already in Git index that needs to be kept on disk for local dev use, you MUST run `git rm --cached <files>` so Git untracks them while preserving the files locally.
- **2026-09-23 (Entrypoint Proliferation & Canonical Launcher Invariant)**:
  - *Mistake*: Generating extra entrypoints (`start_eclipse.sh`, `nephis.bat`) when user asked to run from anywhere.
  - *Rule*: Eclipse has **strictly two canonical entrypoints**:
    1. `start.sh` (symlinked as `nephis` and `eclipse` for Linux/macOS/Termux) — uses `realpath` resolution and `$PREFIX/bin` linking so it runs anywhere.
    2. `start.bat` for Windows — uses `%~dp0` to resolve the root from any current working directory.
    Never create auxiliary `.bat` or `.sh` wrapper scripts in the repository root.
- **2026-09-23 (Co-Startup Lifecycle Management for Dual Services)**:
  - *Mistake*: Relying on standalone manual launches for Tavern Studio while Eclipse was running.
  - *Rule*: `start.sh` and `start.bat` handle dual co-startup automatically:
    - Checks for `TAV-TEST` first (if user is developing locally) or `TAVERN`.
    - Spawns Tavern in background on ports 5173/3001 with auto `npm install` check.
    - Sets process traps (`trap cleanup INT TERM EXIT`) on Linux/macOS/Termux so child node processes are cleanly killed when Eclipse exits.
- **2026-09-23 (Cross-Device & LAN Host Binding Blocker in Integrated Web Services)**:
  - *Mistake*: When accessing Eclipse from other devices on the LAN (e.g. phone or laptop on `http://192.168.1.x:9000`), clicking "Tavern" failed with connection refused because:
    1. Vite defaulted to loopback `127.0.0.1` without `server.host: '0.0.0.0'`.
    2. Express backend in `server/index.ts` listened on `127.0.0.1` without `API_HOST=0.0.0.0`.
    3. `originCheck.ts` rejected non-loopback origins with `403 Forbidden origin`.
    4. Frontend and backend hardcoded `http://localhost:5173` instead of dynamically resolving against the caller's active device hostname (`window.location.hostname`).
  - *Rule*: Whenever integrating secondary web servers (Vite/Node/FastAPI), ALWAYS:
    1. Configure `host: '0.0.0.0'` in `vite.config.ts`.
    2. Set default host to `0.0.0.0` in the backend server (`server/index.ts`).
    3. Whitelist private IPv4 subnets (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`, `.local`) in origin guards.
    4. Dynamically rewrite launcher and API URLs using the caller request's host header or `window.location.hostname`.
- **2026-09-24 (Accidental Dependency Re-introduction & Pydantic-Core Rust Build Trap on Phones)**:
  - *Mistake*: While adding DeepSeek and Qwen features, `fastapi` and `pydantic` were inadvertently added back into `requirements.txt`, and `start.sh` had `import fastapi` in its startup check. On Android (Termux), `pip install` pulled `pydantic-core`, which requires compiling Rust with `cargo`, hanging for hours on phones.
  - *Rule*: Eclipse's runtime is 100% pure Python and relies on `StarletteGateway` in `eclipse/server.py`. Neither `pydantic` nor `fastapi` is used. Never add `pydantic`, `fastapi`, or any package requiring a Rust toolchain to `requirements.txt`. Startup checks in `start.sh` must strictly check pure packages (`starlette, uvicorn, httpx`) so phone installation takes 3–5 seconds flat.
- **2026-09-24 (Termux Kernel vs Userspace Mismatch & `[Errno 8] Exec format error`)**:
  - *Mistake*: When downloading native ngrok binaries on Android Termux, `uname -m` reported `aarch64` (64-bit kernel), but the Termux environment on the device was a 32-bit userland (`arm` / `armhf`). Attempting to spawn the 64-bit ELF binary caused `Failed to spawn ngrok process: [Errno 8] Exec format error: '/data/data/com.termux/files/usr/bin/ngrok'`. Additionally, `get_ngrok_bin_path` assumed any file with executable bit was runnable without performing an actual execution dry-run.
  - *Rule*: Never rely solely on `uname -m` on Android/Termux.
    1. Query the actual userspace architecture via `dpkg --print-architecture` and check `sys.maxsize > 2**32`.
    2. Every candidate binary must pass `is_binary_runnable` (`ngrok version`) before being accepted or spawned.
    3. Implement automatic architecture fallback: if `arm64` triggers `Exec format error`, automatically fetch and verify the 32-bit `arm` binary.
    4. On startup, automatically detect and purge any corrupted or architecture-mismatched binaries from `$PREFIX/bin/` so the system self-heals.
- **2026-09-24 (Windows Batch Parenthesis Trap in `if (...)` Blocks)**:
  - *Mistake*: In `run_tavern.bat` and `start.bat`, `echo Please install Node.js (v22+)` and `echo (first-time setup)` were placed inside CMD `if (...)` blocks. In `cmd.exe`, raw parentheses inside an `if` block prematurely terminate the block parser, crashing with `... was unexpected at this time`.
  - *Rule*: Never use raw unescaped parentheses inside `if (...)` blocks in Windows `.bat` files. Use square brackets `[v22+]` or escape them `^)`. Never use unescaped ampersands `&` in echo statements (use `^&` so CMD doesn't treat it as a command separator).
- **2026-09-24 (Missing Standard Library Imports in Dynamic Archive Handlers)**:
  - *Mistake*: Calling `tarfile.open()` inside `eclipse/tunnel.py::install_ngrok()` without `import tarfile` at the module level caused `Could not auto-install ngrok: Failed to auto-install ngrok for generic-arm64: name 'tarfile' is not defined` when extracting `.tgz` binaries on Android/Linux.
  - *Rule*: Always declare standard library extraction utilities (`tarfile`, `zipfile`, `shutil`) at module level and run an AST check across new functions to eliminate runtime `NameError` exceptions.
- **2026-09-24 (Termux Current Directory vs. Global PATH Command Execution)**:
  - *Mistake*: When in `~/Eclipse`, typing `nephis` or `eclipse` without `./` before first boot failed with `No command found` because the current working directory `.` is not in `$PATH`.
  - *Rule*: On initial setup, users run `./start.sh` or `bash install.sh`. `start.sh` must immediately symlink both `nephis`, `eclipse`, and `c2a` into `$PREFIX/bin` (and `~/.local/bin` on Linux/macOS) and add aliases to `~/.bashrc` so that all subsequent invocations without `./` work globally from any directory.
- **2026-09-24 (ChatGPT Web Image Generation Block in Temporary Chats & Estuary CDN 403)**:
  - *Mistake*: Selecting image generation models like `gpt-image-2.5-flare` or `gpt-image-2.5-sunburst` returned a refusal: *"I can help create an apple image, but image generation isn't available in this temporary chat. Please switch to a regular ChatGPT chat and ask again..."*. This occurred because:
    1. `history_and_training_disabled: True` was unconditionally sent to the upstream OpenAI backend API, placing the session in "Temporary Chat" (incognito) mode where DALL-E / picture_v2 tools are strictly disabled by OpenAI.
    2. Model slugs (`gpt-image-2.5-flare`) were not aliased to `"auto"`, preventing proper tool binding.
    3. OpenAI estuary CDN download URLs (`sediment://` or `backend-api/estuary/content`) return HTTP 403 when loaded directly in browser `<img>` tags without session cookies.
  - *Rule*: For all image generation models:
    1. Dynamically set `history_and_training_disabled: not is_image_model` and include `"system_hints": ["picture_v2"]`.
    2. Proxy and cache all generated image assets: intercept SSE `sediment://` and `file-service://` asset pointers, download the full PNG binary using the TLS-impersonated session, persist them to `eclipse/static/generated/`, and stream standard base64 data URIs (`![Generated Image](data:image/png;base64,...)`) so the frontend renders the interactive viewport immediately.
    3. Clean up the user's ChatGPT sidebar automatically post-generation by issuing `PATCH /backend-api/conversation/{conv_id}` with `{"is_visible": False}`.
- **2026-09-24 (Generated Image Viewport UI & Clean Floating Action Overlays)**:
  - *Mistake*: Encasing AI-generated images inside bloated cards with extra border outlines and footer caption bars ("Neural Synthesis", redundant prompt text). In modern conversational UI (e.g. ChatGPT), the generated image must stand clean and borderless with its natural aspect ratio and rounded corners, avoiding visual clutter.
  - *Rule*: Generated images must be presented cleanly:
    1. Render the image directly with modern rounded corners (`border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 4px 24px rgba(0, 0, 0, 0.28);`).
    2. Eliminate redundant caption / prompt footers.
    3. Floating action overlay (top-right) provides dedicated, high-contrast frosted glass buttons for **Copy** and **Download** only (omitting distracting edit/share menus), with tooltips (`data-tooltip`) and immediate visual feedback (e.g. checkmark icon and "Copied!" state).
- **2026-09-25 (High-Definition WebGL Fluid Simulation & Theme Adaptive Palette)**:
  - *Mistake*: Checking `document.body.getAttribute('data-theme')` instead of `document.documentElement.getAttribute('data-theme')`, causing light mode to falsely register as dark mode and rendering black patches instead of clean white; and hardcoding pitch black instead of the UI's theme primary dark `#141414`.
  - *Rule*: For image generation loading:
    1. Check theme on `document.documentElement` (`document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme')`).
    2. In Light Mode: Replace all dark/black elements with pure white (`#ffffff`) and soft whitish (`#fcfbfa`). Terracotta `#d97757` streams fold and merge with whitish fluid. Zero black or dark patches!
    3. In Dark Mode: Background is the UI's dark background `#141414` (from tokens `--bg-primary`) with luminous `#d97757` terracotta streams and warm peach highlights.
    4. Render with GPU-accelerated WebGL using **analytical harmonic vortex potential flow** ($\sin, \cos, \text{atan}, \text{length}$). These are $C^\infty$ mathematically continuous, guaranteed 100% artifact-free, and impossible to produce noise or TV grain.
    5. Render at native Retina display resolution (`canvas.width = clientWidth * dpr`). Fluid motion must be strictly **autonomous** (no pointer listeners).
    6. Clean ChatGPT UI framing: "Creating image" header in top-left, aspect ratio container, and frosted glass percentage progress pill ("19%") in bottom-right corner.
    7. When inference completes, `finish()` cleanly deallocates WebGL shaders and the final image pop-fades in.
- **2026-09-25 (Dark Mode Theme Accents & High-Contrast Icon Elements)**:
  - *Mistake*: Setting user message bubbles to generic dark gray (`#242424`) and dimming response buttons and top header settings icons to muddy low-contrast gray (`#78716c`), causing poor visual hierarchy and readability on dark backdrops.
  - *Rule*: In dark mode:
    1. User message bubble background is brand terracotta (`#d97757`) with crisp white text (`#ffffff`), 16px corners, and subtle warm drop shadow.
    2. Response action buttons (copy, retry, edit, tts, feedback) in `.response-actions` and user message hover bar `.user-msg-actions` are crisp whitish (`rgba(255, 255, 255, 0.85)` / `#ffffff` on hover).
    3. Top header settings buttons (`.claude-icon-btn`, `.claude-avatar-btn`) are crisp whitish (`rgba(255, 255, 255, 0.88)` / `#ffffff` on hover).
    4. Date timestamps (`.response-date`, `.user-msg-date`) remain subtly muted (`var(--text-muted)`) so they do not compete with interactive controls.
- **2026-09-25 (Google Omni Multimodal & Veo Cinematic Video Model Integration)**:
  - *Context*: Google DeepMind's frontier generative media family expands beyond text/code to include **Google Omni** (`gemini-omni-flash`, `gemini-omni-1.1-flash`, `gemini-omni-pro`, `google-omni`) for any-to-any multimodal conversation and conversational video editing, and **Veo** (`veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-lite`, `veo-3.0`, `veo-2.0-generate-001`, `veo-2`) for cinematic video generation with native synchronized audio.
  - *Rule*:
    1. Register all Omni and Veo models with accurate capabilities (`['video', 'audio', 'vision', 'chat']`) and context window specs in `MODELS_CATALOG` (`eclipse/providers.py`).
    2. Add routing prefixes (`veo`, `google-omni`, `omni`) in `resolve_model_provider()` and video modality detection in `_get_simulated_response_payload()` (`eclipse/server.py`).
    3. Register runtime engine mode and thinking configurations in `MODEL_CONFIGS` (`eclipse/engines/gemini.py`).
    4. Accurately reflect video quotas and multimodal features in `get_all_limits()` (`eclipse/providers.py`).
- **2026-09-25 (Strict Real-Live Testing Rule & Elimination of Fake Simulated Responses)**:
  - *Mistake*: Testing model endpoints and fixes using `--simulate` instead of authentic live upstream requests. The user explicitly forbids fake simulated responses.
  - *Rule*: NEVER test with `--simulate`. Always execute real live test queries against the running server/engine using `./singular chat "<prompt>" -m <model>` to verify authentic network calls, cookie authentication, response tokens, and media downloads.
- **2026-09-25 (Google Gemini Batchexecute SNlM0e XSRF Token & ALR Image Pipeline)**:
  - *Mistake*: Gemini `StreamGenerate` calls failing with HTTP 400 (`[["er",null,null,null,null,400,null,null,null,3,[{"48448350":["xsrf","..."]}]]]`) and image generation failing with guest mode refusal ("It's possible you're signed out or image creation isn't available").
  - *Rule*:
    1. Gemini's `StreamGenerate` endpoint strictly requires the `at` parameter (`SNlM0e` XSRF token) and modern `bl` build label.
    2. Dynamically extract `SNlM0e` and `bl` from `https://gemini.google.com/app` using active session cookies (`__Secure-1PSID`), caching context for 10 minutes.
    3. If rotation causes HTTP 400, automatically parse `["xsrf", "<new_token>"]` from the response error body, refresh cache, and auto-retry.
    4. Google generated image links (`https://lh3.googleusercontent.com/gg-dl/...`) return 403 unless resolved through authenticated App Layer Redirection (`=d-I?alr=yes`) hops. Follow ALR hops with session cookies until binary is received, save to `eclipse/static/generated/`, and stream as base64 data URI `![Generated Image](data:image/png;base64,...)`.
- **2026-09-25 (Google Gemini `__Secure-1PSIDTS` Cookie Requirement & Multi-Account Fallback)**:
  - *Mistake*: When copying Gemini cookies from browser DevTools, users frequently omit `__Secure-1PSIDTS`. In Google auth, `__Secure-1PSID` is strictly bound to `__Secure-1PSIDTS`. Without `__Secure-1PSIDTS` (or when expired), Google treats the session as unauthenticated guest mode and refuses image generation with: *"Are you signed in? I can search for images, but can't seem to create any for you right now..."* Furthermore, Eclipse hardcoded `accounts[0]` in ascending order, ignoring newer accounts and lacking multi-account authenticated session discovery.
  - *Rule*:
    1. Sort database credentials `ORDER BY id DESC` so recently added accounts take immediate priority over stale credentials.
    2. In `eclipse/engines/gemini.py`, iterate through all candidate accounts in priority order and test `_get_gemini_session_context` to find an account with a verified `SNlM0e` authenticated session.
    3. Validate `__Secure-1PSIDTS`: flag in `parse_credential`, surface warnings in `save_stacked_cookies`, and display real-time warning toasts in the UI if `__Secure-1PSIDTS` is missing.
- **2026-09-25 (Google Gemini `SAPISIDHASH` Authentication & Full Cookie Bundle Support)**:
  - *Mistake*: Assuming `__Secure-1PSID` and `__Secure-1PSIDTS` alone are sufficient for Google's authenticated image generation endpoints. Google Web endpoints require the `Authorization: SAPISIDHASH <ts>_<sha1>` header (derived from the `SAPISID` cookie) and validate the complete cookie bundle (`SID`, `__Secure-1PSID`, `__Secure-1PSIDTS`, `SAPISID`, etc.). Prematurely returning an abort notice blocked live execution and auto-healing.
  - *Rule*:
    1. Do not prematurely abort image requests before sending them to Gemini; allow requests to hit the backend so auto-healing and token recovery can execute.
    2. Extract `SAPISID`, `__Secure-1PAPISID`, or `__Secure-3PAPISID` from the candidate cookie if present, and dynamically compute and attach the `Authorization: SAPISIDHASH <timestamp>_<sha1>` header for `https://gemini.google.com`.
    3. Update the Control Center guide and in-stream help notice to recommend copying the full `Cookie:` header from the browser's Network tab (`F12` -> Network -> click any Gemini request -> Request Headers -> Cookie).
    4. Only replace Google's signed-out / location refusal message if no generated images were emitted (`not emitted_images`), preventing false error states when images are successfully returned.
- **2026-09-26 (Unclosed Modal Parent Container & Global Delegation for Icon Buttons)**:
  - *Mistake*: Clicking the top-right header gear icon (`#btn-open-settings`) failed to show the Claude Settings Modal ("when i click on gear icon, nothing comes up"). A missing `</div>` on the preceding `#playground-lightbox` container caused `#claude-settings-modal` to be parsed inside `.lightbox-modal`, which had `opacity: 0; pointer-events: none;`, making the opened modal totally invisible ($1 \times 0 = 0$). Furthermore, `initUserProfile` was not hoisted, and clicking on SVG paths inside `#btn-open-settings` lacked global delegated event capturing.
  - *Rule*:
    1. **Strict HTML Tag Balancing**: Run programmatic tag validation whenever adding or editing modal backdrops. Ensure all fixed modal windows are top-level siblings placed outside deeply nested UI layouts.
    2. **Proper Function Hoisting**: Always declare functions with standard `function <name>()` syntax (`function initUserProfile() { return initClaudeSettings(); }`) if they are referenced anywhere during page initialization.
    3. **Explicit Lifecycle Calling**: Explicitly call modal and feature initializers (e.g. `initClaudeSettings()`) directly in `DOMContentLoaded`.
    4. **Robust Event Delegation**: Attach global delegation on `document` with `e.target.closest('#btn-open-settings, .claude-settings-gear-btn')` so clicks on child SVG icons and paths open modals reliably.
- **2026-09-26 (Custom Model Selector Lifecycle Re-rendering & Segmented Theme Capsule Geometry)**:
  - *Mistake*: The chat playground model switcher popover displayed an empty box below the search input because `renderCustomSelectOptions()` was only called once at startup without a re-render trigger on click, leaving it blank if `/api/models` completed asynchronously. Additionally, the popover stuck right to the button with an awkward offset, and the theme segmented control in Settings lacked explicit width, collapsing the indicator into a squished vertical oval.
  - *Rule*:
    1. **Dynamic Dropdown Lifecycle**: Always trigger `renderCustomSelectOptions()` whenever the dropdown trigger is clicked, provide fallback loading states if catalogs are in flight, and auto-fetch if `state.models` is empty.
    2. **Refined Popover Spacing & Ergonomics**: Offset popovers with 12px breathing room (`bottom: calc(100% + 12px)`), clean 14px border-radius, and smooth spring transitions so popovers don't cling awkwardly to input buttons.
    3. **Item Feedback & Selection State**: Add visual checkmark icons (`✓`) and provider tags for selected items, and update labels immediately.
    4. **Segmented Control Minimum Sizing**: Always declare fixed minimum container geometry (`width: 132px; height: 38px;`) on segmented controls so capsule indicators glide horizontally with correct aspect ratio.
- **2026-09-30 (JavaScript Syntax Validation & Modal Initialization Execution Failure)**:
  - *Mistake*: When refactoring Settings modal select dropdowns to custom components in `eclipse/static/app.js`, an unclosed block in the font dropdown event listener left a dangling syntax error (`SyntaxError: missing ) after argument list`). This parse-time error aborted script evaluation, preventing `initClaudeSettings()` and global click listeners from attaching, causing the header gear icon (`#btn-open-settings`) to appear completely unresponsive when clicked.
  - *Rule*:
    1. **Mandatory AST / Syntax Check**: Always run `node --check eclipse/static/app.js` immediately after modifying frontend script files before concluding work or testing in the browser.
    2. **Defensive Initializer Scoping**: Keep core modal open/close triggers resilient to individual component failures and always verify script parse status if UI buttons fail to respond.
- **2026-10-08 (Followed Creators Database Architecture, Native Janitor Profile Hierarchy & Cloud Vault Hygiene)**:
  - *Mistake*: The "Followed Creators" page (`connect-panel.js`) rendered raw UUID strings (e.g. `@22d035a7-fbd9-409a-b035-fe66a6b11c3f`), zero followers, and placeholder avatars. Clicking a creator loaded a blank demo profile with 0 followers and 0 characters. This happened because `eclipse/connect.py` lacked SQLite creator profile caching and only queried `cards-backend.domcord.org`, which frequently timed out (>10s) or 404'd on user profile IDs. On timeout, the frontend fell back to creating dummy placeholder records (`{id: rawId, username: rawId, displayName: rawId, followers: 0}`), which then synchronized up to Supabase, polluting the database with corrupt records.
  - *Rule*:
    1. **Dedicated SQLite Creator Cache**: Add `connect_creators` table schema to SQLite database with `id`, `username`, `name`, `avatar`, `bio`, `followers`, `total_bots`, `badges`, `style`, `updated_at`. Automatically seed/backfill from author metadata in the 2,387 cards in `connect_cards`.
    2. **Multi-Tier Fetch Hierarchy**: Upgraded `fetch_creator_profile(creator_id)` in `eclipse/connect.py`: Tier 1 = Local SQLite (0ms), Tier 2 = Fast native Janitor endpoint `https://janitorai.com/mb/profiles/{creator_id}` (~300ms) with authentic `followers_count`, `user_name`, `avatar`, `badges`, and `about_me`, Tier 3 = Domcord backend (`cards-backend.domcord.org`, 6s timeout) for authored bots list, Tier 4 = Local authored cards in `connect_cards`.
    3. **Single Batch Endpoint**: Added `GET /api/connect/creators/batch?ids=...` to resolve all followed creators in a single HTTP request instead of issuing N parallel network requests.
    4. **Cloud Sync Cleansing**: In `server.py` and `supabase-sync.js`, reject and purge corrupted placeholder objects where `username == id` and `avatar` is blank, ensuring the Supabase vault retains only authentic creator identities.
- **2026-10-08 (Zero-Flicker Stale-While-Revalidate (SWR) Rendering & Elimination of Periodic Screen Refresh)**:
  - *Mistake*: The creators page and character cards repeatedly flashed and wiped the DOM every 5 seconds, resetting scroll position and breaking readability. This was caused by `supabase-sync.js` calling `applyCloudState()` on focus, visibility change, and interval syncs, which unconditionally called `renderCreatorsView(container)` whenever `currentView === 'creators'`, and `renderCreatorsView()` was wiping `container.innerHTML = ...` with skeleton placeholders on every execution.
  - *Rule*:
    1. **Dirty-Checking in Cloud Sync**: Only trigger view re-renders if the incoming cloud data actually mutated (`hasFollowingChanged`, `hasCreatorProfilesChanged`, `hasLibraryChanged`).
    2. **Instant 0ms SWR Rendering**: `renderCreatorsView` and `renderCreatorDetailView` must check `creatorCache` and `botCache` on first paint and render known cards immediately at 0ms latency without displaying empty skeleton placeholders.
    3. **In-Place DOM Mutation**: When background batch fetches return fresh data, update `#creators-page-grid` in-place, and only mutate the DOM if `grid.innerHTML !== newHTML` to completely eliminate UI flicker.
- **2026-10-08 (Creator Avatar CDN Namespace Isolation & Multi-Tier Client Auto-Heal)**:
  - *Mistake*: Followed creator avatars (such as ZeroNine1 `1a91edf6-3464-41ca-b6e6-5073b406e971` with avatar hash `crH9B1J57oSzCwUhnvsV_.webp`) failed with 404 and rendered fallback placeholder icons. `eclipse/connect.py` had mapped all bare hash filenames to `https://ella.janitorai.com/bot-avatars/{hash}`. However, Janitor's CDN strictly isolates user/creator avatars (`/avatars/`, `/user-avatars/`, or `/profile-avatar-approved/`) from bot avatars (`/bot-avatars/` or `/media-approved/`). Requesting a creator's avatar under `/bot-avatars/` returns HTTP 404. Furthermore, the frontend `onerror` fallback only handled strings containing `/user-avatars/` or `/avatars/`, immediately jumping to `DEFAULT_AVATAR` when seeing `/bot-avatars/`.
  - *Rule*:
    1. **Dedicated Creator Avatar Resolver**: Implement `resolve_creator_avatar_url(raw_url)` in `eclipse/connect.py`: bare filenames resolve directly to `https://ella.janitorai.com/avatars/{hash}`, legacy `/bot-avatars/` paths are dynamically rewritten to `/avatars/`, and `data:image/` URIs are preserved untouched.
    2. **Database Auto-Migration**: On startup, run SQL migrations on `connect_creators` and `connect_cards` replacing `'/bot-avatars/'` with `'/avatars/'` across all existing creator rows.
    3. **Multi-Tier Client Auto-Heal**: In `eclipse/static/connect-panel.js`, implement `SConnect.handleAvatarError(img)` which sequentially tests candidate CDN paths (`/bot-avatars/` -> `/avatars/` -> `/user-avatars/` -> `/profile-avatar-approved/`) before falling back to `DEFAULT_AVATAR`.
- **2026-10-08 (Non-Blocking Tiered Backend Fetching & Latency Bottleneck Elimination)**:
  - *Mistake*: The Followed Creators view took 9+ seconds on initial load despite native Janitor returning authentic profile data in ~300ms. Investigation revealed `fetch_creator_profile()` was synchronously awaiting Tier 3 (`cards-backend.domcord.org`) for 8.9s on every call even when native Janitor had already succeeded with full follower count, bio, name, and avatar.
  - *Rule*:
    1. **Conditional Tier 3 Invocation**: Only query Tier 3 (Domcord) if essential profile data is missing or if no authored bots exist, skipping it entirely when native Janitor succeeds.
    2. **Strict Timeout Capping**: Cap external mirror timeouts at 1.5s so lagging community backends never block user navigation or batch profile resolution.
    3. **Cache-First 0ms Access**: Always query local SQLite `connect_creators` first so repeated visits load in 0ms without network overhead.
- **2026-10-08 (Asymmetric Cloud Sync Downgrades, Synthetic Dummy Profile Fabrication & CSS Bio Leaks)**:
  - *Mistake*: Followed creator cards (`ZeroNine1`, `fishywashy`) repeatedly flickered their bios and follower counts vanished into `• Creator` before reappearing, while `InsomniacZer0` remained completely stable. This occurred because `supabase-sync.js` and `server.py` had a legacy loop iterating over `savedBotsData` that fabricated synthetic dummy creator profiles with `bio: "Creator of ${bot.name}"` and `followers: 0` for any creator who authored a saved bot card in the user's library (`Still Yours, My Love.. | Nessa` by ZeroNine1, `Chudette's First Job | Jess` by fishywashy). InsomniacZer0 had no saved bots in the library, so no dummy profile was ever generated for him. These 0-follower profiles synchronized to Supabase, and on every sync interval or tab focus, `applyCloudState()` clobbered the authentic cached profiles because `existing.followers !== cp.followers` without checking for quality/fidelity downgrades. Additionally, `stripHTML()` stripped `<style>` tags but left the enclosed raw CSS rules (`body::after...`) leaking into the bio preview text.
  - *Rule*:
    1. **Strict Prohibition on Synthetic Profile Fabrication**: Never manufacture dummy creator profiles with 0 followers or synthetic `"Creator of <bot>"` bios into cloud sync payloads or persistent storage. Cloud sync must strictly synchronize authentic creator identities from `connect_creators` / `creatorCache`.
    2. **Non-Destructive In-Memory Quality Guards (`cacheCreator` & `applyCloudState`)**: A low-fidelity or partial record must NEVER downgrade an authentic cached record. If an incoming record has `followers === 0` (or missing/synthetic bio) while the cached record has authentic `followers > 0` (or real bio), preserve the authentic cached fields.
    3. **SQL `ON CONFLICT` Quality Shield in `eclipse/db.py`**: In `save_creator_profile`, ensure `followers` and `bio` updates protect authentic existing data from being overwritten by synthetic prefixes (`Creator of %` / `JanitorAI author of %`) or 0-follower records. Never call `save_creator_profile` from read-only fallback queries.
    4. **Embedded Style & Script Stripping in `stripHTML()`**: Janitor creators frequently use custom CSS and HTML in profile bios. Always strip `<style[^>]*>[\s\S]*?<\/style>` and `<script[^>]*>[\s\S]*?<\/script>` before tag stripping to prevent raw CSS code from leaking into card bio previews.
- **2026-10-08 (Home Recent Chats Desktop Column Layout & Top-3 Ceiling Invariant)**:
  - *Mistake*: The Discover/Home "Recent Chats" section displayed 4 cards (`.slice(0, 4)`). On desktop viewports where `.janitor-recent-chats-scroll` uses a 3-column auto-fill responsive grid (`minmax(360px, 1fr)`), 3 cards filled the top row, leaving the 4th card awkwardly dangling alone on the second row.
  - *Rule*: When presenting preview session carousels on the main dashboard, enforce a strict top-3 ceiling (`.slice(0, 3)`) to maintain a clean, single-row layout that aligns with the 3-column responsive grid. Users who wish to browse additional historical sessions can click "View All" to access the full `/my-chats` view.
- **2026-10-08 (Sticky Navigation Header Clipping & `scrollIntoView` Target Anchor Invariant)**:
  - *Mistake*: When navigating between tabs/sections in S-Connect (Discover, Following Feed, Personas), the view consistently loaded scrolled down ~64px, clipping the top navigation bar, search inputs, page titles, and hero filters under the sticky navbar. This occurred because `resetScrollToTop()` had a fallback `document.getElementById('connect-main-view').scrollIntoView({ behavior: 'instant', block: 'start' })`. `#connect-main-view` sits beneath the 64px sticky header `<header class="cards-top-nav-bar">`. Aligning `#connect-main-view` to `block: 'start'` forced `.panel-viewport` to scroll down by 64px, pushing the top content behind the sticky navbar.
  - *Rule*:
    1. **Never Scroll Inner Content Under Sticky Navbars**: Never call `scrollIntoView` on inner content containers (`#connect-main-view`, `.bot-detail-page`, `.back-nav-btn`) that sit below a sticky header.
    2. **Target Absolute Top Anchors ($Y=0$)**: If invoking `scrollIntoView`, target strictly `#cards-top-nav-bar` or `#pane-connect` (the true top element at $Y=0$).
    3. **Synchronous & RAF Scroll Reset**: Reset `scrollTop = 0` across all scroll ancestors (`.panel-viewport`, `#pane-connect`, `document.documentElement`, `window`) both synchronously and inside `requestAnimationFrame` to guarantee zero visual clipping or layout displacement.
- **2026-10-09 (Recent Chats Netflix Video Thumbnail & "Continue Watching" UI Pattern)**:
  - *Evolution*: Replaced bulky, boxy text-heavy Recent Chat cards with widescreen 16:9 Netflix video thumbnails, matching the modern video streaming continue-watching aesthetic.
  - *Rule*:
    1. **16:9 Aspect Ratio & Full-Cover Artwork**: Cards use `aspect-ratio: 16 / 9; overflow: hidden;` with character avatar filling the card (`object-fit: cover; object-position: center 25%`) and subtle zoom transition on hover (`scale(1.06)`).
    2. **Frosted Glass Center Play Button**: Absolute-centered circular glassmorphic play button (`backdrop-filter: blur(8px)`, white play triangle) that scales on hover with Netflix red accent illumination (`#E50914`).
    3. **Cinematic Bottom Vignette & Metadata**: Gradient overlay (`linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.92) 100%)`) holding single-line lock icon + bot title and relative timestamp + message count.
    4. **Netflix "Continue Watching" Red Progress Bar**: Persistent 3.5px red bar (`#E50914`) across the bottom edge with randomized/varied watch progress (20% to 92%) deterministically hashed per chat session.
    5. **Responsive Row Dynamics**: Responsive grid uses `data-count` (1 to 4) mapping seamlessly to up to 4 columns on desktop, 2 columns on tablet, and horizontal swipe on mobile.
    6. **Clean Home Discover Hierarchy**: Category filter chips bar removed in favor of clean omni-search leading straight into Recent Chats and "Trending this week".
- **2026-10-09 (Following Feed Native Janitor Batch Architecture & Concurrency Scalability)**:
  - *Mistake*: The Following Feed (`renderFollowingView` in `connect-panel.js`) was erratic, slow, and dropped creators: sometimes showing only 1 creator, sometimes 0 (blank screen), sometimes 2/5 or 4/5 of followed creators, taking 7+ seconds of blank skeleton cards. Furthermore, `.slice(0, 24)` hardcoded cap permanently discarded any followed creator beyond 24, breaking when users follow 70 or 100+ creators. This happened because the frontend issued $N$ parallel HTTP requests (`Promise.all(followingList.slice(0, 24).map(...))`) to `/api/connect/creators/{id}/bots`, which hit the slow, rate-limited Domcord community mirror (`cards-backend.domcord.org`) with a 7.0-second timeout. When multiple concurrent requests hit Domcord, they timed out, fell back to an empty SQLite table, and returned 0 bots.
  - *Rule*:
    1. **Native Janitor Character Batching**: Janitor AI's native `/mb/characters` endpoint supports querying characters by creator using `mode=all&page={page}&sort=latest&user_id[]={id1}&user_id[]={id2}...` with validation cap `@ArrayMaxSize(64)`. Querying up to 50 creators in a single request completes in ~500–800ms.
    2. **Chunked Concurrency for 70 to 100+ Creators**: In `fetch_following_feed()` (`eclipse/connect.py`), partition followed creator UUIDs into chunks of 50 (`CHUNK_SIZE = 50`) and fetch all chunks in parallel with `asyncio.gather()`. 100 creators require only 2 parallel requests instead of 100 browser requests, completing in <1 second.
    3. **Fair Round-Robin Interleaving**: Group returned characters by creator and round-robin interleave across all followed creators before slicing to limit. This guarantees high-volume authors do not crowd out creators with fewer releases, ensuring every followed creator is fairly represented in the feed.
    4. **Multi-Tier Fallback & Database Indexing**: Auto-persist all fetched bots to `connect_cards`. Index `connect_cards(creator_id)` and `connect_cards(updated_at DESC)`. If offline or on network failure, fall back instantly to `get_connect_cards_by_creators(clean_ids)`.
- **2026-10-09 (Creator Multi-Page Catalog Scraping & Complete Character Pagination Architecture)**:
  - *Mistake*: Creators on Janitor AI with >34 bots (e.g. 60, 112, 121+ cards) were truncated to page 1 or an arbitrary SQLite `LIMIT 60`. `fetch_creator_profile` only queried `/mb/profiles/{id}` (which contains user bio and avatar, but 0 characters) and fell back to SQLite with `LIMIT 60` or Domcord (which timed out). Meanwhile, `fetch_creator_bots` returned `len(norm_bots)` instead of the authentic `total` count and never scraped pages $2..N$. As a result, creator profiles showed at most 34 bots, hiding the rest of their creations from users.
  - *Rule*:
    1. **Strict 34 Bots/Page Pagination**: Janitor AI strictly limits character responses to 34 items per page (`size: 34`). Overriding `size` or `limit` parameters is ignored by Janitor's backend.
    2. **Deterministic Total Discovery**: Page 1 (`https://janitorai.com/mb/characters?mode=all&page=1&sort=latest&user_id[]={id}`) returns `{ "total": 121, "size": 34, ... }`. Total pages is computed as `math.ceil(total / 34)`.
    3. **High-Speed Parallel Multi-Page Scraping (`scrape_all_creator_characters`)**: If `total > 34`, fire requests for pages $2..N$ concurrently using `asyncio.gather()`. Scraping 120+ cards across 4 pages takes only ~1.1 seconds.
    4. **Vault Persistence & Cache Invariant**: Upsert all scraped cards into SQLite `connect_cards` preserving unmasked stats. Persist `all_pages_scraped: True` in `connect_creators.raw_payload_json` so subsequent loads serve the entire catalog instantly at 0ms.
    5. **Removal of Hardcoded Caps**: Never hardcode `LIMIT 60` in creator queries; load all authored cards for complete representation.
    6. **UI Dynamic Count Reflection**: In `drawCreatorDetailPage`, display the exact count `${bots.length < totalCards ? `${bots.length} of ${totalCards}` : bots.length} publicly available cards` and render the full responsive grid.
- **2026-10-09 (Xiaomi MiMo Cookie Quotes Sanitization, Key Aliasing & ModelConfig Contract)**:
  - *Mistake*: When copying cookies from browser DevTools, values often contain surrounding quotes (e.g. `xiaomichatbot_serviceToken="lBp+..."` or `xiaomichatbot_ph="ol0U..."`). Passing literal quotes in cookie headers caused Xiaomi's `/open-apis/bot/chat` backend to reject requests with `HTTP 401: {"code":401,"loginUrl":"..."}`. Additionally, the cookie in DevTools can be named `xiaomichatbot_serviceToken` or `serviceToken`, and assuming the model parameter was `modelCode` resulted in `event:error data:{"type":"text","content":"模型名称错误"}`.
  - *Rule*:
    1. **Strict Quote Stripping**: Always sanitize and strip surrounding quotes (`.strip('"\'')`) from cookie/token values in both `eclipse/db.py` (`parse_credential`) and `eclipse/engines/mimo.py` (`_parse_mimo_credentials`).
    2. **Token Key Aliasing**: Support both `serviceToken` and `xiaomichatbot_serviceToken` using regex `(?:xiaomichatbot_)?serviceToken=`, and send both keys in request cookies for seamless authentication.
    3. **ModelConfig Contract**: In Xiaomi AI Studio `/open-apis/bot/chat`, the model parameter inside `modelConfig` must strictly be `"model": <model_id>` (e.g. `"model": "mimo-v2.6-pro"`), NOT `"modelCode"`.
- **2026-10-09 (Clean Terminal Experience, Mobile Termux Responsive Layout & Access Log Muting)**:
  - *Mistake*: Uvicorn defaulted to `access_log=True`, causing a continuous stream of `INFO: 127.0.0.1:xxx - "GET /api/... HTTP/1.1" 200 OK` from background polls (`/api/tunnel/status`, `/api/services`, cloud sync) to flood stdout, pushing server status off the screen. Additionally, fixed 66-character box borders (`"=" * 66`) shattered and wrapped into broken lines on narrow Termux mobile screens, and lingering processes holding port 9000 caused port conflicts.
  - *Rule*:
    1. **Mute Uvicorn HTTP Access Logs**: Set `access_log=False` and `log_level="warning"` by default, disabling the `uvicorn.access` logger so background health checks and sync polls remain completely silent. Provide a `ECLIPSE_DEBUG=1` escape hatch for troubleshooting.
    2. **Frame-Free Responsive Terminal UI**: Never draw rigid fixed-width boxes (`"=" * 66` or `╭────╮`) that wrap and shatter on narrow 35–45 column Termux screens. Use clean left-aligned indentation (`  `), soft indicators (`● online`, `➜ Local:`, `• Vault:`), and short lines that wrap naturally on any display.
    3. **Multi-Tier Port Auto-Kill**: Before launching the server, inspect and reclaim port `5000` via `ss -lptn`, `fuser`, `lsof`, and process table matching to prevent `Address already in use` crashes.
- **2026-10-22 (CSS Preloader Stuck State & Solid Black Backdrop Excision)**:
  - *Mistake*: The frontend displayed a pitch black screen on initial load. Investigation revealed two culprits: (1) `#eclipse-preloader` had no safety watchdog, so if external font assets stalled or window load events misfired, the preloader remained at `display: flex; opacity: 1; z-index: 999999` forever; (2) `.claude-flow-wrapper` in `style.css` was hardcoded to `background: #000; z-index: 99999; position: fixed; inset: 0`, acting as an impenetrable black wall obstructing the entire interface.
  - *Rule*:
    1. **Preloader Auto-Dismiss Watchdog**: In `preloader.js`, always attach a 2.5s fallback `setTimeout` that forcefully applies `.hide` and calls `el.remove()` to ensure the preloader can never permanently lock the UI.
    2. **Zero Solid Full-Screen Wrapper Blocks**: Excised artificial `#000` fixed overlays. The workspace must render naturally onto `--bg-base` with glassmorphic docks.
- **2026-10-22 (GLM Guest Token 429 Rate-Limit Interception & Auto-Healer Validation)**:
  - *Mistake*: Under heavy continuous probing (e.g. 10-minute endurance runs with $\ge 1\text{k}$ token outputs), Zhipu GLM guest tokens eventually receive HTTP 429 ("Too Many Requests" or `1301`). Without transparent interception, JanitorAI users receive jarring red error toasts and truncated roleplay responses.
  - *Rule*:
    1. **Stream-Level 429 Interception**: Intercept rate-limit signals directly in the SSE generator (`glm.py`).
    2. **Seamless In-Memory Token Recycling**: When a 429 error occurs, immediately flush the expired guest token from cache, provision a fresh guest identity in memory, and replay the stream request transparently.
    3. **Endurance Validation**: Validate auto-healing under multi-turn load before shipping to guarantee 100% completion success rate.



