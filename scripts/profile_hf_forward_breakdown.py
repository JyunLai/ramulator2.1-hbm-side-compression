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


class ModuleTimer:
    def __init__(self, module):
        self.module = module
        self.pairs = []
        self.h1 = None
        self.h2 = None

    def clear(self):
        self.pairs.clear()

    def pre_hook(self, module, inputs):
        ev = torch.cuda.Event(enable_timing=True)
        ev.record()
        self.pairs.append({"start": ev, "end": None})

    def post_hook(self, module, inputs, output):
        ev = torch.cuda.Event(enable_timing=True)
        ev.record()
        if not self.pairs:
            raise RuntimeError("post_hook without pre_hook")
        self.pairs[-1]["end"] = ev

    def install(self):
        self.h1 = self.module.register_forward_pre_hook(self.pre_hook)
        self.h2 = self.module.register_forward_hook(self.post_hook)

    def remove(self):
        if self.h1 is not None:
            self.h1.remove()
        if self.h2 is not None:
            self.h2.remove()

    def elapsed_ms(self):
        total = 0.0
        for p in self.pairs:
            if p["end"] is None:
                raise RuntimeError("event pair missing end")
            total += p["start"].elapsed_time(p["end"])
        return total


def get_lm_head(model):
    if hasattr(model, "get_output_embeddings"):
        out = model.get_output_embeddings()
        if out is not None:
            return out
    if hasattr(model, "lm_head"):
        return model.lm_head
    return None


def measure_one(model, input_ids, attention_mask, warmup, iters):
    emb = model.get_input_embeddings()
    lm_head = get_lm_head(model)

    if emb is None:
        raise RuntimeError("input embedding module not found")

    emb_timer = ModuleTimer(emb)
    lm_head_timer = ModuleTimer(lm_head) if lm_head is not None else None

    emb_timer.install()
    if lm_head_timer is not None:
        lm_head_timer.install()

    try:
        with torch.inference_mode():
            for _ in range(warmup):
                _ = call_model(model, input_ids, attention_mask)
        torch.cuda.synchronize()

        full_list = []
        emb_list = []
        lm_head_list = []

        with torch.inference_mode():
            for _ in range(iters):
                emb_timer.clear()
                if lm_head_timer is not None:
                    lm_head_timer.clear()

                full_start = torch.cuda.Event(enable_timing=True)
                full_end = torch.cuda.Event(enable_timing=True)

                full_start.record()
                _ = call_model(model, input_ids, attention_mask)
                full_end.record()

                torch.cuda.synchronize()

                full_ms = full_start.elapsed_time(full_end)
                emb_ms = emb_timer.elapsed_ms()
                lm_ms = lm_head_timer.elapsed_ms() if lm_head_timer is not None else 0.0

                full_list.append(full_ms)
                emb_list.append(emb_ms)
                lm_head_list.append(lm_ms)

        full_avg = sum(full_list) / len(full_list)
        emb_avg = sum(emb_list) / len(emb_list)
        lm_avg = sum(lm_head_list) / len(lm_head_list)

        rest_avg = max(0.0, full_avg - emb_avg - lm_avg)

        return {
            "full_forward_ms": full_avg,
            "embedding_ms": emb_avg,
            "lm_head_ms": lm_avg,
            "rest_ms": rest_avg,
            "embedding_fraction": emb_avg / full_avg if full_avg > 0 else 0.0,
            "lm_head_fraction": lm_avg / full_avg if full_avg > 0 else 0.0,
            "rest_fraction": rest_avg / full_avg if full_avg > 0 else 0.0,
            "has_lm_head": lm_head is not None,
        }

    finally:
        emb_timer.remove()
        if lm_head_timer is not None:
            lm_head_timer.remove()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--seq-lens", nargs="*", type=int, default=[128, 512, 1024, 2048])
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16")
    parser.add_argument("--out", default="results/hf_forward_breakdown_profile.csv")
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
        "lm_head_ms",
        "rest_ms",
        "embedding_fraction_percent",
        "lm_head_fraction_percent",
        "rest_fraction_percent",
        "has_lm_head",
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

                    m = measure_one(
                        model=model,
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        warmup=args.warmup,
                        iters=args.iters,
                    )

                    rows.append({
                        "model": short_name(repo),
                        "repo": repo,
                        "seq_len": seq_len,
                        "batch_size": args.batch_size,
                        "dtype": args.dtype,
                        "vocab_size": vocab_size,
                        "hidden_size": hidden_size,
                        "num_hidden_layers": num_layers,
                        "full_forward_ms": m["full_forward_ms"],
                        "embedding_ms": m["embedding_ms"],
                        "lm_head_ms": m["lm_head_ms"],
                        "rest_ms": m["rest_ms"],
                        "embedding_fraction_percent": m["embedding_fraction"] * 100.0,
                        "lm_head_fraction_percent": m["lm_head_fraction"] * 100.0,
                        "rest_fraction_percent": m["rest_fraction"] * 100.0,
                        "has_lm_head": m["has_lm_head"],
                        "status": "ok",
                        "error": "",
                    })

                    print(
                        f"  full={m['full_forward_ms']:.4f} ms, "
                        f"emb={m['embedding_ms']:.6f} ms "
                        f"({m['embedding_fraction']*100:.4f}%), "
                        f"lm_head={m['lm_head_ms']:.6f} ms "
                        f"({m['lm_head_fraction']*100:.4f}%), "
                        f"rest={m['rest_ms']:.6f} ms "
                        f"({m['rest_fraction']*100:.4f}%)",
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
                        "lm_head_ms": "",
                        "rest_ms": "",
                        "embedding_fraction_percent": "",
                        "lm_head_fraction_percent": "",
                        "rest_fraction_percent": "",
                        "has_lm_head": "",
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
                "lm_head_ms": "",
                "rest_ms": "",
                "embedding_fraction_percent": "",
                "lm_head_fraction_percent": "",
                "rest_fraction_percent": "",
                "has_lm_head": "",
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
