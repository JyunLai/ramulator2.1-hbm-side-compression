#include "prime_ramulator_bridge.h"

#include <array>
#include <cstdlib>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "ramulator/base/config.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

using namespace Ramulator;

struct PrimeChunkState {
  bool issued = false;
  bool ready = false;
  int remaining_compressed_reads = 0;
  unsigned long long ready_cycle = 0;
  std::vector<int> waiting_user_source_ids;
};

struct PrimeInternalRetry {
  unsigned long long addr = 0;
  unsigned long long chunk_key = 0;
};

struct DirectPrimeChunkState {
  bool issued = false;
  bool ready = false;
  int ramulator_chunk_id = -1;
  std::array<bool, 3> subread_sent{{false, false, false}};
  std::vector<int> waiting_user_source_ids;
};

struct DirectPrimeRetry {
  unsigned long long chunk_key = 0;
  int subread_idx = 0;
};

struct DirectPrimeMeta {
  int channel = 0;
  int pseudochannel = 0;
  int bankgroup = 0;
  int even_bank = 0;
  int odd_bank = 1;
  int row = 0;
  int read_col_base = 0;
  int write_col_base = 0;
};

struct PrimeRamulatorBridge {
  std::unique_ptr<IFrontEnd> frontend;
  std::unique_ptr<IMemorySystem> memory_system;

  std::deque<int> completed_source_ids;

  unsigned long long cycle = 0;
  unsigned long long sent = 0;       // original user-level requests accepted
  unsigned long long completed = 0;  // original user-level requests completed

  unsigned long long prime_physical_reads_sent = 0;
  unsigned long long prime_chunks_issued = 0;
  unsigned long long prime_chunks_completed = 0;

  unsigned long long direct_prime_subreads_sent = 0;
  unsigned long long direct_prime_chunks_issued = 0;
  unsigned long long direct_prime_chunks_completed = 0;

  unsigned long long hbm_comp_physical_reads_sent = 0;
  unsigned long long hbm_comp_chunks_issued = 0;
  unsigned long long hbm_comp_chunks_completed = 0;

  int frontend_tick_ratio = 1;
  int memory_tick_ratio = 1;
  int frontend_counter = 0;
  int memory_counter = 0;

  bool prime_mode = false;
  bool prime_direct_mode = false;
  bool hbm_side_comp_mode = false;

  int prime_chunk_bytes = 128;       // two 64B uncompressed blocks
  int prime_compressed_bytes = 96;   // two 48B compressed blocks
  int prime_tx_bytes = 32;           // HBM2 transaction size
  int prime_decomp_latency = 3;
  int prime_wb_latency = 4;

  int prime_direct_channels = 8;
  int next_direct_prime_chunk_id = 0;

  int hbm_comp_chunk_bytes = 128;       // host-visible logical block
  int hbm_comp_compressed_bytes = 96;   // compressed physical block
  int hbm_comp_tx_bytes = 32;           // HBM2 transaction size
  int hbm_comp_decomp_latency = 3;      // logic-die decompression latency
  bool hbm_comp_debug_printed = false;
  bool hbm_comp_padded_mapping = false;
  int hbm_comp_mapping_latency = 0;     // V1 fixed mapping, default zero

  std::unordered_map<unsigned long long, PrimeChunkState> prime_chunks;
  std::deque<PrimeInternalRetry> prime_retry_q;

  std::unordered_map<unsigned long long, DirectPrimeChunkState> direct_prime_chunks;
  std::deque<DirectPrimeRetry> direct_prime_retry_q;

  std::unordered_map<unsigned long long, PrimeChunkState> hbm_comp_chunks;
  std::deque<PrimeInternalRetry> hbm_comp_retry_q;

  // HBM-side Compression statistics.
  unsigned long long hbm_comp_parent_reads = 0;
  unsigned long long hbm_comp_parent_read_bytes = 0;
  std::unordered_map<unsigned long long, unsigned long long> hbm_comp_sector_mask;
};

static PrimeRamulatorBridge* g_hbm_comp_last_bridge = nullptr;
static bool g_hbm_comp_atexit_registered = false;

