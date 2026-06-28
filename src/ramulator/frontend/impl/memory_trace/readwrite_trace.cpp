#include <cstdlib>
#include <filesystem>
#include <fmt/format.h>
#include <fstream>
#include <iostream>

#include "ramulator/base/param.h"
#include "ramulator/frontend/i_frontend.h"

namespace Ramulator {

namespace fs = std::filesystem;

class ReadWriteTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, ReadWriteTrace, "ReadWriteTrace")

 private:
  struct Trace {
    bool is_write;
    AddrVec_t addr_vec;
  };

  std::vector<Trace> m_trace;

  size_t m_trace_length = 0;
  size_t m_curr_trace_idx = 0;

  // Number of requests successfully injected into the memory system.
  size_t m_trace_count = 0;

  // Number of requests completed by the memory controller.
  size_t m_completed_count = 0;

  std::string m_trace_path;

  bool m_completion_log_enabled = false;
  std::string m_completion_log_path;
  std::ofstream m_completion_log_file;

 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(m_clock_ratio, unsigned int, "clock_ratio").required();
    RAMULATOR_PARSE_PARAM(m_trace_path, std::string, "path").required();

    m_logger.info(fmt::format("Loading trace file {} ...", m_trace_path));
    init_trace(m_trace_path);
    m_logger.info(fmt::format("Loaded {} lines.", m_trace.size()));

    const char* completion_log_env = std::getenv("PRIME_COMPLETION_LOG");
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
            fmt::format("Cannot open PRIME_COMPLETION_LOG file {}", m_completion_log_path));
      }

      m_completion_log_file
          << "req_id,op,arrive_cycle,complete_cycle,channel,pseudochannel,bankgroup,bank,row,column\n";

      m_logger.info(fmt::format("Completion log enabled: {}", m_completion_log_path));
    }
  };

  void tick() override {
    // If all trace requests have already been injected, keep the frontend idle.
    // The simulator will continue ticking until callbacks report completion.
    if (m_trace_count >= m_trace_length) {
      return;
    }

    const Trace& t = m_trace[m_curr_trace_idx];

    Request req(t.addr_vec, t.is_write ? Request::Type::Write : Request::Type::Read);

    // Important:
    // Request(addr_vec, type) does not provide a flat req.addr.
    // ControllerBase uses req.addr for write coalescing and read forwarding.
    // Therefore, generate a deterministic flat address from the address vector.
    req.addr = flatten_addr_vec(t.addr_vec);
    req.intra_channel_addr = req.addr;

    req.size_bytes = m_memory_system->get_tx_bytes();

    const size_t req_id = m_trace_count;
    const bool is_write = t.is_write;
    const AddrVec_t addr_vec = t.addr_vec;

    req.callback = [this, req_id, is_write, addr_vec](Request& completed) {
      m_completed_count++;

      if (m_completion_log_enabled) {
        const int ch  = addr_vec.size() > 0 ? addr_vec[0] : -1;
        const int pc  = addr_vec.size() > 1 ? addr_vec[1] : -1;
        const int bg  = addr_vec.size() > 2 ? addr_vec[2] : -1;
        const int bk  = addr_vec.size() > 3 ? addr_vec[3] : -1;
        const int row = addr_vec.size() > 4 ? addr_vec[4] : -1;
        const int col = addr_vec.size() > 5 ? addr_vec[5] : -1;

        m_completion_log_file
            << req_id << ","
            << (is_write ? "W" : "R") << ","
            << completed.arrive << ","
            << completed.depart << ","
            << ch << ","
            << pc << ","
            << bg << ","
            << bk << ","
            << row << ","
            << col << "\n";
      }
    };

    bool sent = m_memory_system->send(req);
    if (sent) {
      m_curr_trace_idx++;
      m_trace_count++;
    }
  };

 private:
  // HBM2 address vector in our traces:
  //   [Channel, PseudoChannel, BankGroup, Bank, Row, Column]
  //
  // Pack into a collision-free flat address for HBM2_2Gb:
  //   Channel       4 bits
  //   PseudoChannel 4 bits
  //   BankGroup     4 bits
  //   Bank          4 bits
  //   Row          20 bits
  //   Column       12 bits
  //
  // Total = 48 bits.
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

    // Fallback for non-HBM2 traces.
    Addr_t flat = 0;
    for (const auto& x : av) {
      flat = flat * 4096 + static_cast<Addr_t>(x);
    }
    return flat;
  }

  // Trace format: one memory access per line, space-separated.
  //   <op> <addr_vec>
  //
  // - op:       R (read) or W (write)
  // - addr_vec: comma-separated integers forming a multi-dimensional address
  //             vector, e.g., channel,pseudochannel,bankgroup,bank,row,column
  //
  // Example:
  //   R 0,0,0,0,100,32
  //   W 0,1,2,3,200,16
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

      bool is_write = false;
      if (tokens[0] == "R") {
        is_write = false;
      } else if (tokens[0] == "W") {
        is_write = true;
      } else {
        throw std::runtime_error(
            fmt::format("Trace {} line {}: unknown type '{}' (expected R or W)", file_path_str, line_num, tokens[0]));
      }

      std::vector<std::string> addr_vec_tokens;
      tokenize(addr_vec_tokens, tokens[1], ",");

      AddrVec_t addr_vec;
      for (const auto& token : addr_vec_tokens) {
        addr_vec.push_back(static_cast<int>(std::stoll(token)));
      }

      m_trace.push_back({is_write, addr_vec});
    }

    trace_file.close();

    m_trace_length = m_trace.size();

    if (m_trace_length == 0) {
      throw std::runtime_error(fmt::format("Trace {} is empty!", file_path_str));
    }
  };

  bool is_finished() override {
    return (m_trace_count >= m_trace_length) && (m_completed_count >= m_trace_length);
  };
};

}  // namespace Ramulator
