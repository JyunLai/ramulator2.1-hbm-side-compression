import os
import ramulator

trace_path = os.environ.get(
    "PRIME_TRACE",
    "./examples/traces/prime_smol135m_seq128.trace",
)

dram = ramulator.dram.HBM2(
    org_preset="HBM2_2Gb",
    timing_preset="HBM2_2000Mbps",
)

frontend = ramulator.frontend.ReadWriteTrace(
    clock_ratio=4,
    path=trace_path,
)

ctrl = ramulator.controller.HBM12(
    dram=dram,
    scheduler=ramulator.scheduler.FRFCFS(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.PassThroughAddrMapper(),
    refresh_manager=ramulator.refresh_manager.NoRefresh(),
)

mem = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=[ctrl],
    channel_mapper=ramulator.channel_mapper.PassThroughChannelMapper(),
)

sim = ramulator.Simulation(frontend, mem)
sim.run()

stats = sim.stats

if stats:
    ctrl_stats = stats["memory_system"]["controller"]

    print("=== PriME-like HBM2 ReadWriteTrace ===")
    print(f"Trace path:            {trace_path}")
    print(f"Controller cycles:     {ctrl_stats['cycles']}")
    print(f"Avg read latency:      {ctrl_stats['avg_read_latency']:.1f} cycles")
    print(f"Read requests:         {ctrl_stats['num_read_reqs']}")
    print(f"Write requests:        {ctrl_stats['num_write_reqs']}")

    if "num_read_reqs_served" in ctrl_stats:
        print(f"Read reqs served:      {ctrl_stats['num_read_reqs_served']}")
    if "num_write_reqs_served" in ctrl_stats:
        print(f"Write reqs served:     {ctrl_stats['num_write_reqs_served']}")
    if "num_write_reqs_coalesced" in ctrl_stats:
        print(f"Write reqs coalesced:  {ctrl_stats['num_write_reqs_coalesced']}")
    print(f"Row hits:              {ctrl_stats['row_hits']}")
    print(f"Row misses:            {ctrl_stats['row_misses']}")
    print(f"Row conflicts:         {ctrl_stats['row_conflicts']}")

    # First-order decompression accounting:
    # The trace itself only models HBM reads/writes.
    # PriME XMC decompressor latency is 3 cycles per 96B chunk.
    # Since each 96B chunk creates 3 reads and 4 writes, chunks = read_reqs / 3.
    prime_chunks = ctrl_stats["num_read_reqs"] // 3
    decomp_cycles_nonoverlap = prime_chunks * 3

    print(f"PriME chunks:          {prime_chunks}")
    print(f"Decomp cycles raw:     {decomp_cycles_nonoverlap}")
    print(f"Total cycles upper bd: {ctrl_stats['cycles'] + decomp_cycles_nonoverlap}")