static unsigned int hbm_comp_popcount64(unsigned long long x) {
  unsigned int c = 0;
  while (x) {
    c += static_cast<unsigned int>(x & 1ULL);
    x >>= 1;
  }
  return c;
}

static void hbm_comp_print_summary(PrimeRamulatorBridge* h, const char* tag) {
  if (!h || !h->hbm_side_comp_mode) return;

  unsigned long long unique_chunks =
      static_cast<unsigned long long>(h->hbm_comp_sector_mask.size());

  unsigned long long sectors_touched = 0;
  for (const auto& kv : h->hbm_comp_sector_mask) {
    sectors_touched += hbm_comp_popcount64(kv.second);
  }

  unsigned long long tx_bytes =
      static_cast<unsigned long long>(h->hbm_comp_tx_bytes > 0 ? h->hbm_comp_tx_bytes : 32);

  unsigned long long chunk_bytes =
      static_cast<unsigned long long>(h->hbm_comp_chunk_bytes > 0 ? h->hbm_comp_chunk_bytes : 128);

  unsigned long long compressed_bytes =
      static_cast<unsigned long long>(h->hbm_comp_compressed_bytes > 0 ? h->hbm_comp_compressed_bytes : 96);

  unsigned long long sectors_per_chunk =
      (chunk_bytes + tx_bytes - 1) / tx_bytes;

  unsigned long long physical_read_bytes =
      h->hbm_comp_physical_reads_sent * tx_bytes;

  unsigned long long compressed_chunk_bytes_issued =
      h->hbm_comp_chunks_issued * compressed_bytes;

  unsigned long long uncompressed_chunk_bytes_touched =
      unique_chunks * chunk_bytes;

  double avg_parent_reads_per_chunk =
      unique_chunks ? static_cast<double>(h->hbm_comp_parent_reads) / unique_chunks : 0.0;

  double avg_sectors_per_chunk =
      unique_chunks ? static_cast<double>(sectors_touched) / unique_chunks : 0.0;

  double sector_util =
      (unique_chunks && sectors_per_chunk)
          ? static_cast<double>(sectors_touched) /
                static_cast<double>(unique_chunks * sectors_per_chunk)
          : 0.0;

  double physical_vs_parent_byte_ratio =
      h->hbm_comp_parent_read_bytes
          ? static_cast<double>(physical_read_bytes) /
                static_cast<double>(h->hbm_comp_parent_read_bytes)
          : 0.0;

  double compressed_vs_uncompressed_chunk_ratio =
      uncompressed_chunk_bytes_touched
          ? static_cast<double>(compressed_chunk_bytes_issued) /
                static_cast<double>(uncompressed_chunk_bytes_touched)
          : 0.0;

  std::cerr << "[hbm_side_comp_summary]"
            << " tag=" << tag
            << " hbm_side_comp_mode=" << (h->hbm_side_comp_mode ? 1 : 0)
            << " parent_reads=" << h->hbm_comp_parent_reads
            << " parent_read_bytes_est=" << h->hbm_comp_parent_read_bytes
            << " unique_chunks_touched=" << unique_chunks
            << " chunks_issued=" << h->hbm_comp_chunks_issued
            << " chunks_completed=" << h->hbm_comp_chunks_completed
            << " physical_reads_sent=" << h->hbm_comp_physical_reads_sent
            << " physical_read_bytes=" << physical_read_bytes
            << " compressed_chunk_bytes_issued=" << compressed_chunk_bytes_issued
            << " uncompressed_chunk_bytes_touched=" << uncompressed_chunk_bytes_touched
            << " sectors_touched=" << sectors_touched
            << " sectors_per_chunk=" << sectors_per_chunk
            << " avg_parent_reads_per_chunk=" << avg_parent_reads_per_chunk
            << " avg_sectors_per_chunk=" << avg_sectors_per_chunk
            << " sector_util=" << sector_util
            << " physical_vs_parent_byte_ratio=" << physical_vs_parent_byte_ratio
            << " compressed_vs_uncompressed_chunk_ratio=" << compressed_vs_uncompressed_chunk_ratio
            << "\n";
}

