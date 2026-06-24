#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>
#define N 1000000


//  Kernel function to perform vector addition
__global__ void vector_addition(int * d_A, int * d_B, int * d_C, long n){
    int blockID = gridDim.x * gridDim.y * blockIdx.z + gridDim.x * blockIdx.y + blockIdx.x;
    int offset = blockDim.x * blockDim.y * threadIdx.z + blockDim.x * threadIdx.y + threadIdx.x;
    int threadID = blockID  *(blockDim.x * blockDim.y * blockDim.z) + offset;
    if (threadID < n) {
        d_C[threadID] = d_A[threadID] + d_B[threadID];
    }
}

void cpu_vector_addition(int * h_A, int * h_B, int * h_C, long n) {
    for (long i = 0; i < n; i++) {
        h_C[i] = h_A[i] + h_B[i];
    }
}

int main(){
    // Allocate memory for vectors on the host
    int* h_A = (int*)malloc(N * sizeof(int));
    int* h_B = (int*)malloc(N * sizeof(int));
    int* h_C = (int*)malloc(N * sizeof(int));

    // Define pointers for device memory
    int * d_A, *d_B, *d_C;

    // Initialize host vectors
    for (int i = 0; i < N; i++) {
        h_A[i] = rand() % 100; // Random values for A
        h_B[i] = rand() % 100; // Random values for B
    }

    // Allocate memory on the device
    cudaMalloc(&d_A, sizeof(int)*N);
    cudaMalloc(&d_B, sizeof(int)*N);
    cudaMalloc(&d_C, sizeof(int)*N);
    // Check for allocation errors
    
    // Copy input vectors to the device
    cudaMemcpy(d_A, h_A, sizeof(int) * N , cudaMemcpyHostToDevice);
    cudaMemcpy(d_B, h_B, sizeof(int) * N , cudaMemcpyHostToDevice); 

    // Define the block size and grid size
    int blockSize = 1024; // Number of threads per block
    dim3 blockDim(blockSize, 1, 1); // 1D block with blockSize threads

    // Calculate the number of blocks needed
    int numBlocks = (N + blockSize - 1) / blockSize; // This ensures we cover all elements
    // Define the grid dimensions
    // Using 1D grid with numBlocks blocks
    dim3 gridDim(numBlocks, 1, 1); // 1D grid with numBlocks blocks

    vector_addition<<<gridDim, blockDim>>>(d_A, d_B, d_C, N);
    cpu_vector_addition(h_A, h_B, h_C, N); // CPU addition for verification
    //Sync
    cudaDeviceSynchronize();

    // Copy the result vector back to the host
    cudaMemcpy(h_C, d_C, sizeof(int) * N, cudaMemcpyDeviceToHost);

    //Compare with CPU and GPU result
    for (int i = 0; i < N; i++) {
        if (h_C[i] != h_A[i] + h_B[i]) {
            printf("Error at index %d: %d + %d != %d\n", i, h_A[i], h_B[i], h_C[i]);
            break;
        }
    }
    cudaFree(d_A);
    cudaFree(d_B);
    cudaFree(d_C);

    return 0;
}