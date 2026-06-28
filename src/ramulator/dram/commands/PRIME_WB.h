#ifndef RAMULATOR_DRAM_COMMANDS_PRIME_WB_H
#define RAMULATOR_DRAM_COMMANDS_PRIME_WB_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct PRIME_WB {
  // Level 4A: metadata-only pseudo command.
  // Later Level 4C can decide whether it should be timing-constrained.
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_PRIME_WB_H
