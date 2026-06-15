#include "reg_utils.h"
#include "xio.h"  // or "xil_io.h" depending on your platform

void set_bit_in_reg(uint32_t addr, uint32_t bit)
{
    uint32_t val = XIo_In32((volatile uint32_t *)addr);
    val |= (1 << bit);
    XIo_Out32((volatile uint32_t *)addr, val);
}

void clear_bit_in_reg(uint32_t addr, uint32_t bit)
{
    uint32_t val = XIo_In32((volatile uint32_t *)addr);
    val &= ~(1 << bit);
    XIo_Out32((volatile uint32_t *)addr, val);
}

void write_reg(uint32_t addr, uint32_t value)
{
    XIo_Out32((volatile uint32_t *)addr, value);
}

uint32_t read_reg(uint32_t addr)
{
    return XIo_In32((volatile uint32_t *)addr);
}

