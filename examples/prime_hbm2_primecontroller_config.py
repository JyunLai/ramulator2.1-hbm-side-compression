import os
import ramulator

trace_path = os.environ.get(
    "PRIME_TRACE",
    "./examples/traces/prime_smol135m_seq128.trace",
)

num_channels = int(os.environ.get("HBM_CHANNELS", "1"))

frontend = ramulator.frontend.PrimeRequestTrace(
    clock_ratio=4,
    path=trace_path,
)

controllers = []

for _ in range(num_channels):
    dram = ramulator.dram.HBM2(
        org_preset="HBM2_2Gb",
        timing_preset="HBM2_2000Mbps",
    )

    ctrl = ramulator.controller.PrimeHBM12(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFS(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
    )

    controllers.append(ctrl)

mem = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=controllers,
    channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper(),
)

sim = ramulator.Simulation(frontend, mem)
sim.run()

stats = sim.stats


def normalize_controller_stats(ctrl_stats):
    if isinstance(ctrl_stats, list):
        return ctrl_stats

    if isinstance(ctrl_stats, dict):
        if "cycles" in ctrl_stats:
            return [ctrl_stats]

        vals = []
        for v in ctrl_stats.values():
            if isinstance(v, dict) and "cycles" in v:
                vals.append(v)
        if vals:
            return vals

    raise RuntimeError(f"Unknown controller stats format: {type(ctrl_stats)}")


if stats:
    ctrl_stats_list = normalize_controller_stats(stats["memory_system"]["controller"])

    total_reads = sum(c.get("num_read_reqs", 0) for c in ctrl_stats_list)
    total_writes = sum(c.get("num_write_reqs", 0) for c in ctrl_stats_list)

    total_read_served = sum(c.get("num_read_reqs_served", 0) for c in ctrl_stats_list)
    total_write_served = sum(c.get("num_write_reqs_served", 0) for c in ctrl_stats_list)
    total_write_coalesced = sum(c.get("num_write_reqs_coalesced", 0) for c in ctrl_stats_list)

    total_row_hits = sum(c.get("row_hits", 0) for c in ctrl_stats_list)
    total_row_misses = sum(c.get("row_misses", 0) for c in ctrl_stats_list)
    total_row_conflicts = sum(c.get("row_conflicts", 0) for c in ctrl_stats_list)

    max_cycles = max(c.get("cycles", 0) for c in ctrl_stats_list)

    weighted_read_latency = 0.0
    if total_reads > 0:
        weighted_read_latency = sum(
            c.get("avg_read_latency", 0.0) * c.get("num_read_reqs", 0)
            for c in ctrl_stats_list
        ) / total_reads

    prime_chunks = total_reads // 3
    decomp_cycles_nonoverlap = prime_chunks * 3

    print("=== PriME-like HBM2 Multi-channel PrimeRequestTrace + PrimeHBM12 ===")
    print(f"Trace path:            {trace_path}")
    print(f"HBM channels:          {num_channels}")
    print(f"Controller count:      {len(ctrl_stats_list)}")
    print(f"Controller cycles:     {max_cycles}")
    print(f"Avg read latency:      {weighted_read_latency:.1f} cycles")
    print(f"Read requests:         {total_reads}")
    print(f"Write requests:        {total_writes}")
    print(f"Read reqs served:      {total_read_served}")
    print(f"Write reqs served:     {total_write_served}")
    print(f"Write reqs coalesced:  {total_write_coalesced}")
    print(f"Row hits:              {total_row_hits}")
    print(f"Row misses:            {total_row_misses}")
    print(f"Row conflicts:         {total_row_conflicts}")
    print(f"PriME chunks:          {prime_chunks}")
    print(f"Decomp cycles raw:     {decomp_cycles_nonoverlap}")
    print(f"Total cycles upper bd: {max_cycles + decomp_cycles_nonoverlap}")