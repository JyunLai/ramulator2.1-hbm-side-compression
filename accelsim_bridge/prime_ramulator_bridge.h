#ifndef PRIME_RAMULATOR_BRIDGE_H
#define PRIME_RAMULATOR_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

void* prime_ramulator_create(const char* config_path);

int prime_ramulator_send(
    void* handle,
    unsigned long long addr,
    int is_write,
    int source_id,
    int size_bytes
);

void prime_ramulator_tick(void* handle);

int prime_ramulator_pop_completed(
    void* handle,
    int* source_id
);

unsigned long long prime_ramulator_cycle(void* handle);
unsigned long long prime_ramulator_sent(void* handle);
unsigned long long prime_ramulator_completed(void* handle);

unsigned long long prime_ramulator_prime_chunks_issued(void* handle);
unsigned long long prime_ramulator_prime_chunks_completed(void* handle);
unsigned long long prime_ramulator_prime_physical_reads_sent(void* handle);
unsigned long long prime_ramulator_prime_retry_queue_size(void* handle);

void prime_ramulator_destroy(void* handle);

#ifdef __cplusplus
}
#endif

#endif
