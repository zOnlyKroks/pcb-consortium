#include <cstdint>
#define SIGMA_WRITE_REGISTER_BLOCK SigmaWriteRegisterBlock

#define ADI_REG_TYPE const uint8_t

void SigmaWriteRegisterBlock(uint8_t devAddr,
                             uint16_t regAddr,
                             uint16_t length,
                             const uint8_t *data);