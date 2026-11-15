#ifndef MOTIONPACK_CORE_H
#define MOTIONPACK_CORE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Experimental numeric-only ABI v1. Inputs are validated host data.
 * Caller owns all buffers, which must not overlap. Never pass untrusted
 * pointers; the Rust library cannot prove memory mapping or provenance.
 * On error, outputs are not modified.
 */
typedef struct {
    int32_t parent;
    double x, y, rotation, scale, opacity;
} MpNode;
typedef struct {
    uint32_t node, mask; /* mask bits: 1=x, 2=y, 4=rotation, 8=scale, 16=opacity */
    double x, y, rotation, scale, opacity;
} MpVariant;
typedef struct { double time_ms, value; } MpKey;
typedef struct {
    uint32_t node, property, key_start, key_count;
    /* property: 0=x, 1=y, 2=rotation, 3=scale, 4=opacity */
} MpTrack;
typedef struct {
    uint32_t upper, lower;
    double length1, length2, target_x, target_y, bend, weight;
} MpChain;
typedef struct { uint32_t chain, axis, key_start, key_count; } MpIkTrack;
typedef struct { uint32_t chain; double x, y; } MpTarget;
typedef struct {
    double x, y, rotation, scale, opacity;
    double a, b, c, d, tx, ty;
} MpOutput;
enum { MP_OK=0, MP_INVALID_INPUT=1, MP_EVALUATION_FAILED=2 };

/* out_capacity >= node_count; out_time points to one writable double.
 * The host owns every allocation. The Rust call is synchronous; no retained
 * pointers, callbacks, file I/O or arbitrary code execution.
 */
int32_t mp_scene_sample_v1(
    const MpNode *nodes, size_t node_count,
    const MpVariant *variants, size_t variant_count,
    const MpTrack *tracks, size_t track_count,
    const MpKey *keys, size_t key_count,
    const MpChain *chains, size_t chain_count,
    const MpIkTrack *ik_tracks, size_t ik_track_count,
    const MpTarget *targets, size_t target_count,
    double duration, uint32_t loop_flag, double time,
    MpOutput *out, size_t out_capacity, double *out_time);

#ifdef __cplusplus
}
#endif
#endif
