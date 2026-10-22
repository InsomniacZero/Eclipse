#!/usr/bin/env python3
"""
Eclipse Unified CLI
Cross-device command-line interface for managing Eclipse AI Gateway,
account vault (SQLite), feature limits, device simulation, and inferences.

Works identically on Linux, macOS, Android (Termux), and Windows.
Zero external legacy dependencies.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure eclipse directory is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import db
import providers
import security


# ==============================================================================
# Helper Formatting Utilities
# ==============================================================================

def print_header(title: str):
    width = 70
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_table(headers: List[str], rows: List[List[str]]):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = "  ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    sep_line = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_line)
    print(sep_line)
    for row in rows:
        print("  ".join(f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)))


# ==============================================================================
# CLI Commands
# ==============================================================================

def cmd_status(args):
    """Display gateway status, provider daemons, and account vault stats."""
    db.init_db()
    sim = providers.is_simulation_active()
    stats = db.get_stats()
    remote_host = db.get_setting("remote_host", "127.0.0.1")

    if args.json:
        data = {
            "gateway": {
                "port": 5000,
                "simulation_mode": sim,
                "remote_host": remote_host,
            },
            "vault": stats,
            "services": asyncio.run(providers.get_all_services_status()),
        }
        print(json.dumps(data, indent=2))
        return

    print_header("⚡ ECLIPSE UNIFIED GATEWAY STATUS")
    print(f"  Gateway Port     : 5000")
    print(f"  Simulation Mode  : {'ENABLED (Simulated Device)' if sim else 'OFF (Live Daemons)'}")
    print(f"  Cluster Host     : {remote_host}")
    print(f"  Database Vault   : {db.DB_PATH} ({stats['total_accounts']} accounts)")

    print_header("🤖 AI PROVIDER FLEET STATUS")
    services = asyncio.run(providers.get_all_services_status())
    headers = ["Provider", "Badge", "Port", "Host", "Status", "Latency", "Accounts"]
    rows = []
    grouped = stats.get("providers", {})
    for s in services:
        pid = s["id"]
        acc_count = grouped.get(pid, {}).get("total", 0)
        status_str = "● ONLINE" if s["running"] else "○ OFFLINE"
        if s.get("simulated"):
            status_str = "● SIMULATED"
        latency_str = f"{s['latency_ms']} ms" if s.get("latency_ms") is not None else "—"
        rows.append([
            s["name"],
            s["badge"],
            str(s["port"]),
            s["host"],
            status_str,
            latency_str,
            str(acc_count),
        ])
    print_table(headers, rows)
    print()


def cmd_limits(args):
    """Inspect remaining limits and quotas for Gemini."""
    db.init_db()
    data = asyncio.run(providers.get_all_limits())

    if args.json:
        print(json.dumps(data, indent=2))
        return

    print_header("📊 LIVE FEATURE LIMITS & QUOTAS (ECLIPSE)")

    # Gemini / Google DeepMind
    gm = data.get("gemini", {})
    gm_accounts = gm.get("accounts", [])
    print(f"\n[1] {gm.get('title', 'Google Gemini Account Quotas')} ({len(gm_accounts)} accounts)")
    if gm_accounts:
        headers = ["Account / Session", "Plan", "Status", "Images/Day", "Hourly Rate", "Deep Res", "Uploads", "Reset Window"]
        rows = []
        for a in gm_accounts:
            rows.append([
                a.get("email", "—"),
                a.get("type", "FREE"),
                a.get("status", "Active"),
                str(a.get("image_quota", "30")),
                str(a.get("reason_remaining", "Standard (60/hr)")),
                str(a.get("deep_research", "0 / day")),
                str(a.get("file_upload", "10 / prompt")),
                str(a.get("restore_at", "Daily (Midnight PST)")),
            ])
        print_table(headers, rows)
    else:
        print("    No Gemini engines loaded.")

    # GLM / Zhipu AI
    glm_obj = data.get("glm", {})
    glm_accounts = glm_obj.get("accounts", [])
    print(f"\n[2] {glm_obj.get('title', 'GLM / Zhipu AI Account Quotas')} ({len(glm_accounts)} accounts)")
    if glm_accounts:
        headers = ["Account / Session", "Plan", "Status", "Images/Day", "Video/Day", "Reasoning", "Deep Res", "Uploads", "Concurrency", "Reset Window"]
        rows = []
        for a in glm_accounts:
            rows.append([
                a.get("email", "—"),
                a.get("type", "FREE"),
                a.get("status", "Active"),
                str(a.get("image_quota", "10")),
                str(a.get("video_quota", "2 / day")),
                str(a.get("reason_remaining", "200 / day")),
                str(a.get("deep_research", "100 / day")),
                str(a.get("file_upload", "5 docs / day")),
                str(a.get("concurrency", "2 requests")),
                str(a.get("restore_at", "Daily (Midnight CST)")),
            ])
        print_table(headers, rows)
    else:
        print("    No GLM engines loaded.")
    print()


def cmd_accounts(args):
    """List or inspect stacked accounts in SQLite vault."""
    db.init_db()
    provider = args.provider.lower() if args.provider else None
    accounts = db.get_accounts(provider)

    if args.json:
        # Mask sensitive tokens
        sanitized = []
        for a in accounts:
            cp = dict(a)
            token = cp.get("token", "")
            if len(token) > 16:
                cp["token"] = token[:8] + "..." + token[-6:]
            sanitized.append(cp)
        print(json.dumps(sanitized, indent=2))
        return

    title = f"CREDENTIAL VAULT ({provider.upper() if provider else 'ALL PROVIDERS'})"
    print_header(title)
    if not accounts:
        print("  No accounts found in vault.")
        return

    headers = ["ID", "Provider", "Name / Email", "Plan", "Status", "Token (Masked)"]
    rows = []
    for a in accounts:
        token = a.get("token", "")
        masked = token[:6] + "..." + token[-4:] if len(token) > 12 else "****"
        rows.append([
            str(a["id"]),
            a["provider"].upper(),
            a.get("name") or a.get("identifier") or "—",
            (a.get("plan") or "free").upper(),
            a.get("status", "active"),
            masked,
        ])
    print_table(headers, rows)
    print()


def cmd_import(args):
    """Import accounts from JSON dump or file path."""
    source = args.source
    content = ""
    if Path(source).exists():
        content = Path(source).read_text(encoding="utf-8")
    else:
        content = source

    try:
        data = json.loads(content)
    except Exception as e:
        print(f"[-] Error: Could not parse JSON input: {e}")
        sys.exit(1)

    res = db.import_all_json(data)
    print(f"[+] {res.get('message', 'Import completed successfully!')}")


def cmd_export(args):
    """Export all accounts to a JSON file or stdout."""
    data = db.export_all_json()
    formatted = json.dumps(data, indent=2)
    if args.output:
        out_path = Path(args.output)
        # The export holds decrypted session tokens: create it owner-read/write only.
        fd = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(formatted)
        try:
            os.chmod(out_path, 0o600)
        except OSError:
            pass
        print(f"[+] Successfully exported {data['total_accounts']} accounts to {out_path}")
        print("[!] This file contains UNENCRYPTED session tokens. Store it somewhere private and delete it after importing.")
    else:
        print(formatted)


def cmd_key(args):
    """Show, set, or rotate the gateway key used for LAN, phone and tunnel access."""
    action = (args.action or "show").strip()
    if action == "rotate":
        key = security.rotate_gateway_key()
        print("[+] Gateway key rotated. Restart Eclipse; other devices must log in again.")
    elif action == "set" and getattr(args, "new_key", None):
        key = security.set_gateway_key(args.new_key)
        print(f"[+] Gateway key updated to: {key}")
    elif action not in ("show", "status") and not getattr(args, "new_key", None):
        key = security.set_gateway_key(action)
        print(f"[+] Gateway key updated to: {key}")
    else:
        key = security.get_gateway_key()
    print(f"    Gateway key : {key}")
    print("    Use it as the API key in OpenAI clients, or paste it on the login screen")
    print("    when opening Eclipse from another device.")


def cmd_simulate(args):
    """View or toggle Device Simulation Mode."""
    db.init_db()
    action = (args.action or "status").lower()
    if action in ("on", "enable", "1", "true"):
        db.set_setting("simulation_mode", "1")
        print("[+] Device Simulation Mode ENABLED.")
        print("    Eclipse will now simulate all models and providers cleanly without requiring local daemons.")
    elif action in ("off", "disable", "0", "false"):
        db.set_setting("simulation_mode", "0")
        print("[+] Device Simulation Mode DISABLED. Connecting to real provider daemons.")
    else:
        sim = providers.is_simulation_active()
        print(f"[*] Device Simulation Mode: {'ENABLED' if sim else 'DISABLED'}")
        print("    Usage: ./singular simulate [on|off]")


def cmd_host(args):
    """View or set remote provider cluster host."""
    db.init_db()
    if args.target:
        db.set_setting("remote_host", args.target)
        print(f"[+] Remote provider cluster host set to: {args.target}")
    else:
        current = db.get_setting("remote_host", "127.0.0.1")
        print(f"[*] Current provider cluster host: {current}")
        print("    Usage: ./singular host <ip_or_domain> (e.g. 192.168.1.100)")


def cmd_thinking(args):
    """View or configure thinking budget cap for any model."""
    db.init_db()
    model = (args.model or "").strip()
    budget = args.budget

    if not model or model in ("list", "all"):
        all_cfgs = db.get_all_model_settings()
        if not all_cfgs:
            print("[*] No custom thinking caps or model settings configured yet.")
            print("    Usage: ./singular thinking <model> <budget_tokens>")
            print("    Example: ./singular thinking claude-3-7-sonnet 8192")
            print("    Example: ./singular thinking gemini-3.8-flash-thinking 16384")
            return

        print_header("🧠 CONFIGURED MODEL THINKING CAPS & SETTINGS")
        headers = ["Model", "Thinking Budget", "Max Tokens", "Temperature"]
        rows = []
        for m, cfg in sorted(all_cfgs.items()):
            tb = cfg.get("thinking_budget")
            tb_str = f"{tb:,} tokens" if (tb is not None and tb > 0) else "Disabled (0)" if tb == 0 else "Default"
            mt = cfg.get("max_tokens", "—")
            temp = cfg.get("temperature", "—")
            rows.append([m, tb_str, str(mt), str(temp)])
        print_table(headers, rows)
        print("\n  Enforced automatically across all gateway /v1/chat/completions requests.")
        return

    if str(budget).lower() in ("reset", "delete", "remove", "default"):
        db.delete_model_settings(model)
        print(f"[+] Reset model settings for '{model}' to default.")
        return

    if budget is not None:
        try:
            budget_val = max(0, int(budget))
        except ValueError:
            print(f"[-] Invalid budget number: {budget}. Must be an integer like 8192 or 0.")
            return

        existing = db.get_model_settings(model)
        existing["thinking_budget"] = budget_val
        db.set_model_settings(model, existing)

        status_label = f"{budget_val:,} tokens" if budget_val > 0 else "DISABLED (0 tokens)"
        print(f"[+] Thinking budget cap for '{model}' set to: {status_label}")
        print("    This thinking budget is now enforced on all requests to Eclipse Gateway for this model.")
    else:
        cfg = db.get_model_settings(model)
        if not cfg:
            print(f"[*] No custom settings for model '{model}'. Upstream provider defaults will be used.")
            print(f"    To set thinking budget: ./singular thinking {model} <tokens>")
        else:
            tb = cfg.get("thinking_budget")
            tb_str = f"{tb:,} tokens" if (tb is not None and tb > 0) else "Disabled (0)" if tb == 0 else "Default"
            print(f"[*] Settings for '{model}':")
            print(f"    • Thinking Budget Cap : {tb_str}")
            if "max_tokens" in cfg:
                print(f"    • Max Tokens          : {cfg['max_tokens']}")
            if "temperature" in cfg:
                print(f"    • Temperature         : {cfg['temperature']}")


def _print_tool_event(event):
    """Show one tool-loop event from a streamed reply."""
    kind = event.get("type")
    if kind == "step_start":
        sys.stdout.write(f"\n\033[36m[step {event.get('step')}]\033[0m\n")
    elif kind == "tool_start":
        sys.stdout.write(f"\033[36m[tool]\033[0m {event.get('name')} {json.dumps(event.get('arguments') or {}, ensure_ascii=False)}\n")
    elif kind == "tool_result":
        if event.get("ok"):
            backend = f" via {event['backend']}" if event.get("backend") else ""
            sys.stdout.write(f"\033[36m[result]\033[0m {event.get('summary', '')}{backend} ({event.get('ms', 0)} ms)\n")
            for src in event.get("sources", []):
                sys.stdout.write(f"    [{src.get('n')}] {src.get('title', '')} - {src.get('url', '')}\n")
        else:
            sys.stdout.write(f"\033[31m[tool failed]\033[0m {event.get('error', '')}\n")
    elif kind == "step_limit":
        sys.stdout.write("\033[33m[step limit reached; answering with what was found]\033[0m\n")
    sys.stdout.flush()


def _print_tool_call(call):
    _print_tool_event({"type": "tool_start", **call})
    _print_tool_event({"type": "tool_result", **call})


def cmd_chat(args):
    """Execute a quick test completion through the local gateway."""
    import httpx

    model = args.model or "gemini-3.8-flash"
    prompt = args.prompt
    url = f"http://127.0.0.1:{args.port}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": args.stream,
    }
    if args.simulate:
        payload["simulate"] = True
    if getattr(args, "thinking", None) is not None:
        payload["thinking_budget"] = args.thinking
    tool_names = [t.strip() for t in (getattr(args, "tools", None) or "").split(",") if t.strip()]
    if tool_names:
        payload["eclipse_tools"] = tool_names
        if getattr(args, "max_steps", None):
            payload["eclipse_max_steps"] = args.max_steps
    is_reasoning = any(x in (model or "").lower() for x in ("think", "reason", "argon", "opus", "pro", "r1", "high", "medium"))
    timeout = 240.0 if (tool_names or is_reasoning) else 90.0

    print(f"[*] Routing to Eclipse Gateway ({model})...\n")

    if args.stream:
        try:
            with httpx.stream("POST", url, json=payload, timeout=timeout) as resp:
                if resp.status_code != 200:
                    print(f"[-] HTTP {resp.status_code}: {resp.read().decode('utf-8')}")
                    return
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                event = delta.get("eclipse_event")
                                if event:
                                    _print_tool_event(event)
                                    continue
                                content = delta.get("content", "")
                                reasoning = delta.get("reasoning_content", "")
                                if reasoning:
                                    sys.stdout.write(f"\033[90m{reasoning}\033[0m")
                                    sys.stdout.flush()
                                if content:
                                    sys.stdout.write(content)
                                    sys.stdout.flush()
                            elif "error" in chunk:
                                sys.stdout.write(f"\n[-] {chunk['error']}\n")
                                sys.stdout.flush()
                        except Exception:
                            pass
                print()
        except httpx.ConnectError:
            print(f"[-] Could not connect to Eclipse gateway at {url}.")
            print("    Start it first with: ./start.sh")
    else:
        try:
            resp = httpx.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                message = data.get("choices", [{}])[0].get("message", {})
                for step in message.get("eclipse_steps", []):
                    for call in step.get("calls", []):
                        _print_tool_call(call)
                print(message.get("content", ""))
            else:
                print(f"[-] HTTP {resp.status_code}: {resp.text}")
        except httpx.ConnectError:
            print(f"[-] Could not connect to Eclipse gateway at {url}.")
            print("    Start it first with: ./start.sh")


def cmd_model_audit(args):
    """Send one real Gemini request and inspect upstream model-selection evidence."""
    import re
    import httpx

    model = args.model
    url = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": True,
        "smooth": False,
        "model_audit": True,
    }

    print(f"[*] Auditing live Gemini Web routing for {model} (one generation request; uses quota)")
    content = []
    audit = None
    try:
        with httpx.stream("POST", url, json=payload, timeout=180.0) as resp:
            if resp.status_code != 200:
                raw = resp.read().decode("utf-8", "replace")
                print(f"[-] HTTP {resp.status_code}: {raw[:500]}")
                sys.exit(1)
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str):
                    content.append(text)
                event = delta.get("model_audit")
                if isinstance(event, dict):
                    audit = event
    except httpx.ConnectError:
        print(f"[-] Could not connect to the local gateway at {url}. Start it with ./start.sh.")
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"[-] Audit request failed ({type(exc).__name__}).")
        sys.exit(1)

    reply = "".join(content).strip()
    if reply:
        print(f"\nProbe answer: {reply[:500]}")
    if not audit:
        print("[-] No backend audit metadata was returned. Check that the updated Gemini engine is running.")
        sys.exit(3)

    print("\n--- Backend routing evidence ---")
    print(f"Requested model       : {audit.get('requested_model', model)}")
    print(f"Internal mode ID      : {audit.get('resolved_mode_id', 'unknown')}")
    print(f"Thinking level        : {audit.get('thinking_level', 'unknown')}")
    print(f"Selection header sent : {'yes' if audit.get('selection_header_sent') else 'NO'}")
    print(f"Cookie bundle supplied: {'yes' if audit.get('cookie_bundle_supplied') else 'no'}")
    print(f"__Secure-1PSID present : {'yes' if audit.get('secure_psid_present') else 'no'}")
    print(f"SIDCC/PSIDCC present   : {'yes' if audit.get('session_cookie_cc_present') else 'no'}")
    print(f"Session XSRF token avail: {'yes' if audit.get('access_token_available') else 'no'}")
    print(f"Session ID available   : {'yes' if audit.get('session_id_available') else 'no'}")
    print(f"Expected bucket       : {', '.join(audit.get('expected_model_names') or []) or 'unknown'}")
    print(f"Observed bucket       : {', '.join(audit.get('observed_model_names') or []) or 'unknown'}")
    print(f"Observed variant ID   : {audit.get('observed_variant_id') or 'unavailable'}")
    print(f"History turn match    : {audit.get('history_turn_match') or 'unavailable'}")
    verdict = audit.get("identity_verification", "unverified")
    print(f"Identity assessment   : {verdict}")

    sanity_ok = bool(re.search(r"\b323\b", reply))
    print(f"Arithmetic sanity     : {'PASS' if sanity_ok else 'NOT CONFIRMED'} (expected 323)")
    for note in audit.get("notes") or []:
        print(f"Note                  : {note}")

    if verdict in ("bucket_mismatch",):
        sys.exit(2)
    if verdict not in ("variant_id_match", "bucket_match"):
        print("Result: the actual model bucket could not be verified conclusively.")
        sys.exit(3)
    if not sanity_ok:
        print("Result: route evidence matched, but the probe answer failed its deterministic check.")
        sys.exit(1)
    print("Result: route evidence matched the requested model bucket.")


def cmd_bench(args):
    """Run the scripted test chats against a preset through the running gateway and print what passed."""
    import httpx
    base = f"http://127.0.0.1:{args.port}"
    try:
        if args.list:
            res = httpx.get(f"{base}/api/bench/scenarios", timeout=10.0)
            if res.status_code == 404:
                print("The running gateway is older than this command. Restart it (./start.sh restart) and try again.")
                sys.exit(1)
            data = res.json()
            rows = [[s["id"], "built-in" if s.get("builtin") else "yours", s["expect"]["search"], s["name"]] for s in data["builtin"] + data["custom"]]
            print_table(["ID", "KIND", "SEARCH", "NAME"], rows)
            return
        if not args.preset or not args.model:
            print("Give a preset and a model:  ./singular bench --preset miyabi --model kimi-k3   (or --list)")
            sys.exit(2)
        body = {"preset": args.preset, "model": args.model}
        if args.only:
            body["scenarios"] = [x.strip() for x in args.only.split(",") if x.strip()]
        started = httpx.post(f"{base}/api/bench/runs", json=body, timeout=15.0)
        if started.status_code == 404:
            print("The running gateway is older than this command. Restart it (./start.sh restart) and try again.")
            sys.exit(1)
        if started.status_code >= 400:
            err = started.json().get("error", started.text)
            print("Could not start:", err.get("message", err) if isinstance(err, dict) else err)
            sys.exit(1)
        run = started.json()
        print_header(f"Test bench: {args.model}@{args.preset}  ({run['total']} tests, uses your provider quota)")
        shown = 0
        while True:
            time.sleep(2.0)
            run = httpx.get(f"{base}/api/bench/runs/{run['id']}", timeout=15.0).json()
            for r in run["results"][shown:]:
                mark = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}.get(r["status"], r["status"])
                print(f"[{mark}] {r['name']}  ({(r.get('ms') or 0) / 1000:.1f} s)" + (f"  searched: {'; '.join(r['queries'])}" if r["queries"] else ""))
                for c in r["checks"]:
                    if not c["ok"]:
                        print(f"        x {c['name']}: {c['detail']}")
                for n in r.get("notes", []):
                    print(f"        i {n}")
                if r["status"] != "pass":
                    print(f"        log entry #{r.get('log_id')}  (Presets tab, Request log)")
            shown = len(run["results"])
            if run["status"] != "running":
                break
        s = run["summary"]
        print(f"\n{s['pass']} passed, {s['fail']} failed, {s['error']} errors, {s['done']} of {s['total']} run  [{run['status']}]")
        sys.exit(0 if run["status"] == "done" and not s["fail"] and not s["error"] else 1)
    except httpx.ConnectError:
        print(f"Cannot reach the gateway on port {args.port}. Start Eclipse first (./start.sh).")
        sys.exit(1)


def cmd_service(args):
    """Start, stop, or restart provider services."""
    action = args.action.lower()
    pid = args.provider.lower() if args.provider else None
    if pid in ("all", "*", "fleet"):
        pid = None

    # If Eclipse Gateway is running on port 5000, dispatch through it so workers run in-process
    gateway_online = False
    try:
        import httpx
        check = httpx.get("http://127.0.0.1:5000/healthz", timeout=1.0)
        if check.status_code == 200:
            gateway_online = True
    except Exception:
        gateway_online = False

    if gateway_online:
        import httpx
        try:
            if action == "start":
                url = f"http://127.0.0.1:5000/api/services/{pid}/start" if pid else "http://127.0.0.1:5000/api/services/start_all"
                resp = httpx.post(url, timeout=10.0)
                data = resp.json()
                if pid:
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    print("[+] Started all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
            elif action == "stop":
                url = f"http://127.0.0.1:5000/api/services/{pid}/stop" if pid else "http://127.0.0.1:5000/api/services/stop_all"
                resp = httpx.post(url, timeout=10.0)
                data = resp.json()
                if pid:
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    print("[+] Stopped all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
            elif action == "restart":
                if pid:
                    resp = httpx.post(f"http://127.0.0.1:5000/api/services/{pid}/restart", timeout=10.0)
                    data = resp.json()
                    print(f"[{data.get('status')}] {data.get('message')}")
                else:
                    httpx.post("http://127.0.0.1:5000/api/services/stop_all", timeout=10.0)
                    time.sleep(1.0)
                    resp = httpx.post("http://127.0.0.1:5000/api/services/start_all", timeout=10.0)
                    data = resp.json()
                    print("[+] Restarted all services via Gateway backend:")
                    for p, r in data.get("results", {}).items():
                        print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
                return
        except Exception:
            pass

    # Gateway not running: direct provider start
    if action == "start":
        if pid:
            res = providers.start_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            res = providers.start_all_services()
            print("[+] Started all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
    elif action == "stop":
        if pid:
            res = providers.stop_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            res = providers.stop_all_services()
            print("[+] Stopped all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")
    elif action == "restart":
        if pid:
            providers.stop_provider(pid)
            time.sleep(1.0)
            res = providers.start_provider(pid)
            print(f"[{res.get('status')}] {res.get('message')}")
        else:
            providers.stop_all_services()
            time.sleep(1.0)
            res = providers.start_all_services()
            print("[+] Restarted all services:")
            for p, r in res.get("results", {}).items():
                print(f"    • {p.upper()}: [{r.get('status')}] {r.get('message')}")


def cmd_tunnel(args):
    """Manage ngrok public cloud tunnel and native installation."""
    import tunnel
    action = getattr(args, "action", "status") or "status"

    if action == "status":
        stat = tunnel.get_tunnel_status()
        if getattr(args, "json", False):
            print(json.dumps(stat, indent=2))
            return

        print_header("🌐 ECLIPSE CLOUD TUNNEL (NGROK)")
        status_label = "● ONLINE" if stat.get("status") == "online" else "○ OFFLINE"
        print(f"  Status        : {status_label}")
        print(f"  Installed     : {'Yes (' + str(stat.get('bin_path')) + ')' if stat.get('installed') else 'No'}")
        print(f"  Device / Arch : {stat.get('arch', 'Standard')}{' (Termux Phone)' if stat.get('is_termux') else ''}")
        print(f"  Authtoken     : {'Configured' if stat.get('has_authtoken') else 'Missing'}")
        if stat.get("public_url"):
            print(f"  Public URL    : {stat.get('public_url')}")
            print(f"  API Endpoint  : {stat.get('api_url')}")
            print(f"  Chat Complete : {stat.get('chat_completions_url')}")
        else:
            print(f"  Note          : {stat.get('message')}")
        print("=" * 70 + "\n")

    elif action == "start":
        print("[*] Starting ngrok tunnel for port 5000...")
        res = tunnel.start_tunnel(port=5000)
        if res.get("status") == "online":
            print("[✓] Tunnel is LIVE!")
            print(f"    Public URL   : {res.get('public_url')}")
            print(f"    API Endpoint : {res.get('api_url')}")
            print("    Access       : requires the gateway key (run './singular key')")
        else:
            print(f"[!] Failed to start tunnel: {res.get('message')}")

    elif action == "stop":
        print("[*] Stopping ngrok tunnel...")
        res = tunnel.stop_tunnel()
        print("[✓] ngrok tunnel stopped.")

    elif action == "install":
        print("[*] Downloading & installing native ngrok binary for this device...")
        res = tunnel.install_ngrok(force=True)
        if res.get("status") == "ok":
            print(f"[✓] Success: {res.get('message')}")
            print(f"    Path: {res.get('path')}")
            print(f"    Version: {res.get('version')}")
        else:
            print(f"[!] Installation failed: {res.get('message')}")

    elif action == "token":
        token = getattr(args, "token_val", None)
        if not token:
            print("[!] Please provide a token: ./singular tunnel token <YOUR_NGROK_AUTHTOKEN>")
            return
        res = tunnel.save_authtoken(token)
        if res.get("status") == "ok":
            print(f"[✓] {res.get('message')}")
        else:
            print(f"[!] Failed to configure token: {res.get('message')}")


def cmd_claudecode(args):
    """Manage Claude Code bridge (disabled in Eclipse)."""
    print("  [!] Claude Code bridge has been removed from Eclipse.")


def cmd_update(args):
    """Check for and pull latest updates from git repository."""
    import subprocess
    print_header("Eclipse Repository Auto-Updater")
    root_dir = SCRIPT_DIR.parent
    if not (root_dir / ".git").exists():
        print("  [!] Not a git repository directory. Auto-updater unavailable.")
        return

    print("  [*] Checking remote repository for latest commits...")
    try:
        subprocess.run(["git", "fetch", "--quiet", "origin", "main"], cwd=root_dir, check=False, timeout=15)
        # Ensure local branch is main and tracks origin/main
        try:
            cur_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root_dir, text=True).strip()
            if cur_branch != "main":
                subprocess.run(["git", "checkout", "-B", "main", "origin/main"], cwd=root_dir, capture_output=True)
            subprocess.run(["git", "branch", "--set-upstream-to=origin/main", "main"], cwd=root_dir, capture_output=True)
        except Exception:
            pass
        local_rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root_dir, text=True).strip()
        try:
            remote_rev = subprocess.check_output(["git", "rev-parse", "FETCH_HEAD"], cwd=root_dir, text=True).strip()
        except Exception:
            try:
                remote_rev = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=root_dir, text=True).strip()
            except Exception:
                remote_rev = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=root_dir, text=True).strip()

        if local_rev == remote_rev:
            print(f"  [✓] Eclipse is already up to date! (commit {local_rev[:8]})")
            return

        print(f"  [🔄] Updating from {local_rev[:8]} -> {remote_rev[:8]}...")
        res = subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=root_dir, text=True, capture_output=True)
        if res.returncode == 0:
            print("  [✨] Eclipse successfully updated to the latest version!")
        else:
            res = subprocess.run(["git", "pull", "origin", "main"], cwd=root_dir, text=True, capture_output=True)
            if res.returncode == 0:
                print("  [✨] Eclipse successfully updated!")
            else:
                # Stash uncommitted changes and retry clean pull
                subprocess.run(["git", "stash", "-q"], cwd=root_dir, capture_output=True)
                retry = subprocess.run(["git", "pull", "origin", "main"], cwd=root_dir, text=True, capture_output=True)
                subprocess.run(["git", "stash", "pop", "-q"], cwd=root_dir, capture_output=True)
                if retry.returncode == 0:
                    print("  [✨] Eclipse successfully updated to the latest version!")
                else:
                    print(f"  [!] Git pull failed: {retry.stderr.strip() or res.stderr.strip()}")
    except Exception as e:
        print(f"  [!] Auto-update error: {e}")


def cmd_login(args):
    """Authenticate and stack an account via official browser OAuth login flow."""
    provider = (getattr(args, "provider", None) or "antigravity").lower().strip()
    if provider in ("antigravity", "agy", "google", "google-antigravity"):
        try:
            from engines import antigravity
        except ImportError:
            from eclipse.engines import antigravity
        antigravity.start_oauth_listener()
        oauth_url = antigravity.get_oauth_url()
        print_header("⚡ ECLIPSE: GOOGLE ANTIGRAVITY OAUTH LOGIN")
        print("  1. Opening official Google Sign-In in your default browser...")
        print(f"     Direct Link:\n     {oauth_url}\n")
        print("  2. Select your Google account and grant permissions.")
        print(f"  3. Waiting for authentication callback on port {antigravity.OAUTH_PORT}...\n")
        try:
            import webbrowser
            webbrowser.open(oauth_url)
        except Exception:
            pass

        start_time = time.time()
        while (time.time() - start_time) < 180:
            latest = antigravity.get_latest_oauth_event()
            if latest and latest.get("timestamp", 0) >= (start_time - 3):
                accounts = db.get_accounts("antigravity")
                print("=" * 70)
                print(f"  [+] SUCCESS! Account '{latest.get('email')}' connected and saved to SQLite vault!")
                print(f"  [+] Total Antigravity accounts stacked: {len(accounts)}")
                print(f"  [+] Stack another account: ./nephis login antigravity")
                print(f"  [+] Test inference anytime: ./nephis chat 'Hello' -m gemini-3.8-flash")
                print("=" * 70)
                return
            time.sleep(1)
        print("[-] Login timed out (180s). Please try again or paste credentials manually.")
    else:
        print(f"[-] Browser login not currently supported for provider '{provider}'. Use './nephis accounts {provider}' to manage.")


def cmd_restart(args):
    """Restart Eclipse gateway by clearing ports and launching server."""
    from server import free_listening_ports
    print_header("RESTARTING ECLIPSE GATEWAY")
    print("  [*] Clearing port 5000...", flush=True)
    free_listening_ports([5000])
    time.sleep(0.4)
    print("  [✓] Port successfully cleared. Launching gateway...\n", flush=True)
    # Clean exec replacement
    os.execv(sys.executable, [sys.executable, str(SCRIPT_DIR / "server.py")])


def cmd_autofetch(args):
    """Auto-discover tokens from local browsers (gemini, mimo, janitor, or antigravity)."""
    target = (args.target or "gemini").lower().strip()
    print_header(f"AUTO-FETCH BROWSER TOKENS ({target.upper()})")

    if target in ("gemini", "google"):
        try:
            from engines.gemini import auto_fetch_gemini_token
        except ImportError:
            from eclipse.engines.gemini import auto_fetch_gemini_token
        print("  [*] Scanning local browser cookie vaults for Gemini sessions (Chrome, Brave, Edge, Firefox, Chromium)...")
        res = auto_fetch_gemini_token(save_to_db=True)
        if res.get("ok"):
            print(f"  [✓] Successfully detected Gemini session from {res.get('browser')} ({res.get('profile', 'Default')})!")
            print(f"  [✓] __Secure-1PSID   : {res.get('masked_token')}")
            print(f"  [✓] __Secure-1PSIDTS : Loaded & Valid")
            print(f"  [✓] SAPISID          : {'Present' if res.get('has_sapisid') else 'Missing'}")
            print(f"  [✓] Saved into SQLite vault successfully under 'gemini' provider!")
            print(f"\n  Test chat inference:")
            print(f"    ./nephis chat \"Hello Gemini\" -m gemini-4-argon")
        else:
            print(f"  [-] {res.get('detail', 'No active session found.')}")

    elif target in ("mimo", "xiaomi"):
        try:
            from mimo import auto_fetch_mimo_token
        except ImportError:
            from eclipse.mimo import auto_fetch_mimo_token
        print("  [*] Scanning local browser cookie vaults (Chrome, Brave, Edge, Firefox, Chromium)...")
        res = auto_fetch_mimo_token(save_to_db=True)
        if res.get("ok"):
            print(f"  [✓] Successfully detected Xiaomi MiMo session from {res.get('browser')} ({res.get('profile', 'Default')})!")
            print(f"  [✓] User ID    : {res.get('user_id') or '—'}")
            print(f"  [✓] Token      : {res.get('token_masked')}")
            print(f"  [✓] Auto-Renew : {'passToken Active (24h transparent refresh)' if res.get('has_pass_token') else 'serviceToken session'}")
            print(f"  [✓] Saved into SQLite vault successfully!")
            print(f"\n  Test chat inference:")
            print(f"    ./singular chat \"Hello MiMo\" -m mimo-v2.6-pro")
        else:
            print(f"  [-] {res.get('detail', 'No active session found.')}")
            print(f"  [TIP] Log into https://aistudio.xiaomimimo.com in Chrome, Brave, Edge, or Firefox, then re-run:")
            print(f"    ./singular autofetch mimo")

    elif target in ("janitor", "janitorai"):
        try:
            from janitor import auto_fetch_janitor_token
        except ImportError:
            from eclipse.janitor import auto_fetch_janitor_token
        print("  [*] Scanning browser cookies for JanitorAI auth tokens...")
        res = auto_fetch_janitor_token()
        if res.get("ok"):
            print(f"  [✓] Successfully detected Janitor token from {res.get('browser')}!")
            print(f"  [✓] Token: {res.get('token')[:16]}...")
        else:
            print(f"  [-] {res.get('detail', 'No token found.')}")

    elif target in ("antigravity", "agy"):
        try:
            from engines import antigravity
        except ImportError:
            from eclipse.engines import antigravity
        print("  [*] Scanning local IDE storage and ~/.gemini credentials...")
        creds = antigravity._load_local_fallback_credentials()
        if creds:
            saved = 0
            for c in creds:
                raw = c.get("token") or ""
                if raw:
                    parsed = db.parse_credential("antigravity", raw)
                    if parsed:
                        db.add_account("antigravity", parsed)
                        saved += 1
            print(f"  [✓] Successfully auto-detected and stacked {saved} Antigravity account(s) into vault!")
        else:
            print("  [-] No local Antigravity credentials found.")
    else:
        print(f"  [-] Unknown autofetch target '{target}'. Supported: mimo, janitor, antigravity")



# ==============================================================================
# Main Dispatcher
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="singular",
        description="Eclipse AI Gateway & Device Management CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # status
    p_status = subparsers.add_parser("status", help="Inspect gateway, providers, and accounts")
    p_status.add_argument("--json", action="store_true", help="Output compact JSON")

    # limits
    p_limits = subparsers.add_parser("limits", help="Inspect quotas and rate limits across providers")
    p_limits.add_argument("--json", action="store_true", help="Output compact JSON")

    # accounts
    p_accounts = subparsers.add_parser("accounts", help="List stacked accounts in SQLite vault")
    p_accounts.add_argument("provider", nargs="?", default=None, help="Filter by provider (gemini, claude, etc.)")
    p_accounts.add_argument("--json", action="store_true", help="Output JSON with masked tokens")

    # import
    p_import = subparsers.add_parser("import", help="Import accounts from JSON dump or file")
    p_import.add_argument("source", help="Path to JSON file or raw JSON string")

    # export
    p_export = subparsers.add_parser("export", help="Export account vault to JSON")
    p_export.add_argument("output", nargs="?", default=None, help="Output file path (default: stdout)")

    # simulate
    p_sim = subparsers.add_parser("simulate", help="Toggle device simulation mode")
    p_sim.add_argument("action", nargs="?", choices=["on", "off", "status"], default="status")

    # host
    p_host = subparsers.add_parser("host", help="View or set remote provider cluster host")
    p_host.add_argument("target", nargs="?", default=None, help="Remote host IP or hostname")

    # chat
    p_chat = subparsers.add_parser("chat", help="Send a test chat completion to Eclipse")
    p_chat.add_argument("prompt", help="Prompt text to test")
    p_chat.add_argument("-m", "--model", default="gemini-2.5-flash", help="Model name (default: gemini-2.5-flash)")
    p_chat.add_argument("--stream", action="store_true", default=True, help="Stream response via SSE")
    p_chat.add_argument("--no-stream", dest="stream", action="store_false")
    p_chat.add_argument("--thinking", type=int, default=None, help="Thinking budget token cap override (e.g. 8192, 0 to disable)")
    p_chat.add_argument("--tools", default=None, help="Comma-separated tools to run: search, url (e.g. --tools search)")
    p_chat.add_argument("--max-steps", type=int, default=None, help="Maximum tool iterations (default: 3)")
    p_chat.add_argument("--simulate", action="store_true", help="Force simulated response")
    p_chat.add_argument("-p", "--port", type=int, default=5000, help="Gateway port (default: 5000)")

    # model-audit (live Gemini Web routing verification; uses one generation request)
    p_audit = subparsers.add_parser("model-audit", help="Audit actual Gemini Web model routing against saved-turn metadata")
    p_audit.add_argument("-m", "--model", required=True, help="Gemini Web model alias to audit")
    p_audit.add_argument("--prompt", default="Compute 17 * 19 and return only the integer.", help="Single deterministic probe prompt")
    p_audit.add_argument("-p", "--port", type=int, default=5000, help="Gateway port (default: 5000)")

    # bench (SillyTavern preset test suite)
    p_bench = subparsers.add_parser("bench", help="Run the test bench against a preset through the running gateway")
    p_bench.add_argument("--preset", help="Name of the preset to test (or use --list)")
    p_bench.add_argument("-m", "--model", help="Model to run the tests with")
    p_bench.add_argument("--only", help="Run only these scenario ids, comma-separated")
    p_bench.add_argument("--list", action="store_true", help="List scenarios and exit")
    p_bench.add_argument("-p", "--port", type=int, default=5000, help="Gateway port (default: 5000)")

    # thinking (model settings & budget cap)
    p_th = subparsers.add_parser("thinking", help="Inspect or set persistent thinking budget caps for models")
    p_th.add_argument("model", nargs="?", default=None, help="Model name (or 'list' to view all)")
    p_th.add_argument("budget", nargs="?", default=None, help="Budget tokens (e.g. 8192, 0 to disable, or 'reset')")

    # service
    p_svc = subparsers.add_parser("service", help="Control provider daemons")
    p_svc.add_argument("action", choices=["start", "stop", "restart", "status"])
    p_svc.add_argument("provider", nargs="?", default=None, help="Provider ID (gemini, claude, etc.)")

    # tunnel
    p_tun = subparsers.add_parser("tunnel", help="Manage ngrok cloud tunnel and native installation")
    p_tun.add_argument("action", nargs="?", choices=["status", "start", "stop", "install", "token"], default="status")
    p_tun.add_argument("token_val", nargs="?", default=None, help="Authtoken value when using 'token'")
    p_tun.add_argument("--json", action="store_true", help="Output compact JSON")

    # claudecode
    p_cc = subparsers.add_parser("claudecode", help="Manage Claude Code bridge for third-party inference")
    p_cc.add_argument("action", nargs="?", choices=["status", "start", "stop", "restart"], default="status")
    p_cc.add_argument("--port", type=int, default=6045, help="Bridge port (default: 6045)")
    p_cc.add_argument("--json", action="store_true", help="Output compact JSON")

    # key
    p_key = subparsers.add_parser("key", help="Show, set or rotate the gateway key for LAN/phone/tunnel access")
    p_key.add_argument("action", nargs="?", default="show", help="'show', 'rotate', or key string to set")
    p_key.add_argument("new_key", nargs="?", default=None, help="Key value when using 'set <key>'")

    # login
    p_login = subparsers.add_parser("login", help="Authenticate and stack account via official Google OAuth")
    p_login.add_argument("provider", nargs="?", default="antigravity", help="Provider to login (default: antigravity)")

    # autofetch
    p_autofetch = subparsers.add_parser("autofetch", help="Auto-discover tokens from local browsers (gemini, mimo, janitor, antigravity)")
    p_autofetch.add_argument("target", nargs="?", default="gemini", help="Target: gemini, mimo, janitor, or antigravity (default: gemini)")

    # update / upgrade
    subparsers.add_parser("update", help="Check and pull latest updates from repository")
    subparsers.add_parser("upgrade", help="Alias for update")

    # restart
    subparsers.add_parser("restart", help="Restart Eclipse gateway (clears port 5000)")

    args = parser.parse_args()

    if not args.subcommand or args.subcommand == "status":
        cmd_status(args if args.subcommand else argparse.Namespace(json=False))
    elif args.subcommand == "login":
        cmd_login(args)
    elif args.subcommand == "autofetch":
        cmd_autofetch(args)
    elif args.subcommand == "limits":
        cmd_limits(args)
    elif args.subcommand == "accounts":
        cmd_accounts(args)
    elif args.subcommand == "import":
        cmd_import(args)
    elif args.subcommand == "export":
        cmd_export(args)
    elif args.subcommand == "simulate":
        cmd_simulate(args)
    elif args.subcommand == "host":
        cmd_host(args)
    elif args.subcommand == "chat":
        cmd_chat(args)
    elif args.subcommand == "model-audit":
        cmd_model_audit(args)
    elif args.subcommand == "bench":
        cmd_bench(args)
    elif args.subcommand == "thinking":
        cmd_thinking(args)
    elif args.subcommand == "service":
        cmd_service(args)
    elif args.subcommand == "tunnel":
        cmd_tunnel(args)
    elif args.subcommand == "claudecode":
        cmd_claudecode(args)
    elif args.subcommand == "key":
        cmd_key(args)
    elif args.subcommand in ("update", "upgrade"):
        cmd_update(args)
    elif args.subcommand == "restart":
        cmd_restart(args)


if __name__ == "__main__":
    main()