static void hbm_comp_atexit_dump() {
  hbm_comp_print_summary(g_hbm_comp_last_bridge, "atexit");
}


static bool env_enabled(const char* name) {
  const char* v = std::getenv(name);
  return v && v[0] && v[0] != '0';
}

static int env_int(const char* name, int fallback) {
  const char* v = std::getenv(name);
  if (!v || !v[0]) return fallback;
  int x = std::atoi(v);
  return x > 0 ? x : fallback;
}

static int env_int_nonnegative(const char* name, int fallback) {
  const char* v = std::getenv(name);
  if (!v || !v[0]) return fallback;
  int x = std::atoi(v);
  return x >= 0 ? x : fallback;
}

static unsigned long long prime_chunk_key_of(PrimeRamulatorBridge* h, unsigned long long addr) {
  return addr / static_cast<unsigned long long>(h->prime_chunk_bytes);
}

static unsigned long long prime_compressed_base_of(PrimeRamulatorBridge* h, unsigned long long chunk_key) {
  return chunk_key * static_cast<unsigned long long>(h->prime_compressed_bytes);
}

static unsigned long long hbm_comp_chunk_key_of(PrimeRamulatorBridge* h, unsigned long long addr) {
  return addr / static_cast<unsigned long long>(h->hbm_comp_chunk_bytes);
}

static unsigned long long hbm_comp_compressed_base_of(
    PrimeRamulatorBridge* h, unsigned long long chunk_key) {
  unsigned long long unit =
      h->hbm_comp_padded_mapping
          ? static_cast<unsigned long long>(h->hbm_comp_chunk_bytes)
          : static_cast<unsigned long long>(h->hbm_comp_compressed_bytes);
  return chunk_key * unit;
}

static DirectPrimeMeta make_direct_prime_meta(PrimeRamulatorBridge* h, unsigned long long chunk_key) {
  DirectPrimeMeta m;

  unsigned long long x = chunk_key;

  m.channel = static_cast<int>(x % static_cast<unsigned long long>(h->prime_direct_channels));
  x /= static_cast<unsigned long long>(h->prime_direct_channels);

  m.pseudochannel = static_cast<int>(x % 2);
  x /= 2;

  m.bankgroup = static_cast<int>(x % 4);
  x /= 4;

  const int bank_pair = static_cast<int>(x % 2);
  x /= 2;

  m.even_bank = bank_pair * 2;
  m.odd_bank = m.even_bank + 1;

  // 128 HBM columns per row. PriME compressed chunk uses 3 consecutive columns.
  const int slots_per_row = 42;  // floor(128 / 3)
  const int slot = static_cast<int>(x % slots_per_row);
  x /= slots_per_row;

  m.read_col_base = slot * 3;
  m.write_col_base = m.read_col_base;

  m.row = static_cast<int>(x & 0x7fffffffULL);

  return m;
}

static bool issue_prime_internal_read(
    PrimeRamulatorBridge* h,
    unsigned long long compressed_addr,
    unsigned long long chunk_key
) {
  auto callback = [h, chunk_key](Request& req) {
    (void)req;

    auto it = h->prime_chunks.find(chunk_key);
    if (it == h->prime_chunks.end()) return;

    if (it->second.remaining_compressed_reads > 0) {
      it->second.remaining_compressed_reads--;
    }

    if (it->second.remaining_compressed_reads == 0 && !it->second.ready) {
      it->second.ready_cycle =
          h->cycle +
          static_cast<unsigned long long>(h->prime_decomp_latency) +
          static_cast<unsigned long long>(h->prime_wb_latency);
    }
  };

  bool ok = h->frontend->receive_external_requests(
      Request::Type::Read,
      static_cast<Addr_t>(compressed_addr),
      0,
      callback,
      h->prime_tx_bytes
  );

  if (ok) {
    h->prime_physical_reads_sent++;
    return true;
  }

  return false;
}

static void drain_prime_internal_retry(PrimeRamulatorBridge* h) {
  while (!h->prime_retry_q.empty()) {
    PrimeInternalRetry r = h->prime_retry_q.front();

    bool ok = issue_prime_internal_read(h, r.addr, r.chunk_key);
    if (!ok) break;

    h->prime_retry_q.pop_front();
  }
}

