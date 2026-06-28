#!/usr/bin/env python3
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

GPU_LAT_CSV = Path("results/final_latency_scaling_seq_avg.csv")
MODEL_CFG_CSV = Path("results/fig8_model_configs.csv")

OUT_CSV = Path("results/final_embedding_fraction_analytical.csv")
OUT_SVG = Path("results/figE_embedding_fraction_analytical.svg")
OUT_PNG = Path("results/figE_embedding_fraction_analytical.png")

# Approximate layer counts and intermediate sizes.
# These are used only for analytical estimation, not bit-exact modeling.
MODEL_ARCH = {
    "Phi-4-mini":        {"layers": 32, "hidden_dim": 3072, "intermediate_dim": 8192},
    "Llama-3.2-1B":     {"layers": 16, "hidden_dim": 2048, "intermediate_dim": 8192},
    "Llama-3.2-3B":     {"layers": 28, "hidden_dim": 3072, "intermediate_dim": 8192},
    "Gemma-2-2B":       {"layers": 26, "hidden_dim": 2304, "intermediate_dim": 9216},
    "SmolLM2-135M":     {"layers": 30, "hidden_dim": 576,  "intermediate_dim": 1536},
    "SmolLM2-360M":     {"layers": 32, "hidden_dim": 960,  "intermediate_dim": 2560},
    "SmolLM2-1.7B":     {"layers": 24, "hidden_dim": 2048, "intermediate_dim": 8192},
    "Qwen2.5-0.5B":     {"layers": 24, "hidden_dim": 896,  "intermediate_dim": 4864},
    "Qwen2.5-1.5B":     {"layers": 28, "hidden_dim": 1536, "intermediate_dim": 8960},
    "Qwen2.5-3B":       {"layers": 36, "hidden_dim": 2048, "intermediate_dim": 11008},
}

# Sweep effective GPU TFLOPS.
# This is effective achieved throughput, not theoretical peak.
EFFECTIVE_TFLOPS = [5, 10, 20, 40, 80]


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_gpu_embedding_latency():
    rows = read_csv(GPU_LAT_CSV)
    out = {}
    for r in rows:
        seq_len = int(r["seq_len"])
        # final_latency_scaling_seq_avg.csv is sequence average.
        out[seq_len] = float(r["gpu_mean_ns"])
    return out


def transformer_flops_prefill(seq_len, layers, hidden_dim, intermediate_dim):
    """
    Rough dense-transformer prefill FLOPs.
    Per layer:
      QKV + O projection: ~8 * L * H^2
      MLP up/gate/down:  ~6 * L * H * I
      Attention score/value: ~4 * L^2 * H
    """
    L = seq_len
    H = hidden_dim
    I = intermediate_dim

    proj = 8.0 * L * H * H
    mlp = 6.0 * L * H * I
    attn = 4.0 * L * L * H

    return layers * (proj + mlp + attn)


def main():
    gpu_embed_ns_by_seq = load_gpu_embedding_latency()

    out_rows = []

    for model, arch in MODEL_ARCH.items():
        for seq_len, embed_ns in gpu_embed_ns_by_seq.items():
            flops = transformer_flops_prefill(
                seq_len,
                arch["layers"],
                arch["hidden_dim"],
                arch["intermediate_dim"],
            )

            for tflops in EFFECTIVE_TFLOPS:
                compute_ns = flops / (tflops * 1e12) * 1e9
                total_ns = embed_ns + compute_ns
                embedding_fraction = embed_ns / total_ns

                out_rows.append({
                    "model": model,
                    "seq_len": seq_len,
                    "effective_tflops": tflops,
                    "gpu_embedding_ns": embed_ns,
                    "estimated_transformer_compute_ns": compute_ns,
                    "estimated_total_ns": total_ns,
                    "embedding_fraction": embedding_fraction,
                })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model",
                "seq_len",
                "effective_tflops",
                "gpu_embedding_ns",
                "estimated_transformer_compute_ns",
                "estimated_total_ns",
                "embedding_fraction",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {OUT_CSV}")

    # Plot sequence-average embedding fraction under each effective TFLOPS.
    by_tflops_seq = defaultdict(list)
    for r in out_rows:
        key = (int(r["effective_tflops"]), int(r["seq_len"]))
        by_tflops_seq[key].append(float(r["embedding_fraction"]) * 100.0)

    seq_lens = sorted(gpu_embed_ns_by_seq.keys())
    x = np.arange(len(seq_lens))

    fig, ax = plt.subplots(figsize=(9.0, 5.0))

    for tflops in EFFECTIVE_TFLOPS:
        ys = []
        for L in seq_lens:
            vals = by_tflops_seq[(tflops, L)]
            ys.append(sum(vals) / len(vals))
        ax.plot(x, ys, marker="o", label=f"{tflops} effective TFLOPS")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Estimated embedding fraction of total latency (%)")
    ax.set_title("Figure E: Analytical embedding fraction estimate")
    ax.set_xticks(x)
    ax.set_xticklabels([str(L) for L in seq_lens])
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")

    # Print compact summary.
    print()
    print("Sequence-average embedding fraction (%):")
    print("effective_tflops,seq_len,embedding_fraction_percent")
    for tflops in EFFECTIVE_TFLOPS:
        for L in seq_lens:
            vals = by_tflops_seq[(tflops, L)]
            print(f"{tflops},{L},{sum(vals)/len(vals):.4f}")


if __name__ == "__main__":
    main()
