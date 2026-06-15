#include <stdio.h>      // Required for printf
#include <stdlib.h>     // Required for malloc
#include <omp.h>

#ifndef NUM_THREADS
	#define NUM_THREADS 2
#endif

// Global variables
int shared_variable = 0; // Shared variable

int main() {
    
    // Create threads
    #pragma omp parallel num_threads(NUM_THREADS)  
    for (int i=0; i < 1e7/NUM_THREADS; i++) {
	// critical section 
	#pragma omp critical		
	shared_variable++; // Increment shared variable
    }

    printf("Shared variable contains value %d.\n", shared_variable);

    return 0;
}
