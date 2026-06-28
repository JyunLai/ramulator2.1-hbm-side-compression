#ifndef RAMULATOR_DRAM_COMMANDS_PRIME_RD96_H
#define RAMULATOR_DRAM_COMMANDS_PRIME_RD96_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct PRIME_RD96 {
  // Level 4A: metadata-only pseudo command.
  // Do not mark as opening / closing / accessing / refreshing.
  // Do not classify as row/column bus command yet.
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_PRIME_RD96_H
