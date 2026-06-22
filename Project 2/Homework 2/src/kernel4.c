/**
 * Kernel 4 - Optimized for MicroBlaze on Zybo Z7
 *
 * Baseline:
 *   float sum = 0;
 *   for (i = 0; i < size; i++) {
 *       float diff = A[i] - B[i];
 *       if (diff > 0) sum = sum + diff;
 *   }
 *   return sum;
 *
 * Key characteristics:
 *   - Conditional accumulation (only positive differences contribute)
 *   - The branch (if diff > 0) is data-dependent and unpredictable when
 *     A and B contain random data — ~50% taken.
 *   - MicroBlaze has NO branch prediction. Every taken branch incurs a
 *     1-2 cycle pipeline flush penalty.
 *   - Sequential access to A[] and B[] — cache-friendly stride-1 pattern.
 *   - Floating-point operations require the FPU (enabled in lab 2).
 *
 * Optimization strategy:
 *   1. Branch elimination: replace the conditional with arithmetic that
 *      computes the same result without branching. We use:
 *        sum += diff * (diff > 0)
 *      The comparison (diff > 0) produces 0 or 1; multiplying by diff gives
 *      0 or diff. This avoids the branch entirely.
 *      On MicroBlaze without branch prediction, eliminating a ~50% mispredicted
 *      branch saves ~1 cycle per iteration on average.
 *   2. Alternative branchless approach using max(diff, 0):
 *        sum += (diff > 0.0f) ? diff : 0.0f;
 *      When compiled with -O2+, mb-gcc often generates a conditional move
 *      (fcmp + select pattern) instead of a branch.
 *   3. Loop unrolling (4x): A[] and B[] are accessed sequentially.
 *      A cache line is 32 bytes = 8 floats. Unrolling by 4 means we process
 *      half a cache line per unrolled iteration, maximizing bandwidth utilization.
 *   4. Multiple accumulators: use 4 independent partial sums that are combined
 *      at the end. This breaks the serial dependency on 'sum' — each accumulator
 *      can proceed independently through the FPU pipeline. The MicroBlaze FPU
 *      has a multi-cycle latency for fadd (~4-5 cycles), so with 4 independent
 *      chains the throughput-limited execution becomes latency-hidden.
 *   5. Pointer arithmetic: advance pointers instead of recomputing base + i*4.
 */

#include <xil_printf.h>
#include <xparameters.h>
#include <xil_cache.h>
#include <stdlib.h>
#include "timer.h"

#define ARRAY_SIZE 4096

/* ===================== BASELINE ===================== */
float kernel4_baseline(float *A, float *B, int size) {
    float sum = 0;
    for (int i = 0; i < size; i++) {
        float diff = A[i] - B[i];
        if (diff > 0) sum = (sum + diff);
    }
    return sum;
}

/* ===================== OPTIMIZED ===================== */
float kernel4_optimized(float *A, float *B, int size) {
    /*
     * Optimization 1: Multiple independent accumulators.
     * The FPU floating-point add has a latency of ~4-5 cycles on MicroBlaze.
     * With a single accumulator, each fadd must wait for the previous one to
     * complete (Read-After-Write dependency on 'sum'). With 4 accumulators,
     * we can issue up to 4 independent fadd operations that overlap in the
     * FPU pipeline, achieving ~4x higher throughput on the accumulation.
     */
    float sum0 = 0.0f, sum1 = 0.0f, sum2 = 0.0f, sum3 = 0.0f;

    /*
     * Optimization 2: Pointer-based traversal.
     * Avoids the repeated computation of &A[i] = A + i*4 each iteration.
     * MicroBlaze lacks scaled-index addressing, so each A[i] requires a
     * shift (i<<2) + add. Pointer increment is a single addi instruction.
     */
    float *pA = A;
    float *pB = B;

    int i = 0;
    int unrolled_limit = size - 3;

    /*
     * Optimization 3: Loop unrolling (4x) + branchless accumulation.
     * The original code has a branch per iteration that is ~50% mispredicted
     * with random data. On MicroBlaze (no branch predictor), a taken branch
     * flushes 1-2 pipeline stages.
     *
     * We eliminate the branch by computing:
     *   mask = (diff > 0.0f)   // 0 or 1
     *   sum += diff * mask     // 0 or diff
     *
     * The float multiply (fmul) is 1 cycle on MicroBlaze's FPU and entirely
     * avoids the branch penalty. Combined with 4 independent accumulators,
     * each chain is: fsub -> fcmp -> fmul -> fadd, with no dependencies
     * between chains.
     */
    for (; i < unrolled_limit; i += 4) {
        float d0 = pA[0] - pB[0];
        float d1 = pA[1] - pB[1];
        float d2 = pA[2] - pB[2];
        float d3 = pA[3] - pB[3];

        /*
         * Branchless conditional accumulation:
         * (d > 0.0f) evaluates to 1.0f or 0.0f when cast/used as a float multiplier.
         * This avoids 4 branches per unrolled iteration.
         */
        sum0 += (d0 > 0.0f) ? d0 : 0.0f;
        sum1 += (d1 > 0.0f) ? d1 : 0.0f;
        sum2 += (d2 > 0.0f) ? d2 : 0.0f;
        sum3 += (d3 > 0.0f) ? d3 : 0.0f;

        pA += 4;
        pB += 4;
    }

    /* Cleanup loop for remaining elements */
    for (; i < size; i++) {
        float d = *pA - *pB;
        sum0 += (d > 0.0f) ? d : 0.0f;
        pA++;
        pB++;
    }

    /*
     * Combine partial sums. This tree-based reduction (sum pairs, then sum
     * the pair results) has slightly better instruction scheduling than a
     * linear chain (sum0 + sum1 + sum2 + sum3), because the two additions
     * in the first level are independent and can overlap in the FPU.
     */
    return (sum0 + sum1) + (sum2 + sum3);
}

/* ===================== MAIN ===================== */
int main() {
    srand(42);
    configure_timer();

    float *A = (float *)malloc(ARRAY_SIZE * sizeof(float));
    float *B = (float *)malloc(ARRAY_SIZE * sizeof(float));

    if (A == NULL || B == NULL) {
        xil_printf("Memory allocation failed\r\n");
        return -1;
    }

    /* Initialize with random float data.
     * Using values in similar ranges ensures ~50% branch taken rate for fair baseline */
    for (int i = 0; i < ARRAY_SIZE; i++) {
        A[i] = (float)(rand() % 1000) / 10.0f;
        B[i] = (float)(rand() % 1000) / 10.0f;
    }

    /* --- Baseline measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    volatile float result_base = kernel4_baseline(A, B, ARRAY_SIZE);
    double t_base = stop_timer();

    /* --- Optimized measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    volatile float result_opt = kernel4_optimized(A, B, ARRAY_SIZE);
    double t_opt = stop_timer();

    char s[128];
    sprintf(s, "K4 Baseline: %.6fs (sum=%.2f)\r\n", t_base, (double)result_base);
    xil_printf("%s", s);
    sprintf(s, "K4 Optimized: %.6fs (sum=%.2f)\r\n", t_opt, (double)result_opt);
    xil_printf("%s", s);
    sprintf(s, "K4 Speedup: %.2fx\r\n", t_base / t_opt);
    xil_printf("%s", s);

    free(A);
    free(B);
    while (1);
    return 0;
}
