#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "prime_ramulator_bridge.h"

struct Req {
  unsigned long long cycle;
  unsigned long long addr;
  int is_write;
  int size_bytes;
  int source_id;
};

static std::vector<std::string> split_csv(const std::string& s) {
  std::vector<std::string> out;
  std::stringstream ss(s);
  std::string item;
  while (std::getline(ss, item, ',')) out.push_back(item);
  return out;
}

static int find_col(const std::vector<std::string>& header, const std::string& name) {
  for (int i = 0; i < (int)header.size(); i++) {
    if (header[i] == name) return i;
  }
  return -1;
}

static std::vector<Req> load_trace(const std::string& path, int reads_only) {
  std::ifstream fin(path);
  if (!fin) {
    throw std::runtime_error("cannot open trace: " + path);
  }

  std::string line;
  if (!std::getline(fin, line)) {
    throw std::runtime_error("empty trace: " + path);
  }

  auto header = split_csv(line);

  int c_cycle = find_col(header, "cycle");
  int c_addr = find_col(header, "addr");
  int c_is_write = find_col(header, "is_write");
  int c_size = find_col(header, "data_size");

  if (c_cycle < 0 || c_addr < 0 || c_is_write < 0 || c_size < 0) {
    throw std::runtime_error("missing required columns");
  }

  std::vector<Req> reqs;
  int sid = 0;

  while (std::getline(fin, line)) {
    if (line.empty()) continue;

    auto v = split_csv(line);
    if ((int)v.size() <= std::max({c_cycle, c_addr, c_is_write, c_size})) continue;

    int is_write = std::stoi(v[c_is_write]);
    if (reads_only && is_write) continue;

    Req r;
    r.cycle = std::stoull(v[c_cycle]);
    r.addr = std::stoull(v[c_addr]);
    r.is_write = is_write;
    r.size_bytes = std::stoi(v[c_size]);
    r.source_id = sid++;

    reqs.push_back(r);
  }

  if (!reqs.empty()) {
    unsigned long long base = reqs.front().cycle;
    for (auto& r : reqs) r.cycle -= base;
  }

  return reqs;
}

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "Usage: " << argv[0]
              << " CONFIG_YAML ACCELSIM_MEMTRACE_CSV [reads_only=1]\n";
    return 1;
  }

  std::string config = argv[1];
  std::string trace = argv[2];
  int reads_only = argc >= 4 ? std::stoi(argv[3]) : 1;

  auto reqs = load_trace(trace, reads_only);

  std::cout << "loaded_requests=" << reqs.size() << "\n";

  void* h = prime_ramulator_create(config.c_str());
  if (!h) {
    std::cerr << "failed to create bridge\n";
    return 1;
  }

  size_t next = 0;
  unsigned long long completed = 0;
  unsigned long long max_cycles = 100000000ULL;

  while ((next < reqs.size() || completed < reqs.size()) &&
         prime_ramulator_cycle(h) < max_cycles) {
    unsigned long long now = prime_ramulator_cycle(h);

    while (next < reqs.size() && reqs[next].cycle <= now) {
      const auto& r = reqs[next];

      int ok = prime_ramulator_send(
          h,
          r.addr,
          r.is_write,
          r.source_id,
          r.size_bytes
      );

      if (!ok) {
        break;
      }

      next++;
    }

    prime_ramulator_tick(h);

    int sid = -1;
    while (prime_ramulator_pop_completed(h, &sid)) {
      completed++;
    }
  }

  std::cout << "bridge_cycles=" << prime_ramulator_cycle(h) << "\n";
  std::cout << "sent=" << prime_ramulator_sent(h) << "\n";
  std::cout << "completed=" << completed << "\n";
  std::cout << "bridge_completed_counter=" << prime_ramulator_completed(h) << "\n";

  prime_ramulator_destroy(h);

  if (completed != reqs.size()) {
    std::cerr << "ERROR: not all requests completed\n";
    return 2;
  }

  return 0;
}