static void complete_ready_prime_chunks(PrimeRamulatorBridge* h) {
  for (auto& kv : h->prime_chunks) {
    PrimeChunkState& st = kv.second;

    if (!st.issued) continue;
    if (st.ready) continue;
    if (st.remaining_compressed_reads != 0) continue;
    if (h->cycle < st.ready_cycle) continue;

    st.ready = true;
    h->prime_chunks_completed++;

    for (int user_sid : st.waiting_user_source_ids) {
      h->completed_source_ids.push_back(user_sid);
      h->completed++;
    }
    st.waiting_user_source_ids.clear();
  }
}

static bool send_prime_parent_read(
    PrimeRamulatorBridge* h,
    unsigned long long addr,
    int user_source_id
) {
  unsigned long long chunk_key = prime_chunk_key_of(h, addr);
  PrimeChunkState& st = h->prime_chunks[chunk_key];

  h->sent++;

  if (st.ready) {
    h->completed_source_ids.push_back(user_source_id);
    h->completed++;
    return true;
  }

  st.waiting_user_source_ids.push_back(user_source_id);

  if (!st.issued) {
    st.issued = true;
    st.remaining_compressed_reads =
        (h->prime_compressed_bytes + h->prime_tx_bytes - 1) / h->prime_tx_bytes;
    h->prime_chunks_issued++;

    unsigned long long cbase = prime_compressed_base_of(h, chunk_key);

    for (int i = 0; i < st.remaining_compressed_reads; i++) {
      unsigned long long caddr =
          cbase + static_cast<unsigned long long>(i * h->prime_tx_bytes);

      bool ok = issue_prime_internal_read(h, caddr, chunk_key);
      if (!ok) {
        h->prime_retry_q.push_back({caddr, chunk_key});
      }
    }
  }

  return true;
}


static bool issue_hbm_comp_internal_read(
    PrimeRamulatorBridge* h,
    unsigned long long compressed_addr,
    unsigned long long chunk_key
) {
  auto callback = [h, chunk_key](Request& req) {
    (void)req;

    auto it = h->hbm_comp_chunks.find(chunk_key);
    if (it == h->hbm_comp_chunks.end()) return;

    if (it->second.remaining_compressed_reads > 0) {
      it->second.remaining_compressed_reads--;
    }

    if (it->second.remaining_compressed_reads == 0 && !it->second.ready) {
      it->second.ready_cycle =
          h->cycle +
          static_cast<unsigned long long>(h->hbm_comp_mapping_latency) +
          static_cast<unsigned long long>(h->hbm_comp_decomp_latency);
    }
  };

  bool ok = h->frontend->receive_external_requests(
      Request::Type::Read,
      static_cast<Addr_t>(compressed_addr),
      0,
      callback,
      h->hbm_comp_tx_bytes
  );

  if (ok) {
    h->hbm_comp_physical_reads_sent++;
    return true;
  }

  return false;
}

static void drain_hbm_comp_internal_retry(PrimeRamulatorBridge* h) {
  while (!h->hbm_comp_retry_q.empty()) {
    PrimeInternalRetry r = h->hbm_comp_retry_q.front();

    bool ok = issue_hbm_comp_internal_read(h, r.addr, r.chunk_key);
    if (!ok) break;

    h->hbm_comp_retry_q.pop_front();
  }
}

static void complete_ready_hbm_comp_chunks(PrimeRamulatorBridge* h) {
  for (auto& kv : h->hbm_comp_chunks) {
    PrimeChunkState& st = kv.second;

    if (!st.issued) continue;
    if (st.ready) continue;
    if (st.remaining_compressed_reads != 0) continue;
    if (h->cycle < st.ready_cycle) continue;

    st.ready = true;
    h->hbm_comp_chunks_completed++;

    for (int user_sid : st.waiting_user_source_ids) {
      h->completed_source_ids.push_back(user_sid);
      h->completed++;
    }
    st.waiting_user_source_ids.clear();
  }
}

