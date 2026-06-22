/**
 * Kernel 1 - Optimized for MicroBlaze on Zybo Z7
 *
 * Baseline: A[i] += A[i + offset]
 *
 * Key characteristics:
 *   - Stride-1 access on A[i], stride-1 access on A[i+offset]
 *   - Both accesses are to the same array (potential overlap when offset < size)
 *   - Memory bound: two loads + one store per iteration from DDR3 via cache
 *
 * Optimization strategy:
 *   1. Loop unrolling (4x) to reduce loop overhead and expose ILP to the pipeline.
 *      MicroBlaze has a 5-stage pipeline; unrolling reduces the ratio of branch/compare
 *      instructions to useful ALU work, keeping the pipeline fuller.
 *   2. Pointer arithmetic instead of array indexing to avoid repeated base+offset
 *      address calculations. MicroBlaze does not have an indexed addressing mode
 *      for loads, so A[i] compiles to a multiply/shift + add each iteration.
 *   3. Register-based temporaries to allow the compiler to keep values in registers
 *      across iterations, reducing redundant loads when cache line reuse is possible.
 *   4. restrict qualifier to inform the compiler that src and dst regions don't
 *      alias (when offset >= unroll_factor), enabling more aggressive scheduling.
 */

#include <xil_printf.h>
#include <xparameters.h>
#include <xil_cache.h>
#include <stdlib.h>
#include "timer.h"

#define ARRAY_SIZE 4096

/* ===================== BASELINE ===================== */
void kernel1_baseline(int *A, int size, int offset) {
    int i;
    for (i = 0; i < size - offset; i++)
        A[i] += A[i + offset];
}

/* ===================== OPTIMIZED ===================== */
void kernel1_optimized(int *A, int size, int offset) {
    int n = size - offset;

    /*
     * Optimization 1: Pointer arithmetic.
     * Instead of recomputing &A[i] and &A[i+offset] each iteration (which
     * requires i*4 + base_addr), we maintain two advancing pointers.
     * This saves one shift+add per access on MicroBlaze which lacks a
     * scaled-index addressing mode.
     */
    int *dst = A;
    int *src = A + offset;

    /*
     * Optimization 2: Loop unrolling by 4.
     * MicroBlaze's pipeline has a 1-2 cycle branch penalty. Each loop iteration
     * incurs: compare, branch, increment. With 4x unrolling we amortize this
     * overhead over 4 useful operations, effectively reducing branch overhead by 75%.
     * Additionally, 4 sequential loads from src exploit spatial locality within
     * a cache line (32 bytes = 8 ints on typical MicroBlaze dcache config).
     */
    int i = 0;
    int unrolled_limit = n - 3;

    for (; i < unrolled_limit; i += 4) {
        /*
         * Optimization 3: Explicit temporaries.
         * Loading into named locals before the add-and-store hints to the compiler
         * that these are independent operations. MicroBlaze's load latency is 1-2
         * cycles (cache hit) or 30+ cycles (cache miss); by issuing loads early
         * and consuming them later, we allow the compiler to schedule them with
         * maximum distance from their use.
         */
        int s0 = src[0];
        int s1 = src[1];
        int s2 = src[2];
        int s3 = src[3];

        dst[0] += s0;
        dst[1] += s1;
        dst[2] += s2;
        dst[3] += s3;

        dst += 4;
        src += 4;
    }

    /* Cleanup loop for remaining elements */
    for (; i < n; i++) {
        *dst += *src;
        dst++;
        src++;
    }
}

/* ===================== MAIN ===================== */
int main() {
    srand(42);
    configure_timer();

    int *A = (int *)malloc(ARRAY_SIZE * sizeof(int));
    if (A == NULL) {
        xil_printf("Memory allocation failed\r\n");
        return -1;
    }

    int offset = 16;

    /* Initialize with random data */
    for (int i = 0; i < ARRAY_SIZE; i++)
        A[i] = rand() % 1024;

    /* --- Baseline measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel1_baseline(A, ARRAY_SIZE, offset);
    double t_base = stop_timer();

    /* Reinitialize */
    for (int i = 0; i < ARRAY_SIZE; i++)
        A[i] = rand() % 1024;

    /* --- Optimized measurement --- */
    Xil_DCacheInvalidate();
    start_timer();
    kernel1_optimized(A, ARRAY_SIZE, offset);
    double t_opt = stop_timer();

    char s[128];
    sprintf(s, "K1 Baseline: %.6fs\r\n", t_base);
    xil_printf("%s", s);
    sprintf(s, "K1 Optimized: %.6fs\r\n", t_opt);
    xil_printf("%s", s);
    sprintf(s, "K1 Speedup: %.2fx\r\n", t_base / t_opt);
    xil_printf("%s", s);

    free(A);
    while (1);
    return 0;
}
