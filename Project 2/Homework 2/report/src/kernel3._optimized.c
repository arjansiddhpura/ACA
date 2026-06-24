/**
 * Kernel 3 - Optimized for MicroBlaze on Zybo Z7
 *
 * Baseline: h[idx[i]] = h[idx[i]] + w[i]   (scatter-add / histogram pattern)
 *
 * Key characteristics:
 *   - INDIRECT (gather/scatter) memory access pattern via idx[i].
 *   - h[idx[i]] causes random access into array h — extremely cache-unfriendly.
 *   - Each iteration loads idx[i], then uses it to load h[idx[i]], adds w[i],
 *     and stores back to h[idx[i]]. This is 3 loads + 1 store minimum.
 *   - The random access pattern through idx[] means nearly every access to h[]
 *     is a cache miss when ARRAY_SIZE > cache size (typical dcache is 8-64KB).
 *
 * Optimization strategy:
 *   1. Reduce redundant address computation: load idx[i] once into a register,
 *      then use it for both the load and store of h[]. The baseline code
 *      computes h[idx[i]] twice (read + write), which may reload idx[i] if the
 *      compiler doesn't optimize it (common at -O0/-O1).
 *   2. Pointer arithmetic for sequential arrays (w[] and idx[] are accessed
 *      sequentially — perfect for pointer advancement).
 *   3. Loop unrolling (4x): since w[] and idx[] are sequential, unrolling
 *      exploits spatial locality for these two arrays (one cache line holds
 *      8 ints = 2 unrolled iterations of idx+w).
 *   4. Sorting idx[] before processing: if we sort the index array (and
 *      correspondingly reorder w[]), consecutive iterations access nearby
 *      locations in h[], transforming random access into quasi-sequential access.
 *      This dramatically reduces cache misses on h[]. The sorting cost is
 *      O(n log n) but the cache miss reduction is often 10-50x on large arrays.
 *      NOTE: This changes processing order, which is valid since floating-point
 *      addition is commutative in exact arithmetic (results may differ by
 *      rounding, which is acceptable for this application).
 *   5. Accumulate repeated indices: when idx[] contains duplicates, we can
 *      accumulate w[] values for the same index, reducing stores to h[].
 */

#include <xil_printf.h>
#include <xparameters.h>
#include <xil_cache.h>
#include <stdio.h>
#include <stdlib.h>
#include "timer.h"

#define ARRAY_SIZE_KERNEL3 4096
#define H_SIZE_KERNEL3     1024  /* Size of h[] array - indices in idx[] are in [0, H_SIZE) */

/* ===================== BASELINE ===================== */
void kernel3_baseline(float *h, float *w, int *idx, int size) {
    for (int i = 0; i < size; ++i)
        h[idx[i]] = h[idx[i]] + w[i];
}

/* ===================== OPTIMIZED (Version A: unrolled + register reuse) ===================== */
void kernel3_optimized_a(float *h, float *w, int *idx, int size) {
    /*
     * Optimization: Load idx[i] into a register once, reducing the number
     * of loads from 4 (2x idx[i] + h[idx[i]] + w[i]) to 3 (1x idx[i] + h[] + w[i]).
     * Also unroll by 4 to reduce branch overhead and exploit sequential
     * access to both idx[] and w[] arrays (cache line utilization).
     */
    int i = 0;
    int unrolled_limit = size - 3;

    for (; i < unrolled_limit; i += 4) {
        /* Load all four indices at once — they're sequential in memory,
         * so they likely share a cache line (4 ints = 16 bytes < 32B line) */
        int j0 = idx[i];
        int j1 = idx[i + 1];
        int j2 = idx[i + 2];
        int j3 = idx[i + 3];

        /*
         * Perform the scatter-add. Each h[jX] access is potentially random,
         * but by loading all four indices first, we give the memory subsystem
         * a chance to detect and prefetch (on systems with HW prefetch).
         * On MicroBlaze without HW prefetch, the benefit is mainly from
         * reducing branch overhead and idx[]/w[] cache utilization.
         */
        h[j0] += w[i];
        h[j1] += w[i + 1];
        h[j2] += w[i + 2];
        h[j3] += w[i + 3];
    }

	#pragma GCC diagnostic push
	#pragma GCC diagnostic ignored "-Waggressive-loop-optimizations"
    for (; i < size; i++) {
    	int j = idx[i];
    	h[j] += w[i];
    }
	#pragma GCC diagnostic pop
}

/* ===================== OPTIMIZED (Version B: sort-based for maximum cache efficiency) ===== */

/* Simple insertion sort for small-to-medium arrays on MicroBlaze.
 * We sort idx[] and reorder w[] correspondingly so that accesses to h[]
 * become quasi-sequential. For ARRAY_SIZE=4096, insertion sort is adequate
 * and avoids malloc overhead of merge sort. */
static void sort_by_index(int *idx, float *w, int size) {
    for (int i = 1; i < size; i++) {
        int key_idx = idx[i];
        float key_w = w[i];
        int j = i - 1;
        while (j >= 0 && idx[j] > key_idx) {
            idx[j + 1] = idx[j];
            w[j + 1] = w[j];
            j--;
        }
        idx[j + 1] = key_idx;
        w[j + 1] = key_w;
    }
}