static bool send_hbm_comp_parent_read(
    PrimeRamulatorBridge* h,
    unsigned long long addr,
    int user_source_id
) {
  unsigned long long chunk_key = hbm_comp_chunk_key_of(h, addr);
  PrimeChunkState& st = h->hbm_comp_chunks[chunk_key];

  h->hbm_comp_parent_reads++;
  h->hbm_comp_parent_read_bytes +=
      static_cast<unsigned long long>(h->hbm_comp_tx_bytes > 0 ? h->hbm_comp_tx_bytes : 32);

  unsigned long long sector_idx = 0;
  if (h->hbm_comp_tx_bytes > 0 && h->hbm_comp_chunk_bytes > 0) {
    sector_idx =
        (addr % static_cast<unsigned long long>(h->hbm_comp_chunk_bytes)) /
        static_cast<unsigned long long>(h->hbm_comp_tx_bytes);
  }
  if (sector_idx < 64) {
    h->hbm_comp_sector_mask[chunk_key] |= (1ULL << sector_idx);
  }

  if (!h->hbm_comp_debug_printed) {
    h->hbm_comp_debug_printed = true;
    std::cerr << "[hbm_side_comp_first_read]"
              << " addr=" << addr
              << " chunk_key=" << chunk_key
              << " compressed_base=" << hbm_comp_compressed_base_of(h, chunk_key)
              << " logical_chunk_bytes=" << h->hbm_comp_chunk_bytes
              << " compressed_bytes=" << h->hbm_comp_compressed_bytes
              << " tx_bytes=" << h->hbm_comp_tx_bytes
              << "\n";
  }

  h->sent++;

  if (st.ready) {
    h->completed_source_ids.push_back(user_source_id);
    h->completed++;
    return true;
  }

  st.waiting_user_source_ids.push_back(user_source_id);

  if (!st.issued) {
    st.issued = true;
    st.remaining_compressed_reads =
        (h->hbm_comp_compressed_bytes + h->hbm_comp_tx_bytes - 1) /
        h->hbm_comp_tx_bytes;
    h->hbm_comp_chunks_issued++;

    unsigned long long cbase = hbm_comp_compressed_base_of(h, chunk_key);

    for (int i = 0; i < st.remaining_compressed_reads; i++) {
      unsigned long long caddr =
          cbase + static_cast<unsigned long long>(i * h->hbm_comp_tx_bytes);

      bool ok = issue_hbm_comp_internal_read(h, caddr, chunk_key);
      if (!ok) {
        h->hbm_comp_retry_q.push_back({caddr, chunk_key});
      }
    }
  }

  return true;
}

static bool issue_direct_prime_subread(
    PrimeRamulatorBridge* h,
    unsigned long long chunk_key,
    int subread_idx
) {
  auto it = h->direct_prime_chunks.find(chunk_key);
  if (it == h->direct_prime_chunks.end()) return false;

  DirectPrimeChunkState& st = it->second;

  if (st.ready) return true;
  if (subread_idx < 0 || subread_idx >= 3) return false;
  if (st.subread_sent[subread_idx]) return true;

  DirectPrimeMeta m = make_direct_prime_meta(h, chunk_key);

  AddrVec_t av;
  av.push_back(m.channel);
  av.push_back(m.pseudochannel);
  av.push_back(m.bankgroup);
  av.push_back(m.even_bank);
  av.push_back(m.row);
  av.push_back(m.read_col_base);
  av.push_back(m.odd_bank);
  av.push_back(m.write_col_base);
  av.push_back(subread_idx);

  Request req(av, Request::Type::Prime);
  req.source_id = st.ramulator_chunk_id;
  req.size_bytes = h->prime_tx_bytes;

  req.callback = [h, chunk_key](Request& done) {
    (void)done;

    auto it2 = h->direct_prime_chunks.find(chunk_key);
    if (it2 == h->direct_prime_chunks.end()) return;

    DirectPrimeChunkState& dst = it2->second;
    if (dst.ready) return;

    dst.ready = true;
    h->direct_prime_chunks_completed++;

    for (int user_sid : dst.waiting_user_source_ids) {
      h->completed_source_ids.push_back(user_sid);
      h->completed++;
    }
    dst.waiting_user_source_ids.clear();
  };

  bool ok = h->memory_system->send(req);
  if (!ok) {
    return false;
  }

  st.subread_sent[subread_idx] = true;
  h->direct_prime_subreads_sent++;
  return true;
}

