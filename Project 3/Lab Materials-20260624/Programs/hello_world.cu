#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>

#define BLOCK_DIM_X 2
#define BLOCK_DIM_Y 3
#define BLOCK_DIM_Z 2

#define GRID_DIM_X 4
#define GRID_DIM_Y 3
#define GRID_DIM_Z 2
// get_block_id() returns the unique block ID in a 3D grid.
// It calculates the block ID based on the grid dimensions and the current block index.
__device__ int get_block_id() {
    return gridDim.x * gridDim.y * blockIdx.z + gridDim.x * blockIdx.y + blockIdx.x;
}

// get_thread_offset() returns the unique thread offset within a block. 
// It calculates the offset based on the block dimensions and the current thread index.
__device__ int get_thread_offset() {
    return blockDim.x * blockDim.y * threadIdx.z + blockDim.x * threadIdx.y + threadIdx.x;
}

// get_thread_id() returns the unique thread ID in a 3D grid.
// It combines the block ID and thread offset to create a unique identifier for each thread.
__device__ int get_thread_id() {
    int block_id = get_block_id();
    int offset = get_thread_offset();
    return block_id * (blockDim.x * blockDim.y * blockDim.z) + offset;
}

// hello_world() is a kernel function that prints "Hello, World" along with the thread ID.
// It is executed by multiple threads in parallel, each thread printing its own ID.
__global__ void hello_world() {
    int thread_id = get_thread_id();
    // printf("Hello, World from the thread %d\n", thread_id);
}

int main() {
    /* Initialize CUDA: cudaSetDevice(int device) sets the specified GPU device
    as the current device for the calling host thread, enabling subsequent memory
    allocations, stream and event creations, and kernel launches to be associated
    with the device's primary context. This function initializes the runtime state
    for the device and returns an error if the device is in exclusive or prohibited
    compute modes and unavailable for use.*/
    cudaError_t err = cudaSetDevice(0);
    
    if (err != cudaSuccess) {
        fprintf(stderr, "Failed to set device: %s\n", cudaGetErrorString(err));
        return EXIT_FAILURE;
    }

    // Print the device properties
    cudaDeviceProp prop;
    err = cudaGetDeviceProperties(&prop, 0);
    if (err != cudaSuccess) {
        fprintf(stderr, "Failed to get device properties: %s\n", cudaGetErrorString(err));
        return EXIT_FAILURE;
    }   
    printf("Device Name: %s\n", prop.name);
    printf("Total Global Memory: %zu bytes\n", prop.totalGlobalMem);
    printf("Max Threads Per Block: %d\n", prop.maxThreadsPerBlock);
    printf("Max Threads Dim: [%d, %d, %d]\n", prop
            .maxThreadsDim[0], prop.maxThreadsDim[1], prop.maxThreadsDim[2]);
    printf("Max Grid Size: [%d, %d, %d]\n", prop.maxGridSize[0], prop.maxGridSize[1], prop.maxGridSize[2]);
    printf("Warp Size: %d\n", prop.warpSize);
    printf("Shared Memory Per Block: %zu bytes\n", prop.sharedMemPerBlock);
    //print number of sms 
    printf("Number of Multiprocessors: %d\n", prop.multiProcessorCount);

    // Use macros for block and grid dimensions
    dim3 block(BLOCK_DIM_X, BLOCK_DIM_Y, BLOCK_DIM_Z);
    dim3 grid(GRID_DIM_X, GRID_DIM_Y, GRID_DIM_Z);

    // Launch the kernel
    hello_world<<<grid, block>>>();
    
    // Check for errors during kernel launch
    err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "Kernel launch failed: %s\n", cudaGetErrorString(err));
        return EXIT_FAILURE;
    }

    // Synchronize to ensure all printf output is flushed
    cudaDeviceSynchronize();

    return EXIT_SUCCESS;
}
