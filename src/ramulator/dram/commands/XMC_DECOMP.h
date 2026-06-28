#ifndef RAMULATOR_DRAM_COMMANDS_XMC_DECOMP_H
#define RAMULATOR_DRAM_COMMANDS_XMC_DECOMP_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct XMC_DECOMP {
  // Level 4A: metadata-only pseudo command.
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_XMC_DECOMP_H