static void drain_direct_prime_retry(PrimeRamulatorBridge* h) {
  while (!h->direct_prime_retry_q.empty()) {
    DirectPrimeRetry r = h->direct_prime_retry_q.front();

    bool ok = issue_direct_prime_subread(h, r.chunk_key, r.subread_idx);
    if (!ok) break;

    h->direct_prime_retry_q.pop_front();
  }
}

static bool send_direct_prime_parent_read(
    PrimeRamulatorBridge* h,
    unsigned long long addr,
    int user_source_id
) {
  const unsigned long long chunk_key = prime_chunk_key_of(h, addr);

  DirectPrimeChunkState& st = h->direct_prime_chunks[chunk_key];

  h->sent++;

  if (st.ready) {
    h->completed_source_ids.push_back(user_source_id);
    h->completed++;
    return true;
  }

  st.waiting_user_source_ids.push_back(user_source_id);

  if (!st.issued) {
    st.issued = true;
    st.ramulator_chunk_id = h->next_direct_prime_chunk_id++;
    h->direct_prime_chunks_issued++;

    for (int i = 0; i < 3; i++) {
      bool ok = issue_direct_prime_subread(h, chunk_key, i);
      if (!ok) {
        h->direct_prime_retry_q.push_back({chunk_key, i});
      }
    }
  }

  return true;
}

extern "C" void* prime_ramulator_create(const char* config_path) {
  try {
    if (!config_path || !config_path[0]) {
      std::cerr << "[prime_ramulator_bridge] empty config_path\n";
      return nullptr;
    }

    auto* h = new PrimeRamulatorBridge();

    h->prime_mode = env_enabled("ACCELSIM_RAMULATOR_PRIME_MODE");
    h->prime_direct_mode = env_enabled("ACCELSIM_RAMULATOR_PRIME_DIRECT");
      h->hbm_side_comp_mode = env_enabled("ACCELSIM_HBM_SIDE_COMP_MODE");
      h->hbm_comp_padded_mapping = env_enabled("ACCELSIM_HBM_COMP_PADDED_MAPPING");

    h->prime_decomp_latency = env_int("ACCELSIM_PRIME_DECOMP_LATENCY", 3);
    h->prime_wb_latency = env_int("ACCELSIM_PRIME_WB_LATENCY", 4);
    h->prime_chunk_bytes = env_int("ACCELSIM_PRIME_CHUNK_BYTES", 128);
    h->prime_compressed_bytes = env_int("ACCELSIM_PRIME_COMPRESSED_BYTES", 96);
    h->prime_tx_bytes = env_int("ACCELSIM_PRIME_TX_BYTES", 32);
    h->prime_direct_channels = env_int("ACCELSIM_PRIME_DIRECT_CHANNELS", 8);

      h->hbm_comp_chunk_bytes =
          env_int("ACCELSIM_HBM_COMP_LOGICAL_CHUNK_BYTES",
                  env_int("ACCELSIM_HBM_COMP_CHUNK_BYTES", 128));
      h->hbm_comp_compressed_bytes =
          env_int("ACCELSIM_HBM_COMP_COMPRESSED_BYTES",
                  env_int("ACCELSIM_HBM_COMP_COMPRESSED_CHUNK_BYTES", 96));
      h->hbm_comp_tx_bytes = env_int("ACCELSIM_HBM_COMP_TX_BYTES", 32);
      h->hbm_comp_decomp_latency =
          env_int_nonnegative("ACCELSIM_HBM_COMP_DECOMP_LATENCY", 3);
      h->hbm_comp_mapping_latency =
          env_int_nonnegative("ACCELSIM_HBM_COMP_MAPPING_LATENCY", 0);

    ConfigNode cfg = Config::parse_config_file(std::string(config_path));

    h->frontend.reset(Factory::create_frontend(cfg));
    h->memory_system.reset(Factory::create_memory_system(cfg));

    h->frontend->connect_memory_system(h->memory_system.get());
    h->memory_system->connect_frontend(h->frontend.get());

    h->frontend_tick_ratio = h->frontend->get_clock_ratio();
    h->memory_tick_ratio = h->memory_system->get_clock_ratio();

    if (h->frontend_tick_ratio <= 0 || h->memory_tick_ratio <= 0) {
      throw std::runtime_error("clock_ratio must be positive");
    }

    h->frontend_counter = h->memory_tick_ratio - 1;
    h->memory_counter = h->frontend_tick_ratio - 1;

    std::cerr << "[prime_ramulator_bridge] created with config=" << config_path
              << " fe_ratio=" << h->frontend_tick_ratio
              << " mem_ratio=" << h->memory_tick_ratio
              << " tx_bytes=" << h->memory_system->get_tx_bytes()
              << " prime_mode=" << (h->prime_mode ? 1 : 0)
              << " prime_direct_mode=" << (h->prime_direct_mode ? 1 : 0)
              << " prime_direct_channels=" << h->prime_direct_channels
              << " prime_chunk_bytes=" << h->prime_chunk_bytes
              << " prime_compressed_bytes=" << h->prime_compressed_bytes
              << " prime_decomp_latency=" << h->prime_decomp_latency
              << " prime_wb_latency=" << h->prime_wb_latency
              << "\n";
      g_hbm_comp_last_bridge = h;
      if (!g_hbm_comp_atexit_registered) {
        std::atexit(hbm_comp_atexit_dump);
        g_hbm_comp_atexit_registered = true;
      }

      std::cerr << "[hbm_side_comp_config]"
                << " hbm_side_comp_mode=" << (h->hbm_side_comp_mode ? 1 : 0)
                << " hbm_comp_chunk_bytes=" << h->hbm_comp_chunk_bytes
                << " hbm_comp_compressed_bytes=" << h->hbm_comp_compressed_bytes
                << " hbm_comp_decomp_latency=" << h->hbm_comp_decomp_latency
                << " hbm_comp_mapping_latency=" << h->hbm_comp_mapping_latency
                << " hbm_comp_padded_mapping=" << (h->hbm_comp_padded_mapping ? 1 : 0)
                << "\n";


    return h;
  } catch (const std::exception& e) {
    std::cerr << "[prime_ramulator_bridge] create failed: " << e.what() << "\n";
    return nullptr;
  }
}

