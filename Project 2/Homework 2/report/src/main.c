#include <stdio.h>
#include <xil_cache.h>
#include "xil_printf.h"


//Declaration of test-functions
int run_kernel1_test();
int run_kernel2_test();
int run_kernel3_test();
int run_kernel4_test();

int main() {

	//Caches disabled for unoptimized hardware version
	Xil_DCacheDisable();
	Xil_ICacheDisable();


	xil_printf("=== START OF MEASUREMENT ===\r\n\r\n");

	xil_printf("--- Start Kernel 1 ---\r\n");
	run_kernel1_test();
	xil_printf("\r\n");

	xil_printf("--- Start Kernel 2 ---\r\n");
	run_kernel2_test();
	xil_printf("\r\n");

	xil_printf("--- Start Kernel 3 ---\r\n");
	run_kernel3_test();
	xil_printf("\r\n");

	xil_printf("--- Start Kernel 4 ---\r\n");
	run_kernel4_test();
	xil_printf("\r\n");

	xil_printf("=== MEASUREMENT FINISHED ===\r\n");

	while(1);
	return 0;
}
