#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fmt/format.h>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include "ramulator/base/base.h"
#include "ramulator/controller/impl/hbm_controller_base.h"

namespace Ramulator {

namespace fs = std::filesystem;

class PrimeHBM12Controller final : public HBMControllerBase {
  RAMULATOR_REGISTER_IMPLEMENTATION_DERIVED(IController, PrimeHBM12Controller, HBMControllerBase, "PrimeHBM12")

 private:
  struct PrimeInflight {
    int chunk_id = -1;
    Request original_req;

    int channel = 0;
    int pseudochannel = 0;
    int bankgroup = 0;
    int even_bank = 0;
    int row = 0;
    int read_col_base = 0;
    int odd_bank = 0;
    int write_col_base = 0;

    int subreads_received = 0;
    int outstanding_reads = 3;
    Clk_t read_done = 0;

    bool scheduled = false;
    bool completed = false;

    Clk_t decomp_start = 0;
    Clk_t decomp_done = 0;
    Clk_t wb_start = 0;
    Clk_t wb_done = 0;
  };

  std::unordered_map<int, PrimeInflight> m_prime_reqs;
  std::vector<int> m_prime_done_list;

  struct PrimePseudoCmdEvent {
    int chunk_id = -1;
    int cmd_id = -1;
    std::string cmd_name;
    Clk_t issue_clk = 0;
    AddrVec_t addr_vec;
  };

  std::vector<PrimePseudoCmdEvent> m_prime_pseudo_cmd_events;

  // Level 4C-timing: chunks whose decompression is done and whose PRIME_WB
  // should be issued using DRAMDevice timing constraints.
  std::vector<int> m_prime_device_wb_ready_list;

  std::unordered_map<int, Clk_t> m_decomp_available;
  std::unordered_map<long long, Clk_t> m_odd_bank_available;

  int m_prime_decomp_latency = 3;
  int m_prime_wb_cost = 4;
  std::string m_prime_wb_timing_mode = "manual";

  int m_cmd_prime_rd96 = -1;
  int m_cmd_xmc_decomp = -1;
  int m_cmd_prime_wb = -1;

  size_t s_prime_subread_reqs = 0;
  size_t s_prime_chunks_created = 0;
  size_t s_prime_chunks_completed = 0;

  size_t s_prime_cmd_rd96 = 0;
  size_t s_prime_cmd_xmc_decomp = 0;
  size_t s_prime_cmd_wb = 0;

  size_t s_prime_device_cmd_rd96 = 0;
  size_t s_prime_device_cmd_xmc_decomp = 0;
  size_t s_prime_device_cmd_wb = 0;

  size_t s_prime_wb_device_stall_cycles = 0;

  bool m_event_log_enabled = false;
  std::string m_event_log_base_path;
  bool m_event_log_opened = false;
  std::ofstream m_event_log_file;

  bool m_cmd_trace_enabled = false;
  std::string m_cmd_trace_base_path;
  bool m_cmd_trace_opened = false;
  std::ofstream m_cmd_trace_file;

