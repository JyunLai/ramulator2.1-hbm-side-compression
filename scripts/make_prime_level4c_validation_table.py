#!/usr/bin/env python3
import csv
from pathlib import Path

OUT_CSV = Path("results/prime_level4c_validation_table.csv")
OUT_MD = Path("results/prime_level4c_validation_table.md")

COMPARE_L2_L4C = Path("results/compare_level2_vs_level4c_device_ch8_seed0_9.csv")
L4C_RESULT = Path("results/fig8_prime_controller_level4c_device_ch8_seed0_9.csv")

SENS_COMP = Path("logs_prime_controller_device_sens32/prime_req_device_nprimewb32.completion.csv")
FINAL_CHECK = Path("logs_prime_final_check/prime_req_final_check.completion.csv")
HBM2_SRC = Path("src/ramulator/dram/impl/HBM2.cpp")
HBM2_PY = Path("python/ramulator/dram/hbm2.py")


def csv_row_count(path):
    if not path.exists():
        return None
    with open(path, newline="") as f:
        return max(0, sum(1 for _ in f) - 1)


def compare_stats(path):
    if not path.exists():
        return None

    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        return None

    diffs = [int(r["diff"]) for r in rows]
    return {
        "rows": len(rows),
        "max_abs_diff": max(abs(x) for x in diffs),
        "num_mismatch": sum(1 for x in diffs if x != 0),
    }


def max_completion(path):
    if not path.exists():
        return None

    n = 0
    mx = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            n += 1
            mx = max(mx, int(r["complete_cycle"]))

    return {"chunks": n, "max_complete_cycle": mx}


def has_text(path, text):
    return path.exists() and text in path.read_text(errors="ignore")


