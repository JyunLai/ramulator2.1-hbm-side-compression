#!/usr/bin/env python3
import csv
import json
import urllib.request
from pathlib import Path

models = [
    ("Phi-4-mini", "microsoft/Phi-4-mini-instruct"),
    ("Llama-3.2-1B", "meta-llama/Llama-3.2-1B"),
    ("Llama-3.2-3B", "meta-llama/Llama-3.2-3B"),
    ("Gemma-2-2B", "google/gemma-2-2b"),
    ("SmolLM2-135M", "HuggingFaceTB/SmolLM2-135M"),
    ("SmolLM2-360M", "HuggingFaceTB/SmolLM2-360M"),
    ("SmolLM2-1.7B", "HuggingFaceTB/SmolLM2-1.7B"),
    ("Qwen2.5-0.5B", "Qwen/Qwen2.5-0.5B"),
    ("Qwen2.5-1.5B", "Qwen/Qwen2.5-1.5B"),
    ("Qwen2.5-3B", "Qwen/Qwen2.5-3B"),
]

Path("results").mkdir(exist_ok=True)
out = "results/fig8_model_configs.csv"

rows = []
for name, repo in models:
    url = f"https://huggingface.co/{repo}/resolve/main/config.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            cfg = json.loads(r.read().decode("utf-8"))

        vocab_size = cfg.get("vocab_size")
        hidden_size = cfg.get("hidden_size") or cfg.get("n_embd") or cfg.get("d_model")

        if vocab_size is None or hidden_size is None:
            raise RuntimeError(f"missing vocab_size or hidden_size in config")

        rows.append({
            "model": name,
            "repo": repo,
            "vocab_size": vocab_size,
            "hidden_dim": hidden_size,
            "status": "ok",
        })
        print(f"[OK] {name}: vocab={vocab_size}, hidden={hidden_size}")

    except Exception as e:
        rows.append({
            "model": name,
            "repo": repo,
            "vocab_size": "",
            "hidden_dim": "",
            "status": f"FAILED: {e}",
        })
        print(f"[FAILED] {name}: {e}")

with open(out, "w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=["model", "repo", "vocab_size", "hidden_dim", "status"],
    )
    w.writeheader()
    w.writerows(rows)

print(f"\nWrote {out}")