 public:
  void init() override {
    HBMControllerBase::init();

    // Level 4A: verify that HBM2 has PriME command ids.
    // These commands are not issued through DRAMDevice yet, so timing remains
    // identical to the Level 3 controller-event model.
    if (!m_device.m_spec->has_command("PRIME_RD96") ||
        !m_device.m_spec->has_command("XMC_DECOMP") ||
        !m_device.m_spec->has_command("PRIME_WB")) {
      throw std::runtime_error(
          "PrimeHBM12 Level4A requires HBM2 commands PRIME_RD96, XMC_DECOMP, PRIME_WB");
    }

    m_cmd_prime_rd96 = m_device.m_spec->get_command_id("PRIME_RD96");
    m_cmd_xmc_decomp = m_device.m_spec->get_command_id("XMC_DECOMP");
    m_cmd_prime_wb = m_device.m_spec->get_command_id("PRIME_WB");

    const char* decomp_env = std::getenv("PRIME_DECOMP_LATENCY");
    if (decomp_env != nullptr && std::string(decomp_env).size() > 0) {
      m_prime_decomp_latency = std::stoi(std::string(decomp_env));
    }

    const char* wb_env = std::getenv("PRIME_WB_COST");
    if (wb_env != nullptr && std::string(wb_env).size() > 0) {
      m_prime_wb_cost = std::stoi(std::string(wb_env));
    }

    const char* wb_timing_mode_env = std::getenv("PRIME_WB_TIMING_MODE");
    if (wb_timing_mode_env != nullptr && std::string(wb_timing_mode_env).size() > 0) {
      m_prime_wb_timing_mode = std::string(wb_timing_mode_env);
    }

    if (m_prime_wb_timing_mode != "manual" && m_prime_wb_timing_mode != "device") {
      throw std::runtime_error("PRIME_WB_TIMING_MODE must be 'manual' or 'device'");
    }

    const char* event_log_env = std::getenv("PRIME_CONTROLLER_EVENT_LOG");
    if (event_log_env != nullptr && std::string(event_log_env).size() > 0) {
      m_event_log_enabled = true;
      m_event_log_base_path = std::string(event_log_env);
    }

    const char* cmd_trace_env = std::getenv("PRIME_CMD_TRACE");
    if (cmd_trace_env != nullptr && std::string(cmd_trace_env).size() > 0) {
      m_cmd_trace_enabled = true;
      m_cmd_trace_base_path = std::string(cmd_trace_env);
    }
  }

  void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
    HBMControllerBase::setup(frontend, memory_system);

    m_stats.add("num_prime_subread_reqs", s_prime_subread_reqs);
    m_stats.add("num_prime_chunks_created", s_prime_chunks_created);
    m_stats.add("num_prime_chunks_completed", s_prime_chunks_completed);

    m_stats.add("num_prime_cmd_rd96", s_prime_cmd_rd96);
    m_stats.add("num_prime_cmd_xmc_decomp", s_prime_cmd_xmc_decomp);
    m_stats.add("num_prime_cmd_wb", s_prime_cmd_wb);

    m_stats.add("num_prime_device_cmd_rd96", s_prime_device_cmd_rd96);
    m_stats.add("num_prime_device_cmd_xmc_decomp", s_prime_device_cmd_xmc_decomp);
    m_stats.add("num_prime_device_cmd_wb", s_prime_device_cmd_wb);

    m_stats.add("num_prime_wb_device_stall_cycles", s_prime_wb_device_stall_cycles);
  }

  bool send(Request& req) override {
    if (req.type_id != Request::Type::Prime) {
      return ControllerBase::send(req);
    }

    // PrimeSubRead addr_vec:
    // [ch, pc, bg, even_bank, row, read_col_base, odd_bank, write_col_base, subread_idx]
    if (req.addr_vec.size() != 9) {
      throw std::runtime_error(
          fmt::format("PrimeHBM12 Level2B expects PrimeSubRead addr_vec size 9, got {}", req.addr_vec.size()));
    }

    if (req.source_id < 0) {
      throw std::runtime_error("PrimeHBM12 Level2B expects req.source_id to carry global chunk_id");
    }

    if (m_read_buffer.size() + 1 > m_read_buffer.max_size) {
      return false;
    }

    const int chunk_id = req.source_id;
    const int subread_idx = req.addr_vec[8];

    if (subread_idx < 0 || subread_idx >= 3) {
      throw std::runtime_error(fmt::format("Invalid PrimeSubRead subread_idx {}", subread_idx));
    }

    auto it = m_prime_reqs.find(chunk_id);
    if (it == m_prime_reqs.end()) {
      PrimeInflight p;
      p.chunk_id = chunk_id;
      p.original_req = req;
      p.original_req.arrive = m_clk;

      p.channel = req.addr_vec[0];
      p.pseudochannel = req.addr_vec[1];
      p.bankgroup = req.addr_vec[2];
      p.even_bank = req.addr_vec[3];
      p.row = req.addr_vec[4];
      p.read_col_base = req.addr_vec[5];
      p.odd_bank = req.addr_vec[6];
      p.write_col_base = req.addr_vec[7];

      auto inserted = m_prime_reqs.emplace(chunk_id, p);
      it = inserted.first;
      s_prime_chunks_created++;
    }

    PrimeInflight& p = it->second;
    p.subreads_received++;

    AddrVec_t rd_addr;
    rd_addr.push_back(p.channel);
    rd_addr.push_back(p.pseudochannel);
    rd_addr.push_back(p.bankgroup);
    rd_addr.push_back(p.even_bank);
    rd_addr.push_back(p.row);
    rd_addr.push_back(p.read_col_base + subread_idx);

    Request subreq(rd_addr, Request::Type::Read);
    subreq.addr = flatten_hbm_addr_vec(rd_addr);
    subreq.intra_channel_addr = subreq.addr;
    subreq.size_bytes = m_device.m_spec->get_tx_bytes();

    subreq.callback = [this, chunk_id](Request& completed) {
      on_prime_subread_complete(chunk_id, completed);
    };

    bool sent = ControllerBase::send(subreq);
    if (!sent) {
      p.subreads_received--;
      return false;
    }

    s_prime_subread_reqs++;
    return true;
  }

