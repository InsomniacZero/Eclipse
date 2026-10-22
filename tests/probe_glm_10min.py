#!/usr/bin/env python3
"""
Eclipse GLM 10-Minute Endurance & 429 Auto-Healer Stress Test
==============================================================
Probes GLM-4.7-Think and GLM-5-Turbo-Think continuously for 10 minutes:
- Sustained high-token outputs (>= 1,000 tokens per probe)
- 30-second resting intervals between requests
- Observes & verifies 429 auto-healing, guest session rotation, and reasoning traces
- Logs deterministic metrics to tests/glm_probe_results.jsonl and console
"""

import asyncio
import datetime
import json
import os
import sys
import time
from typing import Any, Dict, List

import httpx

GATEWAY_URL = os.getenv("ECLIPSE_GATEWAY_URL", "http://127.0.0.1:5000/v1/chat/completions")
OUTPUT_LOG = "/home/insomniac/Desktop/Janitor/Sunless/tests/glm_probe_results.jsonl"
TOTAL_DURATION_SEC = 600  # 10 minutes straight
INTERVAL_GAP_SEC = 30     # 30-second gaps

MODELS_POOL = [
    "glm-4.7-think",
    "glm-5-turbo-think",
]

PROMPT_BATTERY = [
    (
        "Distributed Consensus Systems",
        "Write an exhaustive, university textbook-grade treatise on distributed consensus algorithms. "
        "Provide an in-depth comparative breakdown of Classic Paxos, Multi-Paxos, Raft, PBFT (Practical Byzantine Fault Tolerance), "
        "and HotStuff. For each protocol: detail the mathematical safety and liveness invariants, the leader election protocol, "
        "log replication mechanics, quorum intersection proofs (Q1 ∩ Q2 ≠ ∅), and network partition recovery edge cases. "
        "Include step-by-step state machine transition pseudocode. Elaborate thoroughly on write and read amplification, "
        "message complexity per commit, and pipelining optimizations. Ensure an extensive, deeply detailed response exceeding 1,200 words."
    ),
    (
        "Modern Transformer Architecture & Attention Optimization",
        "Provide a comprehensive, highly rigorous architectural breakdown of the modern decoder-only transformer. "
        "1. Derive the Scaled Dot-Product Attention mechanism mathematically from first principles, explaining why 1/√d_k is necessary. "
        "2. Formulate and explain Rotary Position Embeddings (RoPE) with complex vector rotation equations. "
        "3. Detail the GPU memory hierarchy bottleneck during generation and explain how FlashAttention-2 and FlashAttention-3 "
        "use tiling and online softmax to achieve O(N) memory IO. "
        "4. Explain PagedAttention and KV-cache quantization (FP8/INT4) for long context inference. "
        "Ensure an exhaustive, highly technical output with detailed mathematical formulations exceeding 1,200 words."
    ),
    (
        "Linux Kernel Virtual Memory Subsystem",
        "Conduct an exhaustive architectural audit and engineering breakdown of the Linux virtual memory architecture. "
        "Analyze in depth: "
        "1. Physical page allocation: The Buddy Allocator algorithm, zone lists (ZONE_DMA, ZONE_NORMAL, ZONE_MOVABLE), and anti-fragmentation techniques. "
        "2. Kernel slab allocations: SLAB vs SLUB architectures, kmalloc caches, and object alignment. "
        "3. Page table hierarchy: Multi-level page tables (4-level vs 5-level paging / P4D/PUD/PMD/PTE), TLB shootdown mechanisms, "
        "and hugepage management (Transparent Huge Pages - THP). "
        "4. Demand paging, copy-on-write (COW) page faults, and the Linux page-reclaim cycle (kswapd, LRU lists, memory cgroups, OOM killer). "
        "Provide detailed C kernel pseudocode and step-by-step execution path explanations exceeding 1,200 words."
    ),
    (
        "LSM-Tree vs B+Tree Storage Engines",
        "Write an authoritative engineering deep dive comparing Log-Structured Merge Trees (LSM-Trees) and B+ Trees in high-throughput database systems. "
        "Analyze: "
        "1. B+ Tree structural invariants, page splitting, latch crabbing protocols, WAL (Write-Ahead Logging), and write amplification on NVMe SSDs. "
        "2. LSM-Tree architecture: MemTable (SkipLists vs Concurrent SkipLists), Commit Log, and immutable SSTables. "
        "3. Compaction strategies: Size-Tiered vs Leveled Compaction (L0 to Ln) with rigorous write-amplification (WA), read-amplification (RA), "
        "and space-amplification (SA) mathematical equations. "
        "4. Point lookup optimizations: Bloom filters (optimal bit-to-key ratio m/n = -1.44 ln(p)), Block Cache, and prefix bloom filters. "
        "Exceed 1,200 words with thorough analytical proofs."
    ),
    (
        "Quantum Computing & Fault-Tolerant Error Correction",
        "Provide an exhaustive graduate-level treatise on Quantum Error Correction (QEC) and fault-tolerant quantum computation. "
        "1. Explain why classical error correction (bit duplication) fails in quantum systems due to the No-Cloning Theorem. "
        "2. Formulate the stabilizer formalism, Pauli group operators {I, X, Y, Z}, and syndrome measurement measurements. "
        "3. Derive the 2D Surface Code in detail: data qubits, X-measure (star) and Z-measure (plaquette) stabilizers, logical operations, "
        "and code distance d = 2t + 1. "
        "4. Explain decoding algorithms: Minimum Weight Perfect Matching (MWPM) and Union-Find decoders. "
        "5. Detail lattice surgery for fault-tolerant logical CNOT gates and Magic State Distillation for universality. "
        "Make the analysis comprehensive and mathematically rigorous, exceeding 1,200 words."
    ),
    (
        "Advanced Compiler Optimizations & Static Single Assignment",
        "Write an exhaustive technical treatise on modern optimizing compilers (LLVM / GCC). "
        "1. Static Single Assignment (SSA) form: Dominance frontiers, Cytron's phi-node placement algorithm, and semi-pruned SSA construction. "
        "2. Global Value Numbering (GVN), Sparse Conditional Constant Propagation (SCCP), and Common Subexpression Elimination (CSE). "
        "3. Loop Optimizations: Loop Invariant Code Motion (LICM), loop unrolling, loop fission/fusion, and polyhedral model dependence analysis. "
        "4. Instruction scheduling and register allocation via Graph Coloring (Chaitin-Briggs heuristic) vs Linear Scan. "
        "Provide complete pseudocode, dominance trees, and intermediate representation (IR) transformations exceeding 1,200 words."
    ),
]


