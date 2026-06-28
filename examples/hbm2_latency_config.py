import ramulator
from tests.utils import extract_dram_layout

# HBM2 config used as the first baseline for PriME reproduction.
# This follows Ramulator2.1's smoke-test style.

dram = ramulator.dram.HBM2(
    org_preset="HBM2_2Gb",
    timing_preset="HBM2_2000Mbps",
)

layout = extract_dram_layout(dram)

frontend = ramulator.frontend.LatencyThroughputTrace(
    clock_ratio=4,
    nop_counter=5,
    num_probe_requests=10000,
    warmup_cycles=1000,
    seed=12345,
    read_ratio=100,      # 100% reads for the first test
    stream_cls=32,
    **layout,
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
    frontend_stats = stats["frontend"]

    print("=== HBM2 Latency/Throughput Test ===")
    print(f"Controller cycles:     {ctrl_stats['cycles']}")
    print(f"Avg read latency:      {ctrl_stats['avg_read_latency']:.1f} cycles")
    print(f"Read requests:         {ctrl_stats['num_read_reqs']}")
    print(f"Write requests:        {ctrl_stats['num_write_reqs']}")
    print(f"Row hits:              {ctrl_stats['row_hits']}")
    print(f"Row misses:            {ctrl_stats['row_misses']}")
    print(f"Row conflicts:         {ctrl_stats['row_conflicts']}")

    if "avg_probe_latency" in frontend_stats:
        print(f"Frontend avg latency:  {frontend_stats['avg_probe_latency']:.1f} cycles")