  void tick() override {
    hbm_tick_prologue();

    // Level 4C-safe:
    // issue metadata-only PriME pseudo commands into DRAMDevice at their
    // scheduled cycles. These commands have no timing constraints/actions yet.
    serve_prime_pseudo_commands();
    serve_prime_device_wb_ready();

    serve_completed_prime_requests();

    try_issue_slot(SlotType::ColumnBus);
    try_issue_slot(SlotType::RowBus);

    hbm_tick_epilogue();

    serve_prime_pseudo_commands();
    serve_prime_device_wb_ready();
    serve_completed_prime_requests();
  }

 private:
  void on_prime_subread_complete(int chunk_id, Request& completed) {
    PrimeInflight& p = m_prime_reqs.at(chunk_id);

    p.read_done = std::max(p.read_done, completed.depart);
    p.outstanding_reads--;

    if (p.outstanding_reads == 0) {
      schedule_prime_request(p);
    }
  }

  void schedule_prime_request(PrimeInflight& p) {
    if (p.scheduled) {
      return;
    }

    p.scheduled = true;

    p.decomp_start = std::max(p.read_done, m_decomp_available[p.channel]);
    p.decomp_done = p.decomp_start + m_prime_decomp_latency;

    // Pipelined decompressor:
    // latency = m_prime_decomp_latency, initiation interval = 1 cycle.
    m_decomp_available[p.channel] = p.decomp_start + 1;

    if (m_prime_wb_timing_mode == "manual") {
      const long long odd_key = make_odd_bank_key(p.channel, p.pseudochannel, p.bankgroup, p.odd_bank);

      p.wb_start = std::max(p.decomp_done, m_odd_bank_available[odd_key]);
      p.wb_done = p.wb_start + m_prime_wb_cost;

      m_odd_bank_available[odd_key] = p.wb_done;
      m_prime_done_list.push_back(p.chunk_id);
    } else {
      // Device-timing mode:
      // PRIME_WB will be issued later using DRAMDevice::check_timing().
      p.wb_start = -1;
      p.wb_done = -1;
      m_prime_device_wb_ready_list.push_back(p.chunk_id);
    }

    if (m_event_log_enabled && m_prime_wb_timing_mode == "manual") {
      ensure_event_log_open();
      m_event_log_file
          << p.chunk_id << ","
          << p.read_done << ","
          << p.decomp_start << ","
          << p.decomp_done << ","
          << p.wb_start << ","
          << p.wb_done << ","
          << p.channel << ","
          << p.pseudochannel << ","
          << p.bankgroup << ","
          << p.even_bank << ","
          << p.odd_bank << ","
          << p.row << ","
          << p.read_col_base << ","
          << p.write_col_base << "\n";
    }

    if (m_cmd_trace_enabled) {
      ensure_cmd_trace_open();

      write_prime_cmd_trace(p, m_cmd_prime_rd96, "PRIME_RD96", p.original_req.arrive, p.read_done);
      write_prime_cmd_trace(p, m_cmd_xmc_decomp, "XMC_DECOMP", p.decomp_start, p.decomp_done);

      if (m_prime_wb_timing_mode == "manual") {
        write_prime_cmd_trace(p, m_cmd_prime_wb, "PRIME_WB", p.wb_start, p.wb_done);
      }
    }

    // Level 4C:
    // PRIME_RD96 and XMC_DECOMP are always metadata-only pseudo commands.
    // PRIME_WB is queued here only in manual mode. In device mode, it is issued
    // when DRAMDevice::check_timing(PRIME_WB) allows it.
    enqueue_prime_pseudo_command(p, m_cmd_prime_rd96, "PRIME_RD96", p.read_done, false);
    enqueue_prime_pseudo_command(p, m_cmd_xmc_decomp, "XMC_DECOMP", p.decomp_start, false);

    s_prime_cmd_rd96++;
    s_prime_cmd_xmc_decomp++;

    if (m_prime_wb_timing_mode == "manual") {
      enqueue_prime_pseudo_command(p, m_cmd_prime_wb, "PRIME_WB", p.wb_start, true);
      s_prime_cmd_wb++;
    }
  }