extern "C" int prime_ramulator_send(
    void* handle,
    unsigned long long addr,
    int is_write,
    int source_id,
    int size_bytes
) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  if (!h) return 0;

  int user_source_id = source_id;
  int ramulator_core_id = 0;

  // Direct PrimeHBM12 mode:
  // Reads become PrimeSubRead requests sent directly to memory_system->send().
  // Writes are terminal writebacks in Accel-Sim, so complete them upon acceptance
  // to avoid using flat-address External frontend with PassThrough mapping.
  if (h->prime_direct_mode) {
    if (is_write) {
      (void)addr;
      (void)size_bytes;
      h->sent++;
      h->completed_source_ids.push_back(user_source_id);
      h->completed++;
      return 1;
    }

    return send_direct_prime_parent_read(h, addr, user_source_id) ? 1 : 0;
  }

  // PriME mode v1:
  // Bridge internally transforms reads into compressed 96B HBM2 reads.
  // HBM-side Compression V1:
  // Compressed 96B HBM2 reads + logic-die decompression + direct return.
  if (h->hbm_side_comp_mode && !is_write) {
    (void)size_bytes;
    return send_hbm_comp_parent_read(h, addr, user_source_id) ? 1 : 0;
  }

  if (h->prime_mode && !is_write) {
    (void)size_bytes;
    return send_prime_parent_read(h, addr, user_source_id) ? 1 : 0;
  }

  int type = is_write ? Request::Type::Write : Request::Type::Read;

  auto read_callback = [h, user_source_id](Request& req) {
    (void)req;
    h->completed_source_ids.push_back(user_source_id);
    h->completed++;
  };

  std::function<void(Request&)> callback;
  if (!is_write) {
    callback = read_callback;
  }

  bool ok = h->frontend->receive_external_requests(
      type,
      static_cast<Addr_t>(addr),
      ramulator_core_id,
      callback,
      size_bytes
  );

  if (ok) {
    h->sent++;

    if (is_write) {
      h->completed_source_ids.push_back(user_source_id);
      h->completed++;
    }

    return 1;
  }

  return 0;
}

