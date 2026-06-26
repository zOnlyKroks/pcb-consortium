/**********************************************|
| SigmaDSP library                             |
| https://github.com/MCUdude/SigmaDSP          |
|                                              |
| 0_Template.ino                               |
| This example is ment to be used as a         |
| template for your own projects. It provide   |
| no functionality other than connecting the   |
| two analog inputs directly to output 0 and 1 |
|**********************************************/

// Include Wire and SigmaDSP library
#include <Wire.h>
#include <SigmaDSP.h>

#include "../SigmaDSP_parameters.h"

static constexpr int SDA_PIN = 14;
static constexpr int SCL_PIN = 26;

SigmaDSP dsp(Wire, DSP_I2C_ADDRESS, 48000.00f /*,12*/);

void setup()
{
  Serial.begin(9600);
  Serial.println(F("SigmaDSP 0_Template example\n"));

  pinMode(4, OUTPUT);

  Wire.begin(SDA_PIN, SCL_PIN, 100000);
  dsp.begin();

  delay(2000);

  Serial.println(F("Pinging i2c lines...\n0 -> deveice is present\n2 -> device is not present"));
  Serial.print(F("DSP response: "));
  Serial.println(dsp.ping());


  Serial.print(F("\nLoading DSP program... "));
  loadProgram(dsp);
  Serial.println("Done!\n");
}


void loop()
{
  digitalWrite(4, HIGH);
}