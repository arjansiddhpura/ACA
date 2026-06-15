#ifndef REG_UTILS_H
#define REG_UTILS_H

#include <stdint.h>

/**
 * @brief Sets specific bits in a memory-mapped register.
 * 
 * @param addr  The base address of the register.
 * @param bit   The bit mask to set (e.g., (1U << n)).
 */
void set_bit_in_reg(uint32_t addr, uint32_t bit);

/**
 * @brief Clears specific bits in a memory-mapped register.
 * 
 * @param addr  The base address of the register.
 * @param bit   The bit mask to clear (e.g., (1U << n)).
 */
void clear_bit_in_reg(uint32_t addr, uint32_t bit);

/**
 * @brief Writes a 32-bit value to a memory-mapped register.
 * 
 * @param addr   The base address of the register.
 * @param value  The value to write.
 */
void write_reg(uint32_t addr, uint32_t value);

/**
 * @brief Reads a 32-bit value from a memory-mapped register.
 * 
 * @param addr  The base address of the register.
 * @return uint32_t The value read.
 */
uint32_t read_reg(uint32_t addr);

#endif // REG_UTILS_H