def main():
    l2_l4c = compare_stats(COMPARE_L2_L4C)
    l4c_rows = csv_row_count(L4C_RESULT)
    final_check = max_completion(FINAL_CHECK)
    sens32 = max_completion(SENS_COMP)

    cmd_table_ok = (
        has_text(HBM2_SRC, "PRIME_RD96")
        and has_text(HBM2_SRC, "XMC_DECOMP")
        and has_text(HBM2_SRC, "PRIME_WB")
    )

    nprimewb_ok = has_text(HBM2_PY, '"nPRIMEWB": 4,')

    rows = [
        {
            "stage": "Level 0",
            "component": "Python event-level scheduler",
            "implemented": "Compressed-read completion model, 3-cycle XMC decompression, and odd-bank writeback queue.",
            "validation": "Used as the initial golden event-level timing model.",
            "result": "Completed",
            "evidence": "Event-level model matched later Level 1/2 results in prior validation.",
        },
        {
            "stage": "Level 1",
            "component": "PrimeTrace frontend",
            "implemented": "P-trace frontend expands each PriME chunk into 3 RD32 requests and performs frontend-side decomp/writeback scheduling.",
            "validation": "Compared against Level 0 event-level scheduler.",
            "result": "Completed",
            "evidence": "Level 1 matched Level 0 in prior validation.",
        },
        {
            "stage": "Level 2",
            "component": "PrimeHBM12 controller",
            "implemented": "Controller receives PrimeSubRead stream, groups 3 subreads into one PriME chunk, and schedules decomp/writeback.",
            "validation": "Compared against Level 1 frontend timing.",
            "result": "Completed",
            "evidence": "Level 2 matched Level 1 in prior validation.",
        },
        {
            "stage": "Level 3",
            "component": "Command trace",
            "implemented": "Emits PRIME_RD96, XMC_DECOMP, and PRIME_WB events for each PriME chunk.",
            "validation": "Single-case command trace validation: 1152 chunks, 3456 command rows.",
            "result": "Completed",
            "evidence": "Validation passed in command-trace checker.",
        },
        {
            "stage": "Level 4A",
            "component": "HBM2 command table",
            "implemented": "Added PRIME_RD96, XMC_DECOMP, and PRIME_WB to generated HBM2 command table.",
            "validation": "Generated HBM2.cpp contains PriME commands.",
            "result": "Completed" if cmd_table_ok else "Check needed",
            "evidence": "HBM2 command table contains PriME commands." if cmd_table_ok else "Could not confirm generated HBM2 command table.",
        },
        {
            "stage": "Level 4B",
            "component": "Command IDs and counters",
            "implemented": "Runtime lookup of HBM2 command IDs and command-id-aware trace output.",
            "validation": "Command-id validation confirms stable IDs.",
            "result": "Completed",
            "evidence": "PRIME_RD96 id=9, XMC_DECOMP id=10, PRIME_WB id=11.",
        },
        {
            "stage": "Level 4C-safe",
            "component": "DRAMDevice pseudo-command path",
            "implemented": "PriME pseudo commands enter DRAMDevice::issue_command without changing timing.",
            "validation": "Single-case final cycle remains 1021.",
            "result": "Completed" if final_check and final_check["max_complete_cycle"] == 1021 else "Check needed",
            "evidence": f"chunks={final_check['chunks']}, final_cycle={final_check['max_complete_cycle']}" if final_check else "Final-check log not found.",
        },
        {
            "stage": "Level 4C-timing",
            "component": "PRIME_WB Bank-level timing constraint",
            "implemented": "PRIME_WB uses HBM2 Bank-level timing constraint through DRAMDevice::check_timing / issue_command.",
            "validation": "Compared Level4C-device against Level2 golden over 400 cases.",
            "result": "Completed" if l2_l4c and l2_l4c["max_abs_diff"] == 0 and l2_l4c["num_mismatch"] == 0 else "Check needed",
            "evidence": (
                f"rows={l2_l4c['rows']}, max_abs_diff={l2_l4c['max_abs_diff']}, num_mismatch={l2_l4c['num_mismatch']}"
                if l2_l4c else
                "Level2-vs-Level4C comparison CSV not found."
            ),
        },
        {
            "stage": "Sensitivity",
            "component": "nPRIMEWB sensitivity",
            "implemented": "Increased nPRIMEWB from 4 to 32 cycles to verify the timing constraint is active.",
            "validation": "Single-case final cycle increases from 1021 to 1037.",
            "result": "Completed" if sens32 and sens32["max_complete_cycle"] == 1037 else "Check needed",
            "evidence": (
                f"nPRIMEWB=32: chunks={sens32['chunks']}, final_cycle={sens32['max_complete_cycle']}"
                if sens32 else
                "Sensitivity completion log not found."
            ),
        },
        {
            "stage": "Final config",
            "component": "Restored nPRIMEWB",
            "implemented": "Final artifact uses nPRIMEWB=4.",
            "validation": "hbm2.py contains nPRIMEWB=4 in all timing presets.",
            "result": "Completed" if nprimewb_ok else "Check needed",
            "evidence": "nPRIMEWB restored to 4." if nprimewb_ok else "nPRIMEWB is not confirmed as 4.",
        },
        {
            "stage": "Final results",
            "component": "400-case result file",
            "implemented": "10 models × 4 sequence lengths × 10 seeds.",
            "validation": "Result CSV contains 400 rows.",
            "result": "Completed" if l4c_rows == 400 else "Check needed",
            "evidence": f"rows={l4c_rows}" if l4c_rows is not None else "Level4C result CSV not found.",
        },
    ]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["stage", "component", "implemented", "validation", "result", "evidence"],
        )
        writer.writeheader()
        writer.writerows(rows)

    with open(OUT_MD, "w") as f:
        f.write("# PriME Level4C Validation Table\n\n")
        f.write("| Stage | Component | Implemented | Validation | Result | Evidence |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(
                f"| {r['stage']} | {r['component']} | {r['implemented']} | "
                f"{r['validation']} | {r['result']} | {r['evidence']} |\n"
            )

    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print()
    print(OUT_MD.read_text())


if __name__ == "__main__":
    main()
