/**
 * Kernel 2 - Optimized for MicroBlaze on Zybo Z7
 *
 * Baseline: A[i] = A[i-1] + A[i-2] * A[i-3]
 *
 * Key characteristics:
 *   - Loop-carried dependency: A[i] depends on A[i-1] from the PREVIOUS iteration.
 *     This creates a strict serial dependency chain that prevents overlap of
 *     consecutive iterations.
 *   - Each iteration requires: 3 loads, 1 multiply, 1 add, 1 store.
 *   - The multiply is the critical operation: MicroBlaze's HW multiplier has
 *     1-cycle throughput but the dependency chain forces serialization.
 *
 * Optimization strategy:
 *   1. Register-based sliding window: keep A[i-1], A[i-2], A[i-3] in registers
 *      instead of reloading from memory each iteration. This eliminates 2 of the
 *      3 loads per iteration (only the "write-then-shift" remains). On a cache miss
 *      this saves ~60+ cycles per iteration (two fewer DDR3 accesses).
 *   2. Strength reduction on memory accesses: use a single pointer that advances,
 *      avoiding index*4+base recalculation.
 *   3. Loop unrolling (2x): even with the serial dependency, unrolling by 2
 *      reduces branch overhead and allows the compiler to interleave the address
 *      computation of iteration i+1 with the multiply of iteration i, since
 *      MicroBlaze's pipeline can execute the pointer increment in parallel with
 *      the multiply unit.
 *
 * NOTE: This kernel is fundamentally limited by its loop-carried dependency.
 * The dependency A[i] <- A[i-1] means each iteration MUST wait for the previous
 * store to complete. Software optimization can only reduce overhead; the critical
 * path (multiply latency + add latency) cannot be shortened without changing the
 * algorithm's semantics.
 */

#include <xil_printf.h>
#include <xparameters.h>
#include <xil_cache.h>
#include <stdio.h>
#include <stdlib.h>
#include "timer.h"

#define ARRAY_SIZE_KERNEL2 128

/* ===================== BASELINE ===================== */
void kernel2_baseline(int *A, int size) {
    int i;
    for (i = 3; i < size; i++)
        A[i] = A[i - 1] + A[i - 2] * A[i - 3];
}

/* ===================== OPTIMIZED ===================== */
void kernel2_optimized(int *A, int size) {
    /*
     * Optimization 1: Sliding register window.
     * Instead of loading A[i-1], A[i-2], A[i-3] from memory every iteration
     * (3 loads from potentially uncached DDR3), we keep them in CPU registers
     * and shift them forward. This converts 3 loads into register moves, which
     * are single-cycle operations on MicroBlaze.
     *
     * Before (per iteration): 3 loads + 1 multiply + 1 add + 1 store = 6 memory ops
     * After  (per iteration): 0 loads + 1 multiply + 1 add + 1 store = 2 memory ops
     *
     * The register file on MicroBlaze has 32 general-purpose registers, so holding
     * 3 values poses no register pressure problem.
     */
    int r3 = A[0];  /* A[i-3] */
    int r2 = A[1];  /* A[i-2] */
    int r1 = A[2];  /* A[i-1] */

    int *ptr = &A[3]; /* Pointer to current write position */
    int n = size - 3;

    /*
     * Optimization 2: Loop unrolling by 2.
     * Even though we can't break the dependency chain, unrolling reduces the
     * branch instruction frequency. MicroBlaze branch penalty is 1-2 cycles;
     * with ~6 useful instructions per iteration, that's ~15-25% overhead saved.
     * With 2x unroll we compute two iterations back-to-back before branching.
     */
    int i = 0;
    int unrolled_limit = n - 1;

    for (; i < unrolled_limit; i += 2) {
        /* Iteration i: A[i] = A[i-1] + A[i-2] * A[i-3] */
        int val0 = r1 + r2 * r3;
        ptr[0] = val0;

        /* Slide window for iteration i+1 */
        /* Now: r3=A[i-2]=r2, r2=A[i-1]=r1, r1=A[i]=val0 */
        int val1 = val0 + r1 * r2;
        ptr[1] = val1;

        /* Slide window for next pair */
        r3 = r1;    /* was A[i-1], now A[(i+2)-3] = A[i-1] */
        r2 = val0;  /* was A[i],   now A[(i+2)-2] = A[i]   */
        r1 = val1;  /* was A[i+1], now A[(i+2)-1] = A[i+1] */

        ptr += 2;
    }

    /* Handle remaining element (if n is odd) */
    for (; i < n; i++) {
        int val = r1 + r2 * r3;
        *ptr = val;
        ptr++;
        r3 = r2;
        r2 = r1;
        r1 = val;
    }
}

/* ===================== MAIN ===================== */
int run_kernel2_test() {
    srand(42);
    configure_timer();

    int *A = (int *)malloc(ARRAY_SIZE_KERNEL2 * sizeof(int));
    int *A_copy = (int *)malloc(ARRAY_SIZE_KERNEL2 * sizeof(int));
    if (A == NULL || A_copy == NULL) {
        xil_printf("Memory allocation failed\r\n");
        return -1;
    }

    /* Initialize with random data (small values to avoid overflow) */
    for (int i = 0; i < ARRAY_SIZE_KERNEL2; i++) {
        A[i] = rand() % 16;
        A_copy[i] = A[i];
    }

    /* --- Baseline measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel2_baseline(A, ARRAY_SIZE_KERNEL2);
    double t_base = stop_timer();

    /* Restore array */
    for (int i = 0; i < ARRAY_SIZE_KERNEL2; i++)
        A[i] = A_copy[i];

    /* --- Optimized measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel2_optimized(A, ARRAY_SIZE_KERNEL2);
    double t_opt = stop_timer();

    char s[128];
    sprintf(s, "K2 Baseline: %.6fs\r\n", t_base);
    xil_printf("%s", s);
    sprintf(s, "K2 Optimized: %.6fs\r\n", t_opt);
    xil_printf("%s", s);
    sprintf(s, "K2 Speedup: %.2fx\r\n", t_base / t_opt);
    xil_printf("%s", s);

    free(A);
    free(A_copy);
    return 0;
}
