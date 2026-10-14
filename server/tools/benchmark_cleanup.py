#!/usr/bin/env python3
"""Compare cleanup models on real dictation cases.

    python tools/benchmark_cleanup.py qwen2.5:7b-instruct llama3.1:8b

Runs every case through each model with the production prompt (from cleanup.py),
checks the output with the production guard (cleanup_ok), and reports quality
failures plus latency. Requires Ollama running (default localhost:11434).
"""

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup import DEFAULT_CLEANUP_PROMPT, cleanup_ok  # noqa: E402

OLLAMA = os.environ.get("SCRIBE_OLLAMA", "http://localhost:11434")

# (raw transcript, what a correct cleanup must contain, must-not-contain)
CASES = [
    ("um so I was thinking uh we should launch on monday you know",
     ["thinking", "launch", "Monday"], []),
    ("are you responding to me",
     ["responding"], ["yes", "i am", "sure"]),
    ("can you send me the the report by friday",
     ["send", "report", "Friday"], []),
    ("oye necesito que prepares el informe del proyecto para el martes um y tambien recuerdame llamar al cliente",
     ["informe", "martes", "llamar", "cliente"], []),
    ("hola que tal como estas",
     ["hola"], []),
    ("the meeting with the marketing team is moved to thursday at three pm",
     ["marketing", "Thursday"], []),
    ("yeah I think we should uh probably go with the the second option",
     ["second option"], []),
    ("what time is the flight tomorrow",
     ["flight", "tomorrow"], ["it is", "sure"]),
]


def call(model: str, text: str, timeout: float = 180.0) -> tuple[str, float]:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": DEFAULT_CLEANUP_PROMPT},
                     {"role": "user", "content": text}],
        "temperature": 0.0,
        "options": {"num_predict": 500},
        "keep_alive": -1,
        "stream": False,
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())["message"]["content"].strip()
    return out, time.time() - t0


def unload_all() -> None:
    """Free VRAM: an 8 GB card cannot hold two 7-8B models at once."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
            loaded = json.loads(r.read()).get("models", [])
    except Exception:
        loaded = []
    for entry in loaded:
        name = entry.get("name") or entry.get("model")
        if not name:
            continue
        payload = json.dumps({"model": name, "keep_alive": 0}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=60).read()
            print(f"  unloaded {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  could not unload {name}: {e}")
    time.sleep(2)


def vram_bytes(model: str) -> int:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
            for entry in json.loads(r.read()).get("models", []):
                if (entry.get("name") or entry.get("model") or "").startswith(model.split(":")[0]):
                    return int(entry.get("size_vram") or 0)
    except Exception:
        pass
    return 0


def evaluate(model: str) -> dict:
    print(f"\n=== {model} ===")
    unload_all()
    print(f"  warming {model} ...")
    try:
        call(model, "ok")
    except Exception as e:  # noqa: BLE001
        print(f"  cannot load {model}: {e}")
        return {"model": model, "passed": 0, "total": len(CASES), "avg_s": 0.0,
                "failures": [(m, "load failed") for m, _, _ in CASES], "gpu": False}
    vram = vram_bytes(model)
    on_gpu = vram > 1_000_000_000
    print(f"  resident: {'GPU' if on_gpu else 'CPU'} ({vram / 1e9:.1f} GB VRAM)")
    if not on_gpu:
        print("  ! this model does not fit in VRAM alongside Whisper — numbers below are CPU")

    failures = []
    latencies = []
    for raw, must_include, must_not in CASES:
        try:
            cleaned, seconds = call(model, raw)
        except Exception as e:  # noqa: BLE001
            failures.append((raw, f"request failed: {e}"))
            print(f"  FAIL  {raw[:50]!r} -> {e}")
            continue
        latencies.append(seconds)

        ok, reason = cleanup_ok(raw, cleaned)
        low = cleaned.lower()
        missing = [w for w in must_include if w.lower() not in low]
        forbidden = [w for w in must_not if w.lower() in low]

        if not ok or missing or forbidden:
            problems = []
            if not ok:
                problems.append(f"guard: {reason}")
            if missing:
                problems.append(f"missing {missing}")
            if forbidden:
                problems.append(f"forbidden {forbidden}")
            failures.append((raw, ", ".join(problems)))
            print(f"  FAIL  {raw[:48]!r}\n        -> {cleaned[:90]!r}  [{', '.join(problems)}]")
        else:
            print(f"  ok    {raw[:48]!r} -> {cleaned[:80]!r}")

    passed = len(CASES) - len(failures)
    avg = sum(latencies) / len(latencies) if latencies else 0
    print(f"  score: {passed}/{len(CASES)} cases, avg {avg:.2f}s")
    return {"model": model, "passed": passed, "total": len(CASES),
            "avg_s": round(avg, 2), "failures": failures, "gpu": on_gpu}


def main() -> None:
    models = sys.argv[1:] or ["qwen2.5:7b-instruct", "llama3.1:8b"]
    results = [evaluate(m) for m in models]

    print("\n=== summary ===")
    for r in sorted(results, key=lambda r: (-r["passed"], r["avg_s"])):
        where = "GPU" if r.get("gpu") else "CPU"
        print(f"  {r['model']:<28} {r['passed']}/{r['total']}  avg {r['avg_s']}s  ({where})")
    best = max(results, key=lambda r: (r["passed"], -r["avg_s"]))
    print(f"\n  best: {best['model']}")


if __name__ == "__main__":
    main()
