#include <xil_printf.h>
#include "xparameters.h"
#include "reg_utils.h"

int main(void) {
	xil_printf("Hello World!");

	write_reg(XPAR_GPIO_0_BASEADDR + 0x4U, 0x1FF);

	while(1) {
		set_bit_in_reg(XPAR_GPIO_0_BASEADDR, 16);
		for (int i=0; i<10E6; i++);

		clear_bit_in_reg(XPAR_GPIO_0_BASEADDR, 16);
		for (int i=0; i<10E6; i++);
	}

}
