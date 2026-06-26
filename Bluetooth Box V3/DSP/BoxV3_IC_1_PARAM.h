/*
 * File:           C:\Users\finnr\Desktop\pcb-consortium\Bluetooth Box V3\DSP\BoxV3_IC_1_PARAM.h
 *
 * Created:        Friday, June 26, 2026 9:29:15 AM
 * Description:    BoxV3:IC 1 parameter RAM definitions.
 *
 * This software is distributed in the hope that it will be useful,
 * but is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
 * CONDITIONS OF ANY KIND, without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 *
 * This software may only be used to program products purchased from
 * Analog Devices for incorporation by you into audio products that
 * are intended for resale to audio product end users. This software
 * may not be distributed whole or in any part to third parties.
 *
 * Copyright ©2026 Analog Devices, Inc. All rights reserved.
 */
#ifndef __BOXV3_IC_1_PARAM_H__
#define __BOXV3_IC_1_PARAM_H__


/* Module W Noise1 - White Noise*/
#define MOD_WNOISE1_COUNT                              3
#define MOD_WNOISE1_DEVICE                             "IC1"
#define MOD_WNOISE1_ALG0_ENABLENOISE_ADDR              0
#define MOD_WNOISE1_ALG0_ENABLENOISE_FIXPT             0x00800000
#define MOD_WNOISE1_ALG0_ENABLENOISE_VALUE             SIGMASTUDIOTYPE_FIXPOINT_CONVERT(1)
#define MOD_WNOISE1_ALG0_ENABLENOISE_TYPE              SIGMASTUDIOTYPE_FIXPOINT
#define MOD_WNOISE1_ALG0_SEED_ADDR                     1
#define MOD_WNOISE1_ALG0_SEED_FIXPT                    0x0005464B
#define MOD_WNOISE1_ALG0_SEED_VALUE                    SIGMASTUDIOTYPE_INTEGER_CONVERT(345675)
#define MOD_WNOISE1_ALG0_SEED_TYPE                     SIGMASTUDIOTYPE_INTEGER
#define MOD_WNOISE1_ALG0_SEED_ADDR                     1
#define MOD_WNOISE1_ALG0_SEED_FIXPT                    0x0005464B
#define MOD_WNOISE1_ALG0_SEED_VALUE                    SIGMASTUDIOTYPE_INTEGER_CONVERT(345675)
#define MOD_WNOISE1_ALG0_SEED_TYPE                     SIGMASTUDIOTYPE_INTEGER

/* Module W Noise2 - White Noise*/
#define MOD_WNOISE2_COUNT                              3
#define MOD_WNOISE2_DEVICE                             "IC1"
#define MOD_WNOISE2_ALG0_ENABLENOISE_ADDR              2
#define MOD_WNOISE2_ALG0_ENABLENOISE_FIXPT             0x00800000
#define MOD_WNOISE2_ALG0_ENABLENOISE_VALUE             SIGMASTUDIOTYPE_FIXPOINT_CONVERT(1)
#define MOD_WNOISE2_ALG0_ENABLENOISE_TYPE              SIGMASTUDIOTYPE_FIXPOINT
#define MOD_WNOISE2_ALG0_SEED_ADDR                     3
#define MOD_WNOISE2_ALG0_SEED_FIXPT                    0x0005464B
#define MOD_WNOISE2_ALG0_SEED_VALUE                    SIGMASTUDIOTYPE_INTEGER_CONVERT(345675)
#define MOD_WNOISE2_ALG0_SEED_TYPE                     SIGMASTUDIOTYPE_INTEGER
#define MOD_WNOISE2_ALG0_SEED_ADDR                     3
#define MOD_WNOISE2_ALG0_SEED_FIXPT                    0x0005464B
#define MOD_WNOISE2_ALG0_SEED_VALUE                    SIGMASTUDIOTYPE_INTEGER_CONVERT(345675)
#define MOD_WNOISE2_ALG0_SEED_TYPE                     SIGMASTUDIOTYPE_INTEGER

#endif