extern "C" void prime_ramulator_tick(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  if (!h) return;

  if (h->prime_direct_mode) {
    drain_direct_prime_retry(h);
  } else if (h->hbm_side_comp_mode) {
    drain_hbm_comp_internal_retry(h);
  } else if (h->prime_mode) {
    drain_prime_internal_retry(h);
  }

  if (++h->frontend_counter >= h->memory_tick_ratio) {
    h->frontend_counter = 0;
    h->frontend->tick();
  }

  if (++h->memory_counter >= h->frontend_tick_ratio) {
    h->memory_counter = 0;
    h->memory_system->tick();
  }

  if (!h->prime_direct_mode && h->hbm_side_comp_mode) {
    complete_ready_hbm_comp_chunks(h);
  } else if (!h->prime_direct_mode && h->prime_mode) {
    complete_ready_prime_chunks(h);
  }

  h->cycle++;
}

extern "C" int prime_ramulator_pop_completed(void* handle, int* source_id) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  if (!h || !source_id) return 0;

  if (h->completed_source_ids.empty()) return 0;

  *source_id = h->completed_source_ids.front();
  h->completed_source_ids.pop_front();
  return 1;
}

extern "C" unsigned long long prime_ramulator_cycle(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->cycle : 0;
}

extern "C" unsigned long long prime_ramulator_sent(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->sent : 0;
}

extern "C" unsigned long long prime_ramulator_completed(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->completed : 0;
}

extern "C" unsigned long long prime_ramulator_prime_chunks_issued(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->prime_chunks_issued : 0;
}

extern "C" unsigned long long prime_ramulator_prime_chunks_completed(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->prime_chunks_completed : 0;
}

extern "C" unsigned long long prime_ramulator_prime_physical_reads_sent(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? h->prime_physical_reads_sent : 0;
}

extern "C" unsigned long long prime_ramulator_prime_retry_queue_size(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);
  return h ? static_cast<unsigned long long>(h->prime_retry_q.size()) : 0;
}

extern "C" void prime_ramulator_destroy(void* handle) {
  auto* h = reinterpret_cast<PrimeRamulatorBridge*>(handle);

  if (h) {
    std::cerr << "[prime_ramulator_bridge] destroy"
              << " cycle=" << h->cycle
              << " sent=" << h->sent
              << " completed=" << h->completed
              << " prime_mode=" << (h->prime_mode ? 1 : 0)
              << " prime_direct_mode=" << (h->prime_direct_mode ? 1 : 0)
              << " prime_chunks_issued=" << h->prime_chunks_issued
              << " prime_chunks_completed=" << h->prime_chunks_completed
              << " prime_physical_reads_sent=" << h->prime_physical_reads_sent
              << " direct_prime_chunks_issued=" << h->direct_prime_chunks_issued
              << " direct_prime_chunks_completed=" << h->direct_prime_chunks_completed
              << " direct_prime_subreads_sent=" << h->direct_prime_subreads_sent
              << " prime_retry_q=" << h->prime_retry_q.size()
              << " direct_prime_retry_q=" << h->direct_prime_retry_q.size()
              << "\n";
  }
    if (h) {
      std::cerr << "[hbm_side_comp_stats]"
                << " hbm_side_comp_mode=" << (h->hbm_side_comp_mode ? 1 : 0)
                << " hbm_comp_chunks_issued=" << h->hbm_comp_chunks_issued
                << " hbm_comp_chunks_completed=" << h->hbm_comp_chunks_completed
                << " hbm_comp_physical_reads_sent=" << h->hbm_comp_physical_reads_sent
                << " hbm_comp_retry_q=" << h->hbm_comp_retry_q.size()
                << "\n";
    }


  delete h;
}