void kernel3_optimized_b(float *h, float *w, int *idx, int size) {
    /*
     * Optimization: Sort idx[] so that consecutive iterations access h[]
     * in increasing address order. This converts random scatter into
     * sequential access, maximizing cache line reuse.
     *
     * Why this helps on MicroBlaze with DDR3:
     *   - Cache miss penalty: ~30-50 cycles per miss
     *   - Cache line: 32 bytes = 8 floats
     *   - Without sorting: every h[idx[i]] is random -> ~1 miss per access
     *   - With sorting: consecutive indices map to same cache line -> ~1 miss per 8 accesses
     *   - Net effect: ~8x fewer cache misses on h[]
     *
     * The sort itself costs O(n^2) for insertion sort, but since the sort
     * accesses idx[] and w[] sequentially (cache-friendly), the total cost
     * is often offset by the cache miss savings in the kernel proper,
     * especially when H_SIZE >> cache size.
     */
    sort_by_index(idx, w, size);

    /* After sorting, apply the optimized (unrolled) kernel */
    int i = 0;
    //int unrolled_limit = size - 3;
    int prev_idx = -1;
    float accum = 0.0f;

    /*
     * Additional optimization: accumulate values for duplicate indices.
     * When consecutive sorted entries have the same index, we accumulate
     * their w[] values and perform a single read-modify-write to h[].
     * This reduces memory traffic when indices have many duplicates.
     */
    for (i = 0; i < size; i++) {
        int j = idx[i];
        if (j == prev_idx) {
            /* Same index as previous — just accumulate */
            accum += w[i];
        } else {
            /* New index — flush accumulated value to h[], start new accumulation */
            if (prev_idx >= 0)
                h[prev_idx] += accum;
            prev_idx = j;
            accum = w[i];
        }
    }
    /* Flush last accumulated value */
    if (prev_idx >= 0)
        h[prev_idx] += accum;
}

/* ===================== MAIN ===================== */
int run_kernel3_test() {
    srand(42);
    configure_timer();

    float *h = (float *)malloc(H_SIZE_KERNEL3 * sizeof(float));
    float *h_copy = (float *)malloc(H_SIZE_KERNEL3 * sizeof(float));
    float *w = (float *)malloc(ARRAY_SIZE_KERNEL3 * sizeof(float));
    float *w_copy = (float *)malloc(ARRAY_SIZE_KERNEL3 * sizeof(float));
    int *idx = (int *)malloc(ARRAY_SIZE_KERNEL3 * sizeof(int));
    int *idx_copy = (int *)malloc(ARRAY_SIZE_KERNEL3 * sizeof(int));

    if (!h || !h_copy || !w || !w_copy || !idx || !idx_copy) {
        xil_printf("Memory allocation failed\r\n");
        return -1;
    }

    /* Initialize arrays with random data */
    for (int i = 0; i < H_SIZE_KERNEL3; i++)
        h[i] = (float)(rand() % 100) / 10.0f;
    for (int i = 0; i < ARRAY_SIZE_KERNEL3; i++) {
        w[i] = (float)(rand() % 100) / 10.0f;
        idx[i] = rand() % H_SIZE_KERNEL3;
    }

    /* Save copies for fair comparison */
    for (int i = 0; i < H_SIZE_KERNEL3; i++) h_copy[i] = h[i];
    for (int i = 0; i < ARRAY_SIZE_KERNEL3; i++) {
        w_copy[i] = w[i];
        idx_copy[i] = idx[i];
    }

    /* --- Baseline measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel3_baseline(h, w, idx, ARRAY_SIZE_KERNEL3);
    double t_base = stop_timer();

    /* Restore arrays */
    for (int i = 0; i < H_SIZE_KERNEL3; i++) h[i] = h_copy[i];
    for (int i = 0; i < ARRAY_SIZE_KERNEL3; i++) {
        w[i] = w_copy[i];
        idx[i] = idx_copy[i];
    }

    /* --- Optimized A measurement (unrolled) --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel3_optimized_a(h, w, idx, ARRAY_SIZE_KERNEL3);
    double t_opt_a = stop_timer();

    /* Restore arrays */
    for (int i = 0; i < H_SIZE_KERNEL3; i++) h[i] = h_copy[i];
    for (int i = 0; i < ARRAY_SIZE_KERNEL3; i++) {
        w[i] = w_copy[i];
        idx[i] = idx_copy[i];
    }

    /* --- Optimized B measurement (sorted) --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel3_optimized_b(h, w, idx, ARRAY_SIZE_KERNEL3);
    double t_opt_b = stop_timer();

    char s[128];
    sprintf(s, "K3 Baseline:    %.6fs\r\n", t_base);
    xil_printf("%s", s);
    sprintf(s, "K3 Unrolled:    %.6fs\r\n", t_opt_a);
    xil_printf("%s", s);
    sprintf(s, "K3 Sorted:      %.6fs\r\n", t_opt_b);
    xil_printf("%s", s);
    sprintf(s, "K3 Speedup(A):  %.2fx\r\n", t_base / t_opt_a);
    xil_printf("%s", s);
    sprintf(s, "K3 Speedup(B):  %.2fx\r\n", t_base / t_opt_b);
    xil_printf("%s", s);

    free(h); free(h_copy);
    free(w); free(w_copy);
    free(idx); free(idx_copy);
    return 0;
}