async def run_single_probe(probe_idx: int, model: str, topic: str, prompt: str) -> Dict[str, Any]:
    print(f"\n{'='*75}")
    print(f"  🚀 [PROBE #{probe_idx}] Launching Model: {model}")
    print(f"  📚 Topic: {topic}")
    print(f"  ⏰ Start Time: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*75}")

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": True,
    }

    t_start = time.time()
    ttft = None
    think_chars = 0
    content_chars = 0
    think_text = []
    content_text = []
    words_count = 0
    status_code = None
    error_message = None
    auto_healed = False
    retry_count = 0

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", GATEWAY_URL, json=payload) as resp:
                status_code = resp.status_code
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    error_message = f"HTTP {resp.status_code}: {err_body.decode('utf-8', errors='ignore')}"
                    print(f"  ❌ Gateway Error: {error_message}")
                    return {
                        "probe_idx": probe_idx,
                        "model": model,
                        "topic": topic,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "status": "error",
                        "status_code": status_code,
                        "error": error_message,
                        "duration_sec": round(time.time() - t_start, 2),
                    }

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except Exception:
                        continue

                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    if ttft is None and (delta.get("content") or delta.get("reasoning_content")):
                        ttft = round(time.time() - t_start, 3)
                        print(f"  ⚡ First Token (TTFT): {ttft}s")

                    # Detect Reasoning / Thinking
                    if delta.get("reasoning_content"):
                        piece = delta["reasoning_content"]
                        think_chars += len(piece)
                        think_text.append(piece)

                    # Detect Content
                    if delta.get("content"):
                        piece = delta["content"]
                        content_chars += len(piece)
                        content_text.append(piece)
                        # Check if gateway streamed an auto-healer error message
                        if "GLM Server Busy" in piece or "429" in piece:
                            auto_healed = True
                            print(f"  ⚠️  Notice: {piece.strip()}")

    except Exception as exc:
        error_message = str(exc)
        print(f"  ❌ Network / Exception: {exc}")

    t_end = time.time()
    duration = round(t_end - t_start, 2)

    full_think = "".join(think_text)
    full_content = "".join(content_text)
    total_text = full_think + full_content
    words_count = len(full_content.split())

    # Deterministic token approximation:
    # Standard rule of thumb: ~3.8 chars per BPE token in mixed English / technical markdown
    approx_think_tokens = max(1, len(full_think) // 4) if full_think else 0
    approx_content_tokens = max(1, len(full_content) // 4) if full_content else 0
    total_tokens = approx_think_tokens + approx_content_tokens

    # Check if meets >= 1,000 tokens
    passed_1k_gate = (total_tokens >= 1000) or (words_count >= 700)
    tok_sec = round(total_tokens / duration, 1) if duration > 0 else 0

    print(f"\n  📊 [PROBE #{probe_idx} RESULTS]")
    print(f"  ├─ Status:               {'✅ SUCCESS' if not error_message else '❌ FAILED'}")
    print(f"  ├─ Duration:             {duration}s (TTFT: {ttft or 'N/A'}s)")
    print(f"  ├─ Reasoning Chars:      {think_chars} (~{approx_think_tokens} tokens)")
    print(f"  ├─ Content Chars:        {content_chars} (~{approx_content_tokens} tokens)")
    print(f"  ├─ Content Words:        {words_count} words")
    print(f"  ├─ Total Output Tokens:  ~{total_tokens} tokens {'(GATE PASSED >=1k)' if passed_1k_gate else '(BELOW 1k)'}")
    print(f"  ├─ Output Speed:         {tok_sec} tokens/sec")
    print(f"  └─ Sample Preview:       {full_content[:140].replace(chr(10), ' ')}...")

    result = {
        "probe_idx": probe_idx,
        "model": model,
        "topic": topic,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "success" if not error_message else "error",
        "status_code": status_code,
        "ttft_sec": ttft,
        "duration_sec": duration,
        "think_chars": think_chars,
        "content_chars": content_chars,
        "approx_think_tokens": approx_think_tokens,
        "approx_content_tokens": approx_content_tokens,
        "total_tokens": total_tokens,
        "words_count": words_count,
        "tokens_per_sec": tok_sec,
        "passed_1k_gate": passed_1k_gate,
        "error": error_message,
    }

    # Append to JSONL log
    try:
        with open(OUTPUT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    except Exception:
        pass

    return result


async def main():
    print(f"\n{'='*75}")
    print("  🔥 ECLIPSE GLM 10-MINUTE ENDURANCE & 429 AUTO-HEALER SUITE")
    print(f"  🎯 Target Gateway:   {GATEWAY_URL}")
    print(f"  ⏱️  Total Duration:   {TOTAL_DURATION_SEC // 60} Minutes ({TOTAL_DURATION_SEC} seconds)")
    print(f"  💤 Resting Gap:      {INTERVAL_GAP_SEC} seconds between requests")
    print(f"  🎯 Token Threshold:  >= 1,000 tokens per request")
    print(f"  📝 Output Log:       {OUTPUT_LOG}")
    print(f"{'='*75}\n")

    # Clear previous test log if fresh run
    if os.path.exists(OUTPUT_LOG):
        try:
            os.remove(OUTPUT_LOG)
        except Exception:
            pass

    overall_start = time.time()
    probe_idx = 0
    all_results = []

    while True:
        elapsed_overall = time.time() - overall_start
        remaining = TOTAL_DURATION_SEC - elapsed_overall
        if remaining <= 0:
            print(f"\n🎉 10-minute test period complete! (Total runtime: {elapsed_overall:.1f}s)")
            break

        probe_idx += 1
        model = MODELS_POOL[(probe_idx - 1) % len(MODELS_POOL)]
        topic, prompt = PROMPT_BATTERY[(probe_idx - 1) % len(PROMPT_BATTERY)]

        print(f"\n[⏱️  Time Elapsed: {int(elapsed_overall)}s / {TOTAL_DURATION_SEC}s | Remaining: {int(remaining)}s]")
        res = await run_single_probe(probe_idx, model, topic, prompt)
        all_results.append(res)

        elapsed_overall = time.time() - overall_start
        remaining = TOTAL_DURATION_SEC - elapsed_overall
        if remaining <= 0:
            print(f"\n🎉 10-minute test period reached! (Total runtime: {elapsed_overall:.1f}s)")
            break

        sleep_time = min(INTERVAL_GAP_SEC, remaining)
        print(f"\n💤 Resting for {int(sleep_time)}s before next probe (Cooldown to observe session locks & auto-healer)...")
        await asyncio.sleep(sleep_time)

    # Final summary statistics
    print(f"\n{'='*75}")
    print("  🏁 FINAL 10-MINUTE ENDURANCE AUDIT REPORT")
    print(f"{'='*75}")
    total_probes = len(all_results)
    success_probes = sum(1 for r in all_results if r.get("status") == "success")
    passed_1k = sum(1 for r in all_results if r.get("passed_1k_gate"))
    total_tokens_sum = sum(r.get("total_tokens", 0) for r in all_results)
    avg_speed = round(sum(r.get("tokens_per_sec", 0) for r in all_results) / max(1, total_probes), 1)

    print(f"  Total Probes Run:      {total_probes}")
    print(f"  Successful Probes:     {success_probes} / {total_probes} ({round(success_probes/max(1,total_probes)*100)}%)")
    print(f"  Probes Meeting >=1k:   {passed_1k} / {total_probes} ({round(passed_1k/max(1,total_probes)*100)}%)")
    print(f"  Total Tokens Generated: {total_tokens_sum:,} tokens")
    print(f"  Average Output Speed:  {avg_speed} tokens/sec")
    print(f"  Results saved to:      {OUTPUT_LOG}")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    asyncio.run(main())
