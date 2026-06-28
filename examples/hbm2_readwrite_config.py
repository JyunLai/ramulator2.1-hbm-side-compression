import ramulator

dram = ramulator.dram.HBM2(
    org_preset="HBM2_2Gb",
    timing_preset="HBM2_2000Mbps",
)

frontend = ramulator.frontend.ReadWriteTrace(
    clock_ratio=4,
    path="./examples/traces/hbm2_rw_test.trace",
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

    print("=== HBM2 ReadWriteTrace Test ===")
    print(f"Controller cycles:     {ctrl_stats['cycles']}")
    print(f"Avg read latency:      {ctrl_stats['avg_read_latency']:.1f} cycles")
    print(f"Read requests:         {ctrl_stats['num_read_reqs']}")
    print(f"Write requests:        {ctrl_stats['num_write_reqs']}")
    print(f"Row hits:              {ctrl_stats['row_hits']}")
    print(f"Row misses:            {ctrl_stats['row_misses']}")
    print(f"Row conflicts:         {ctrl_stats['row_conflicts']}")
