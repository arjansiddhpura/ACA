#include <cuda_runtime.h>
#include <stdio.h>

#define TILE_SIZE 16 // Size of the tile (block) for shared memory

// CUDA kernel for tiled matrix-matrix multiplication (MMM) with int
__global__ void tiledMMM(const int* A, const int* B, int* C, int N) {

    __shared__ int tileA[TILE_SIZE][TILE_SIZE];
    __shared__ int tileB[TILE_SIZE][TILE_SIZE];

    int row = blockIdx.y * TILE_SIZE + threadIdx.y;
    int col = blockIdx.x * TILE_SIZE + threadIdx.x;

    int sum = 0;

    for (int t = 0; t < (N + TILE_SIZE - 1) / TILE_SIZE; t++) {

        // TODO 1: load tileA
        // TODO 2: load tileB

        __syncthreads();

        // TODO 3: compute partial sum

        __syncthreads();
    }

    // TODO 4: write result
}

// Host function using int
void hostMMM(const int* A, const int* B, int* C, int N) {
    int *d_A, *d_B, *d_C;
    size_t bytes = N * N * sizeof(int);
    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);

    cudaMalloc(&d_A, bytes);
    cudaMalloc(&d_B, bytes);
    cudaMalloc(&d_C, bytes);

    cudaMemcpy(d_A, A, bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_B, B, bytes, cudaMemcpyHostToDevice);

    dim3 block(TILE_SIZE, TILE_SIZE);
    dim3 grid((N + TILE_SIZE - 1) / TILE_SIZE, (N + TILE_SIZE - 1) / TILE_SIZE);

    cudaEventRecord(start, 0);
    tiledMMM<<<grid, block>>>(d_A, d_B, d_C, N);
    cudaDeviceSynchronize();
    cudaEventRecord(stop, 0);
    cudaEventSynchronize(stop);

    cudaMemcpy(C, d_C, bytes, cudaMemcpyDeviceToHost);

    float milliseconds = 0;
    cudaEventElapsedTime(&milliseconds, start, stop);
    printf("\nelapsed time %f ms\n", milliseconds);

    cudaFree(d_A);
    cudaFree(d_B);
    cudaFree(d_C);
}

int main() {
    int N = 512;
    size_t bytes = N * N * sizeof(int);

    int *A = (int*)malloc(bytes);
    int *B = (int*)malloc(bytes);
    int *C = (int*)malloc(bytes);

    for (int i = 0; i < N * N; ++i) {
        A[i] = 1;
        B[i] = 2;
    }

    hostMMM(A, B, C, N);

    printf("C[0]=%d\n", C[0]);

    free(A);
    free(B);
    free(C);
    return 0;
}
