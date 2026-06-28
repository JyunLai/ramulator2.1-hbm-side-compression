#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fmt/format.h>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include "ramulator/base/param.h"
#include "ramulator/frontend/i_frontend.h"

namespace Ramulator {

namespace fs = std::filesystem;

class PrimeTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, PrimeTrace, "PrimeTrace")

 private:
  struct PrimeChunk {
    size_t chunk_id = 0;

    int channel = 0;
    int pseudochannel = 0;
    int bankgroup = 0;
    int even_bank = 0;
    int row = 0;
    int read_col_base = 0;
    int odd_bank = 0;
    int write_col_base = 0;

    int outstanding_reads = 3;
    Clk_t read_done = 0;

    bool scheduled = false;
    Clk_t decomp_start = 0;
    Clk_t decomp_done = 0;
    Clk_t wb_start = 0;
    Clk_t wb_done = 0;
  };

  std::vector<PrimeChunk> m_chunks;

  size_t m_trace_length = 0;
  size_t m_curr_chunk_idx = 0;
  int m_curr_subread_idx = 0;

  size_t m_prime_chunks_fully_injected = 0;
  size_t m_read_reqs_injected = 0;
  size_t m_read_reqs_completed = 0;
  size_t m_prime_chunks_scheduled = 0;

  Clk_t m_clk = 0;
  Clk_t m_max_prime_done = 0;

  std::string m_trace_path;

  int m_decomp_latency = 3;
  int m_wb_cost = 4;

  std::unordered_map<int, Clk_t> m_decomp_available;
  std::unordered_map<long long, Clk_t> m_odd_bank_available;

  bool m_event_log_enabled = false;
  std::string m_event_log_path;
  std::ofstream m_event_log_file;

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_PARSE_PARAM(m_trace_path, std::string, "path").required();

    const char* decomp_env = std::getenv("PRIME_DECOMP_LATENCY");
    if (decomp_env != nullptr && std::string(decomp_env).size() > 0) {
      m_decomp_latency = std::stoi(std::string(decomp_env));
    }

    const char* wb_env = std::getenv("PRIME_WB_COST");
    if (wb_env != nullptr && std::string(wb_env).size() > 0) {
      m_wb_cost = std::stoi(std::string(wb_env));
    }

    const char* event_log_env = std::getenv("PRIME_P_EVENT_LOG");
    if (event_log_env != nullptr && std::string(event_log_env).size() > 0) {
      m_event_log_enabled = true;
      m_event_log_path = std::string(event_log_env);

      fs::path log_path(m_event_log_path);
      if (log_path.has_parent_path()) {
        fs::create_directories(log_path.parent_path());
      }

      m_event_log_file.open(m_event_log_path);
      if (!m_event_log_file.is_open()) {
        throw std::runtime_error(fmt::format("Cannot open PRIME_P_EVENT_LOG file {}", m_event_log_path));
      }

      m_event_log_file
          << "chunk_id,read_done,decomp_start,decomp_done,wb_start,wb_done,"
          << "channel,pseudochannel,bankgroup,even_bank,odd_bank,row,read_col_base,write_col_base\n";
    }

    m_logger.info(fmt::format("Loading Prime P trace file {} ...", m_trace_path));
    init_trace(m_trace_path);
    m_logger.info(fmt::format("Loaded {} Prime chunks.", m_chunks.size()));
    m_logger.info(fmt::format("PrimeTrace decomp_latency={} wb_cost={}", m_decomp_latency, m_wb_cost));
  };

  void tick() override {
    if (m_prime_chunks_fully_injected < m_trace_length) {
      issue_one_subread();
    }

    m_clk++;
  };

 private:
  void issue_one_subread() {
    PrimeChunk& chunk = m_chunks[m_curr_chunk_idx];

    const int col = chunk.read_col_base + m_curr_subread_idx;

    AddrVec_t addr_vec;
    addr_vec.push_back(chunk.channel);
    addr_vec.push_back(chunk.pseudochannel);
    addr_vec.push_back(chunk.bankgroup);
    addr_vec.push_back(chunk.even_bank);
    addr_vec.push_back(chunk.row);
    addr_vec.push_back(col);

    Request req(addr_vec, Request::Type::Read);

    req.addr = flatten_addr_vec(addr_vec);
    req.intra_channel_addr = req.addr;
    req.size_bytes = m_memory_system->get_tx_bytes();

    const size_t chunk_id = chunk.chunk_id;

    req.callback = [this, chunk_id](Request& completed) {
      m_read_reqs_completed++;

      PrimeChunk& c = m_chunks[chunk_id];
      c.read_done = std::max(c.read_done, completed.depart);
      c.outstanding_reads--;

      if (c.outstanding_reads == 0) {
        schedule_prime_chunk(c);
      }
    };

    bool sent = m_memory_system->send(req);
    if (sent) {
      m_read_reqs_injected++;

      m_curr_subread_idx++;
      if (m_curr_subread_idx == 3) {
        m_curr_subread_idx = 0;
        m_curr_chunk_idx++;
        m_prime_chunks_fully_injected++;
      }
    }
  }

  void schedule_prime_chunk(PrimeChunk& c) {
    if (c.scheduled) {
      return;
    }

    c.scheduled = true;

    c.decomp_start = std::max(c.read_done, m_decomp_available[c.channel]);
    c.decomp_done = c.decomp_start + m_decomp_latency;

    // Pipelined decompressor:
    // latency = m_decomp_latency, initiation interval = 1 cycle.
    m_decomp_available[c.channel] = c.decomp_start + 1;

    const long long odd_key = make_odd_bank_key(c.channel, c.pseudochannel, c.bankgroup, c.odd_bank);

    c.wb_start = std::max(c.decomp_done, m_odd_bank_available[odd_key]);
    c.wb_done = c.wb_start + m_wb_cost;

    m_odd_bank_available[odd_key] = c.wb_done;

    m_max_prime_done = std::max(m_max_prime_done, c.wb_done);
    m_prime_chunks_scheduled++;

    if (m_event_log_enabled) {
      m_event_log_file
          << c.chunk_id << ","
          << c.read_done << ","
          << c.decomp_start << ","
          << c.decomp_done << ","
          << c.wb_start << ","
          << c.wb_done << ","
          << c.channel << ","
          << c.pseudochannel << ","
          << c.bankgroup << ","
          << c.even_bank << ","
          << c.odd_bank << ","
          << c.row << ","
          << c.read_col_base << ","
          << c.write_col_base << "\n";
    }
  }

  long long make_odd_bank_key(int channel, int pseudochannel, int bankgroup, int odd_bank) const {
    long long key = channel;
    key = key * 16 + pseudochannel;
    key = key * 16 + bankgroup;
    key = key * 16 + odd_bank;
    return key;
  }

  Addr_t flatten_addr_vec(const AddrVec_t& av) {
    if (av.size() == 6) {
      Addr_t flat = 0;
      flat |= (static_cast<Addr_t>(av[0]) & 0xF) << 44;
      flat |= (static_cast<Addr_t>(av[1]) & 0xF) << 40;
      flat |= (static_cast<Addr_t>(av[2]) & 0xF) << 36;
      flat |= (static_cast<Addr_t>(av[3]) & 0xF) << 32;
      flat |= (static_cast<Addr_t>(av[4]) & 0xFFFFF) << 12;
      flat |= (static_cast<Addr_t>(av[5]) & 0xFFF);
      return flat;
    }

    Addr_t flat = 0;
    for (const auto& x : av) {
      flat = flat * 4096 + static_cast<Addr_t>(x);
    }
    return flat;
  }

  // Prime P trace format:
  //
  //   P channel,pseudochannel,bankgroup,even_bank,row,read_col_base,odd_bank,write_col_base
  //
  // Example:
  //
  //   P 7,0,2,0,42,30,1,120
  //
  // One P command represents one 96B compressed chunk:
  //   RD32 col_base
  //   RD32 col_base + 1
  //   RD32 col_base + 2
  //   XMC decompression
  //   internal writeback to paired odd bank
  void init_trace(const std::string& file_path_str) {
    fs::path trace_path(file_path_str);
    if (!fs::exists(trace_path)) {
      throw std::runtime_error(fmt::format("Trace {} does not exist!", file_path_str));
    }

    std::ifstream trace_file(trace_path);
    if (!trace_file.is_open()) {
      throw std::runtime_error(fmt::format("Trace {} cannot be opened!", file_path_str));
    }

    std::string line;
    int line_num = 0;

    while (std::getline(trace_file, line)) {
      line_num++;

      if (line.empty()) {
        continue;
      }

      std::vector<std::string> tokens;
      tokenize(tokens, line, " ");

      if (tokens.size() != 2) {
        throw std::runtime_error(
            fmt::format("Trace {} line {}: expected 2 tokens, got {}", file_path_str, line_num, tokens.size()));
      }

      if (tokens[0] != "P") {
        throw std::runtime_error(
            fmt::format("Trace {} line {}: unknown type '{}' (expected P)", file_path_str, line_num, tokens[0]));
      }

      std::vector<std::string> vals;
      tokenize(vals, tokens[1], ",");

      if (vals.size() != 8) {
        throw std::runtime_error(
            fmt::format("Trace {} line {}: expected 8 address fields, got {}", file_path_str, line_num, vals.size()));
      }

      PrimeChunk chunk;
      chunk.chunk_id = m_chunks.size();
      chunk.channel = static_cast<int>(std::stoll(vals[0]));
      chunk.pseudochannel = static_cast<int>(std::stoll(vals[1]));
      chunk.bankgroup = static_cast<int>(std::stoll(vals[2]));
      chunk.even_bank = static_cast<int>(std::stoll(vals[3]));
      chunk.row = static_cast<int>(std::stoll(vals[4]));
      chunk.read_col_base = static_cast<int>(std::stoll(vals[5]));
      chunk.odd_bank = static_cast<int>(std::stoll(vals[6]));
      chunk.write_col_base = static_cast<int>(std::stoll(vals[7]));

      m_chunks.push_back(chunk);
    }

    trace_file.close();

    m_trace_length = m_chunks.size();

    if (m_trace_length == 0) {
      throw std::runtime_error(fmt::format("Trace {} is empty!", file_path_str));
    }
  };

  bool is_finished() override {
    const bool all_prime_chunks_injected = (m_prime_chunks_fully_injected >= m_trace_length);
    const bool all_reads_completed = (m_read_reqs_completed >= m_trace_length * 3);
    const bool all_prime_chunks_scheduled = (m_prime_chunks_scheduled >= m_trace_length);
    const bool tail_done = (m_clk >= m_max_prime_done);

    return all_prime_chunks_injected && all_reads_completed && all_prime_chunks_scheduled && tail_done;
  };
};

}  // namespace Ramulator