  void serve_completed_prime_requests() {
    for (auto it = m_prime_done_list.begin(); it != m_prime_done_list.end();) {
      PrimeInflight& p = m_prime_reqs.at(*it);

      if (p.completed || p.wb_done > m_clk) {
        ++it;
        continue;
      }

      p.original_req.depart = p.wb_done;

      if (p.original_req.callback) {
        p.original_req.callback(p.original_req);
      }

      p.completed = true;
      s_prime_chunks_completed++;

      it = m_prime_done_list.erase(it);
    }
  }

  long long make_odd_bank_key(int channel, int pseudochannel, int bankgroup, int odd_bank) const {
    long long key = channel;
    key = key * 16 + pseudochannel;
    key = key * 16 + bankgroup;
    key = key * 16 + odd_bank;
    return key;
  }

  Addr_t flatten_hbm_addr_vec(const AddrVec_t& av) {
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

  AddrVec_t make_prime_wb_addr_vec(const PrimeInflight& p) const {
    AddrVec_t av;
    av.push_back(p.channel);
    av.push_back(p.pseudochannel);
    av.push_back(p.bankgroup);
    av.push_back(p.odd_bank);
    av.push_back(p.row);
    av.push_back(p.write_col_base);
    return av;
  }

  void serve_prime_device_wb_ready() {
    if (m_prime_wb_timing_mode != "device") {
      return;
    }

    for (auto it = m_prime_device_wb_ready_list.begin(); it != m_prime_device_wb_ready_list.end();) {
      PrimeInflight& p = m_prime_reqs.at(*it);

      if (p.decomp_done > m_clk) {
        ++it;
        continue;
      }

      AddrVec_t wb_addr = make_prime_wb_addr_vec(p);

      if (!m_device.check_timing(m_cmd_prime_wb, wb_addr, m_clk)) {
        s_prime_wb_device_stall_cycles++;
        ++it;
        continue;
      }

      p.wb_start = m_clk;
      p.wb_done = p.wb_start + m_prime_wb_cost;

      // PRIME_WB now enters DRAMDevice timing/state path as a real command.
      m_device.issue_command(m_cmd_prime_wb, wb_addr, p.wb_start);
      s_prime_device_cmd_wb++;
      s_prime_cmd_wb++;

      if (m_cmd_trace_enabled) {
        ensure_cmd_trace_open();
        write_prime_cmd_trace(p, m_cmd_prime_wb, "PRIME_WB", p.wb_start, p.wb_done);
      }

      if (m_event_log_enabled) {
        ensure_event_log_open();
        m_event_log_file
            << p.chunk_id << ","
            << p.read_done << ","
            << p.decomp_start << ","
            << p.decomp_done << ","
            << p.wb_start << ","
            << p.wb_done << ","
            << p.channel << ","
            << p.pseudochannel << ","
            << p.bankgroup << ","
            << p.even_bank << ","
            << p.odd_bank << ","
            << p.row << ","
            << p.read_col_base << ","
            << p.write_col_base << "\n";
      }

      m_prime_done_list.push_back(p.chunk_id);
      it = m_prime_device_wb_ready_list.erase(it);
    }
  }

  void enqueue_prime_pseudo_command(const PrimeInflight& p,
                                    int cmd_id,
                                    const std::string& cmd_name,
                                    Clk_t issue_clk,
                                    bool target_odd_bank) {
    PrimePseudoCmdEvent e;
    e.chunk_id = p.chunk_id;
    e.cmd_id = cmd_id;
    e.cmd_name = cmd_name;
    e.issue_clk = issue_clk;

    const int target_bank = target_odd_bank ? p.odd_bank : p.even_bank;
    const int target_col = target_odd_bank ? p.write_col_base : p.read_col_base;

    e.addr_vec.push_back(p.channel);
    e.addr_vec.push_back(p.pseudochannel);
    e.addr_vec.push_back(p.bankgroup);
    e.addr_vec.push_back(target_bank);
    e.addr_vec.push_back(p.row);
    e.addr_vec.push_back(target_col);

    m_prime_pseudo_cmd_events.push_back(e);
  }

  void serve_prime_pseudo_commands() {
    for (auto it = m_prime_pseudo_cmd_events.begin(); it != m_prime_pseudo_cmd_events.end();) {
      if (it->issue_clk > m_clk) {
        ++it;
        continue;
      }

      // Level 4C-safe:
      // These commands are registered in HBM2 and go through DRAMDevice,
      // but currently have empty metadata, no action, and no timing constraints.
      m_device.issue_command(it->cmd_id, it->addr_vec, it->issue_clk);

      if (it->cmd_id == m_cmd_prime_rd96) {
        s_prime_device_cmd_rd96++;
      } else if (it->cmd_id == m_cmd_xmc_decomp) {
        s_prime_device_cmd_xmc_decomp++;
      } else if (it->cmd_id == m_cmd_prime_wb) {
        s_prime_device_cmd_wb++;
      }

      it = m_prime_pseudo_cmd_events.erase(it);
    }
  }

  void write_prime_cmd_trace(const PrimeInflight& p, int cmd_id, const std::string& cmd, Clk_t start, Clk_t end) {
    m_cmd_trace_file
        << p.chunk_id << ","
        << cmd_id << ","
        << cmd << ","
        << start << ","
        << end << ","
        << (end - start) << ","
        << p.channel << ","
        << p.pseudochannel << ","
        << p.bankgroup << ","
        << p.even_bank << ","
        << p.odd_bank << ","
        << p.row << ","
        << p.read_col_base << ","
        << p.write_col_base << "\n";
  }

  void ensure_cmd_trace_open() {
    if (m_cmd_trace_opened) {
      return;
    }

    fs::path base(m_cmd_trace_base_path);
    fs::path out;

    if (base.has_extension()) {
      out = base.parent_path() /
            (base.stem().string() + ".ch" + std::to_string(m_channel_id) + base.extension().string());
    } else {
      out = fs::path(base.string() + ".ch" + std::to_string(m_channel_id) + ".csv");
    }

    if (out.has_parent_path()) {
      fs::create_directories(out.parent_path());
    }

    m_cmd_trace_file.open(out);
    if (!m_cmd_trace_file.is_open()) {
      throw std::runtime_error(fmt::format("Cannot open Prime command trace {}", out.string()));
    }

    m_cmd_trace_file
        << "chunk_id,cmd_id,cmd,start_cycle,end_cycle,duration,"
        << "channel,pseudochannel,bankgroup,even_bank,odd_bank,row,read_col_base,write_col_base\n";

    m_cmd_trace_opened = true;
  }

  void ensure_event_log_open() {
    if (m_event_log_opened) {
      return;
    }

    fs::path base(m_event_log_base_path);
    fs::path out;

    if (base.has_extension()) {
      out = base.parent_path() /
            (base.stem().string() + ".ch" + std::to_string(m_channel_id) + base.extension().string());
    } else {
      out = fs::path(base.string() + ".ch" + std::to_string(m_channel_id) + ".csv");
    }

    if (out.has_parent_path()) {
      fs::create_directories(out.parent_path());
    }

    m_event_log_file.open(out);
    if (!m_event_log_file.is_open()) {
      throw std::runtime_error(fmt::format("Cannot open Prime controller event log {}", out.string()));
    }

    m_event_log_file
        << "chunk_id,read_done,decomp_start,decomp_done,wb_start,wb_done,"
        << "channel,pseudochannel,bankgroup,even_bank,odd_bank,row,read_col_base,write_col_base\n";

    m_event_log_opened = true;
  }
};

}  // namespace Ramulator
