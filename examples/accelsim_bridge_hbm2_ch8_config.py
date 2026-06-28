import os
import ramulator

num_channels = int(os.environ.get("HBM_CHANNELS", "8"))

frontend = ramulator.frontend.External(
    clock_ratio=1,
)

controllers = []

for _ in range(num_channels):
    dram = ramulator.dram.HBM2(
        org_preset="HBM2_2Gb",
        timing_preset="HBM2_2000Mbps",
    )

    ctrl = ramulator.controller.HBM12(
        dram=dram,
        scheduler=ramulator.scheduler.FRFCFS(),
        row_policy=ramulator.row_policy.Open(),
        addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        refresh_manager=ramulator.refresh_manager.NoRefresh(),
    )

    controllers.append(ctrl)

mem = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=controllers,
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
)

sim = ramulator.Simulation(frontend, mem)
sim.run()
