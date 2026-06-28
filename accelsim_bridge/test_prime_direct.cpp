#include <cstdlib>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "ramulator/base/config.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

using namespace Ramulator;

static void tick_system(
    IFrontEnd* frontend,
    IMemorySystem* memory_system,
    int& frontend_counter,
    int& memory_counter,
    int frontend_tick_ratio,
    int memory_tick_ratio
) {
  if (++frontend_counter >= memory_tick_ratio) {
    frontend_counter = 0;
    frontend->tick();
  }

  if (++memory_counter >= frontend_tick_ratio) {
    memory_counter = 0;
    memory_system->tick();
  }
}

static bool send_prime_subread(
    IMemorySystem* memory_system,
    int chunk_id,
    int subread_idx,
    int channel,
    int pseudochannel,
    int bankgroup,
    int even_bank,
    int row,
    int read_col_base,
    int odd_bank,
    int write_col_base,
    int& callback_count,
    unsigned long long& callback_depart
) {
  AddrVec_t av;
  av.push_back(channel);
  av.push_back(pseudochannel);
  av.push_back(bankgroup);
  av.push_back(even_bank);
  av.push_back(row);
  av.push_back(read_col_base);
  av.push_back(odd_bank);
  av.push_back(write_col_base);
  av.push_back(subread_idx);

  Request req(av, Request::Type::Prime);
  req.source_id = chunk_id;
  req.size_bytes = 32;

  req.callback = [&callback_count, &callback_depart](Request& done) {
    callback_count++;
    callback_depart = done.depart;
    std::cerr << "[test_prime_direct] callback"
              << " count=" << callback_count
              << " depart=" << done.depart
              << " source_id=" << done.source_id
              << "\n";
  };

  return memory_system->send(req);
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "Usage: " << argv[0] << " <config.yaml>\n";
    return 1;
  }

  const std::string config_path = argv[1];

  try {
    ConfigNode cfg = Config::parse_config_file(config_path);

    std::unique_ptr<IFrontEnd> frontend(Factory::create_frontend(cfg));
    std::unique_ptr<IMemorySystem> memory_system(Factory::create_memory_system(cfg));

    frontend->connect_memory_system(memory_system.get());
    memory_system->connect_frontend(frontend.get());

    const int frontend_tick_ratio = frontend->get_clock_ratio();
    const int memory_tick_ratio = memory_system->get_clock_ratio();

    int frontend_counter = memory_tick_ratio - 1;
    int memory_counter = frontend_tick_ratio - 1;

    int callback_count = 0;
    unsigned long long callback_depart = 0;

    const int chunk_id = 12345;

    // One PriME logical chunk:
    // [ch, pc, bg, even_bank, row, read_col_base, odd_bank, write_col_base, subread_idx]
    const int ch = 0;
    const int pc = 0;
    const int bg = 0;
    const int even_bank = 0;
    const int odd_bank = 1;
    const int row = 0;
    const int read_col_base = 0;
    const int write_col_base = 0;

    bool sent[3] = {false, false, false};

    unsigned long long cycle = 0;
    const unsigned long long max_cycles = 200000;

    while (cycle < max_cycles && callback_count < 1) {
      for (int i = 0; i < 3; i++) {
        if (!sent[i]) {
          bool ok = send_prime_subread(
              memory_system.get(),
              chunk_id,
              i,
              ch,
              pc,
              bg,
              even_bank,
              row,
              read_col_base,
              odd_bank,
              write_col_base,
              callback_count,
              callback_depart
          );

          if (ok) {
            sent[i] = true;
            std::cerr << "[test_prime_direct] sent subread_idx=" << i
                      << " at cycle=" << cycle << "\n";
          }
        }
      }

      tick_system(
          frontend.get(),
          memory_system.get(),
          frontend_counter,
          memory_counter,
          frontend_tick_ratio,
          memory_tick_ratio
      );

      cycle++;
    }

    std::cout << "prime_direct_test_result,"
              << "sent0=" << sent[0] << ","
              << "sent1=" << sent[1] << ","
              << "sent2=" << sent[2] << ","
              << "callback_count=" << callback_count << ","
              << "callback_depart=" << callback_depart << ","
              << "cycles=" << cycle
              << "\n";

    if (!sent[0] || !sent[1] || !sent[2]) {
      std::cerr << "ERROR: not all PrimeSubReads were accepted.\n";
      return 2;
    }

    if (callback_count != 1) {
      std::cerr << "ERROR: expected exactly one final Prime chunk callback.\n";
      return 3;
    }

    std::cerr << "[test_prime_direct] PASSED\n";
    return 0;

  } catch (const std::exception& e) {
    std::cerr << "ERROR: " << e.what() << "\n";
    return 10;
  }
}
