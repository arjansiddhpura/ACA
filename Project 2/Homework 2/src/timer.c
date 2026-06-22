#include <xparameters.h>
#include <xio.h>
#include "timer.h"

void configure_timer() {
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR), (1 << 11));
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR + 0x4), 0);
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR + 0x14), 0);
}

void clear_timer() {
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR), (1 << 5));
}

void start_timer() {
    clear_timer();
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR), (1 << 11) | (1 << 7));
}

double stop_timer() {
    double t;
    long long unsigned int upper;
    long unsigned int lower;
    XIo_Out32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR), (1 << 11));

    upper = ((long long unsigned int)XIo_In32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR + 0x18))) << 32;
    lower = XIo_In32((volatile u32 *)(XPAR_AXI_TIMER_0_BASEADDR + 0x8));
    t = (double)(upper + lower);
    t = t / XPAR_MICROBLAZE_CORE_CLOCK_FREQ_HZ;

    return t;
}
