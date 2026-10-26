#ifndef PROJECT86_H
#define PROJECT86_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct P86Machine P86Machine;
typedef enum { P86_RUNNING, P86_HALTED, P86_WAITING_KEY, P86_FAULT } P86Status;
typedef struct {
    uint16_t ax, cx, dx, bx, sp, bp, si, di;
    uint16_t es, cs, ss, ds, ip, flags;
} P86CPUState;
typedef struct {
    P86CPUState cpu;
    uint64_t instructions, cycles;
    P86Status status;
    uint8_t video_mode;
    uint8_t reserved[3];
    char message[256];
} P86Snapshot;
/* Single-owner API: callers serialize every operation, including reads. */
P86Machine *p86_create(void);
void p86_destroy(P86Machine *machine);
/* Select 8086 (0) or the supported 286 real-mode subset (1), before boot. */
void p86_set_cpu286(P86Machine *machine, int enabled);
/* CPU throughput multiplier, clamped to 1..16; device/audio time is unchanged.
   Default is 1 for compatibility and fixtures. Preserved across boot/reset. */
void p86_set_cpu_speed(P86Machine *machine, uint32_t multiplier);
void p86_reset(P86Machine *machine);
void p86_load_demo(P86Machine *machine);
int p86_attach_floppy(P86Machine *machine, const char *path, int writable);
int p86_attach_hard_disk(P86Machine *machine, const char *path, int writable);
int p86_flush_disks(P86Machine *machine);
int p86_boot(P86Machine *machine);
P86Status p86_run(P86Machine *machine, uint64_t instruction_budget);
/* Real-time host execution uses a 4,772,728 Hz virtual clock. */
P86Status p86_run_cycles(P86Machine *machine, uint64_t cycle_budget);
void p86_enable_audio(P86Machine *machine, int enabled);
void p86_get_snapshot(const P86Machine *machine, P86Snapshot *snapshot);
void p86_get_cpu(const P86Machine *machine, P86CPUState *state);
void p86_set_cpu(P86Machine *machine, const P86CPUState *state);
/* Raw instruction stepping: no BIOS dispatch or device scheduling. */
P86Status p86_step_cpu(P86Machine *machine);
uint8_t p86_read_memory(const P86Machine *machine, uint32_t address);
void p86_write_memory(P86Machine *machine, uint32_t address, uint8_t value);
void p86_key(P86Machine *machine, uint8_t ascii, uint8_t scan, int pressed);
void p86_mouse(P86Machine *machine, int dx, int dy, uint8_t buttons);
/* 80x25 cells, character then attribute. Caller owns destination. */
size_t p86_copy_text(const P86Machine *machine, uint8_t *cells, size_t capacity);
size_t p86_copy_pixels(const P86Machine *machine, uint32_t *rgba, size_t capacity,
                       uint32_t *width, uint32_t *height);
size_t p86_read_audio(P86Machine *machine, float *samples, size_t capacity);
uint8_t p86_read_port(P86Machine *machine, uint16_t port);
void p86_write_port(P86Machine *machine, uint16_t port, uint8_t value);
const char *p86_version(void);
#ifdef __cplusplus
}
#endif
#endif
