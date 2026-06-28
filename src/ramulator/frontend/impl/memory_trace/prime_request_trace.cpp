#include <cstdlib>
#include <filesystem>
#include <fmt/format.h>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "ramulator/base/param.h"
#include "ramulator/frontend/i_frontend.h"

namespace Ramulator {

namespace fs = std::filesystem;

class PrimeRequestTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, PrimeRequestTrace, "PrimeRequestTrace")

 private:
  struct PrimeTraceEntry {
    size_t chunk_id = 0;
    AddrVec_t p_addr_vec;  // [ch, pc, bg, even_bank, row, read_col_base, odd_bank, write_col_base]
  };

  std::vector<PrimeTraceEntry> m_trace;

  size_t m_trace_length = 0;
  size_t m_curr_chunk_idx = 0;
  int m_curr_subread_idx = 0;

  size_t m_prime_subreads_sent = 0;
  size_t m_prime_chunks_completed = 0;

  std::string m_trace_path;

  bool m_completion_log_enabled = false;
  std::string m_completion_log_path;
  std::ofstream m_completion_log_file;

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_PARSE_PARAM(m_trace_path, std::string, "path").required();

    const char* completion_log_env = std::getenv("PRIME_REQUEST_COMPLETION_LOG");
    if (completion_log_env != nullptr && std::string(completion_log_env).size() > 0) {
      m_completion_log_enabled = true;
      m_completion_log_path = std::string(completion_log_env);

      fs::path log_path(m_completion_log_path);
      if (log_path.has_parent_path()) {
        fs::create_directories(log_path.parent_path());
      }

      m_completion_log_file.open(m_completion_log_path);
      if (!m_completion_log_file.is_open()) {
        throw std::runtime_error(
            fmt::format("Cannot open PRIME_REQUEST_COMPLETION_LOG file {}", m_completion_log_path));
      }

      m_completion_log_file
          << "chunk_id,arrive_cycle,complete_cycle,"
          << "channel,pseudochannel,bankgroup,even_bank,row,read_col_base,odd_bank,write_col_base\n";
    }

    m_logger.info(fmt::format("Loading PrimeRequestTrace file {} ...", m_trace_path));
    init_trace(m_trace_path);
    m_logger.info(fmt::format("Loaded {} Prime chunks.", m_trace.size()));
    m_logger.info("PrimeRequestTrace mode=PrimeSubRead stream");
  };

  void tick() override {
    if (m_curr_chunk_idx >= m_trace_length) {
      return;
    }

    const PrimeTraceEntry& e = m_trace[m_curr_chunk_idx];

    // PrimeSubRead addr_vec:
    // [ch, pc, bg, even_bank, row, read_col_base, odd_bank, write_col_base, subread_idx]
    AddrVec_t req_addr_vec = e.p_addr_vec;
    req_addr_vec.push_back(m_curr_subread_idx);

    Request req(req_addr_vec, Request::Type::Prime);

    // Use the actual RD32 address as routing/identity address.
    AddrVec_t rd_addr_vec;
    rd_addr_vec.push_back(e.p_addr_vec[0]);  // channel
    rd_addr_vec.push_back(e.p_addr_vec[1]);  // pseudochannel
    rd_addr_vec.push_back(e.p_addr_vec[2]);  // bankgroup
    rd_addr_vec.push_back(e.p_addr_vec[3]);  // even_bank
    rd_addr_vec.push_back(e.p_addr_vec[4]);  // row
    rd_addr_vec.push_back(e.p_addr_vec[5] + m_curr_subread_idx);  // read_col_base + subread

    req.addr = flatten_addr_vec(rd_addr_vec);
    req.intra_channel_addr = req.addr;
    req.size_bytes = m_memory_system->get_tx_bytes();

    // Use source_id to carry the global chunk id to PrimeHBM12.
    req.source_id = static_cast<int>(e.chunk_id);

    const size_t chunk_id = e.chunk_id;
    const AddrVec_t p_addr_vec = e.p_addr_vec;

    // PrimeHBM12 will call this callback exactly once per chunk,
    // after the three PrimeSubReads complete and decomp/writeback finish.
    req.callback = [this, chunk_id, p_addr_vec](Request& completed) {
      m_prime_chunks_completed++;

      if (m_completion_log_enabled) {
        m_completion_log_file
            << chunk_id << ","
            << completed.arrive << ","
            << completed.depart << ","
            << p_addr_vec[0] << ","
            << p_addr_vec[1] << ","
            << p_addr_vec[2] << ","
            << p_addr_vec[3] << ","
            << p_addr_vec[4] << ","
            << p_addr_vec[5] << ","
            << p_addr_vec[6] << ","
            << p_addr_vec[7] << "\n";
      }
    };

    bool sent = m_memory_system->send(req);
    if (sent) {
      m_prime_subreads_sent++;

      m_curr_subread_idx++;
      if (m_curr_subread_idx == 3) {
        m_curr_subread_idx = 0;
        m_curr_chunk_idx++;
      }
    }
  };

 private:
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

  // Input P trace format:
  //
  //   P channel,pseudochannel,bankgroup,even_bank,row,read_col_base,odd_bank,write_col_base
  //
  // This frontend streams each P chunk as three Request::Type::Prime subreads.
  // The controller performs RD32 issue, grouping, decompression, and writeback.
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

      PrimeTraceEntry entry;
      entry.chunk_id = m_trace.size();

      for (const auto& v : vals) {
        entry.p_addr_vec.push_back(static_cast<int>(std::stoll(v)));
      }

      m_trace.push_back(entry);
    }

    trace_file.close();

    m_trace_length = m_trace.size();

    if (m_trace_length == 0) {
      throw std::runtime_error(fmt::format("Trace {} is empty!", file_path_str));
    }
  };

  bool is_finished() override {
    return (m_curr_chunk_idx >= m_trace_length) && (m_prime_chunks_completed >= m_trace_length);
  };
};

}  // namespace Ramulator
