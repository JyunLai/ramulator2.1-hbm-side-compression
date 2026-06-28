#!/usr/bin/env python3
import argparse
import csv
import os
from pathlib import Path

import torch
from transformers import AutoConfig, AutoModelForCausalLM


DEFAULT_MODELS = [
    "HuggingFaceTB/SmolLM2-135M",
    "HuggingFaceTB/SmolLM2-360M",
    "Qwen/Qwen2.5-0.5B",
]


def short_name(repo):
    return repo.split("/")[-1]


def call_model(model, input_ids, attention_mask):
    try:
        return model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            use_cache=False,
        )
    except TypeError:
        return model(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )


def measure_one(model, input_ids, attention_mask, warmup, iters):
    emb = model.get_input_embeddings()
    if emb is None:
        raise RuntimeError("model.get_input_embeddings() returned None")

    current_pairs = []

    def pre_hook(module, inputs):
        ev = torch.cuda.Event(enable_timing=True)
        ev.record()
        current_pairs.append({"start": ev, "end": None})

    def post_hook(module, inputs, output):
        ev = torch.cuda.Event(enable_timing=True)
        ev.record()
        if not current_pairs:
            raise RuntimeError("embedding post_hook without pre_hook")
        current_pairs[-1]["end"] = ev

    h1 = emb.register_forward_pre_hook(pre_hook)
    h2 = emb.register_forward_hook(post_hook)

    try:
        # Warmup
        with torch.inference_mode():
            for _ in range(warmup):
                _ = call_model(model, input_ids, attention_mask)
        torch.cuda.synchronize()

        full_ms_list = []
        emb_ms_list = []

        with torch.inference_mode():
            for _ in range(iters):
                current_pairs.clear()

                full_start = torch.cuda.Event(enable_timing=True)
                full_end = torch.cuda.Event(enable_timing=True)

                full_start.record()
                _ = call_model(model, input_ids, attention_mask)
                full_end.record()

                torch.cuda.synchronize()

                full_ms = full_start.elapsed_time(full_end)

                emb_ms = 0.0
                for p in current_pairs:
                    if p["end"] is None:
                        raise RuntimeError("embedding event pair missing end event")
                    emb_ms += p["start"].elapsed_time(p["end"])

                full_ms_list.append(full_ms)
                emb_ms_list.append(emb_ms)

        full_avg = sum(full_ms_list) / len(full_ms_list)
        emb_avg = sum(emb_ms_list) / len(emb_ms_list)
        frac = emb_avg / full_avg if full_avg > 0 else 0.0

        return full_avg, emb_avg, frac

    finally:
        h1.remove()
        h2.remove()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--seq-lens", nargs="*", type=int, default=[128, 512, 1024, 2048])
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16")
    parser.add_argument("--out", default="results/hf_embedding_fraction_profile.csv")
    parser.add_argument("--cache-dir", default=os.path.expanduser("~/prime-repro/hf_cache"))
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("ERROR: CUDA is not available")

    if args.dtype == "fp16":
        dtype = torch.float16
    elif args.dtype == "bf16":
        dtype = torch.bfloat16
    else:
        dtype = torch.float32

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "model",
        "repo",
        "seq_len",
        "batch_size",
        "dtype",
        "vocab_size",
        "hidden_size",
        "num_hidden_layers",
        "full_forward_ms",
        "embedding_ms",
        "embedding_fraction",
        "embedding_fraction_percent",
        "status",
        "error",
    ]

    rows = []

    for repo in args.models:
        print(f"\n=== Loading {repo} ===", flush=True)

        try:
            cfg = AutoConfig.from_pretrained(repo, cache_dir=args.cache_dir)
            model = AutoModelForCausalLM.from_pretrained(
                repo,
                cache_dir=args.cache_dir,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
            )
            model.eval()
            model.to("cuda")

            vocab_size = int(getattr(cfg, "vocab_size", 0))
            hidden_size = int(getattr(cfg, "hidden_size", 0))
            num_layers = int(getattr(cfg, "num_hidden_layers", 0))

            for seq_len in args.seq_lens:
                print(f"Profiling {short_name(repo)} seq={seq_len}", flush=True)

                try:
                    torch.cuda.empty_cache()

                    input_ids = torch.randint(
                        low=0,
                        high=vocab_size,
                        size=(args.batch_size, seq_len),
                        device="cuda",
                        dtype=torch.long,
                    )
                    attention_mask = torch.ones_like(input_ids, device="cuda")

                    full_ms, emb_ms, frac = measure_one(
                        model=model,
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        warmup=args.warmup,
                        iters=args.iters,
                    )

                    row = {
                        "model": short_name(repo),
                        "repo": repo,
                        "seq_len": seq_len,
                        "batch_size": args.batch_size,
                        "dtype": args.dtype,
                        "vocab_size": vocab_size,
                        "hidden_size": hidden_size,
                        "num_hidden_layers": num_layers,
                        "full_forward_ms": full_ms,
                        "embedding_ms": emb_ms,
                        "embedding_fraction": frac,
                        "embedding_fraction_percent": frac * 100.0,
                        "status": "ok",
                        "error": "",
                    }
                    rows.append(row)

                    print(
                        f"  full={full_ms:.4f} ms, "
                        f"embedding={emb_ms:.6f} ms, "
                        f"fraction={frac*100:.6f}%",
                        flush=True,
                    )

                except RuntimeError as e:
                    err = str(e).replace("\n", " ")[:300]
                    print(f"  ERROR seq={seq_len}: {err}", flush=True)
                    rows.append({
                        "model": short_name(repo),
                        "repo": repo,
                        "seq_len": seq_len,
                        "batch_size": args.batch_size,
                        "dtype": args.dtype,
                        "vocab_size": vocab_size,
                        "hidden_size": hidden_size,
                        "num_hidden_layers": num_layers,
                        "full_forward_ms": "",
                        "embedding_ms": "",
                        "embedding_fraction": "",
                        "embedding_fraction_percent": "",
                        "status": "error",
                        "error": err,
                    })
                    torch.cuda.empty_cache()

            del model
            torch.cuda.empty_cache()

        except Exception as e:
            err = str(e).replace("\n", " ")[:300]
            print(f"ERROR loading {repo}: {err}", flush=True)
            rows.append({
                "model": short_name(repo),
                "repo": repo,
                "seq_len": "",
                "batch_size": args.batch_size,
                "dtype": args.dtype,
                "vocab_size": "",
                "hidden_size": "",
                "num_hidden_layers": "",
                "full_forward_ms": "",
                "embedding_ms": "",
                "embedding_fraction": "",
                "embedding_fraction_percent": "",
                "status": "load_error",
                "error": err,
            })

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
