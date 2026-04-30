#define SIGMA_WRITE_REGISTER_BLOCK SigmaWriteRegisterBlock

void SigmaWriteRegisterBlock(uint8_t devAddr,
                             uint16_t regAddr,
                             uint16_t length,
                             uint8_t *data);