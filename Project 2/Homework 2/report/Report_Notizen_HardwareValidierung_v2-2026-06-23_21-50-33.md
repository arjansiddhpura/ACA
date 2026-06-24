ACA Lab 2: Notizen

Zu main.c hinzugefügt:

// new includes

#include "xil_cache.h"        // From

hardware_platform/microblaze_0/standalone_domain/bsp/microblaze_0/include/

xil_chace.h

                                 // Required for enabling / disabling

caches

################################################################

int main()

{

    Xil_ICacheDisable();    // from xil_caches.h

    Xil_DCacheDisable();    // from xil_caches.h

...


    // Hint: "Small data arrays may already reside in the cache at the start

of the experiment"

    // -> Invalidate data-cache

    Xil_DcacheInvalidate();

}

Compiler optimization auf -O0 stellen: matrix_multiplication_app → C/C++ Build Settings → Optimization

Alle Optionen: Verschiedene Optimierungslevel & Caches disabled (Xil_IcacheDisable();

Xil_DcacheDisable();), nur einer an (Xil_IcacheEnable(); Xil_DcacheDisable();) oder beide enabled

(Alles nur einmal getestet, also keine guten mittelwerte. Aber einzeln mehrfach getestet und die ergebnisse unterscheiden sich nur selten um 0.0001s. Interessant war aber, dass wenn es unterschiede gab, immer IcacheEnable & DcacheDisable um 0.0001s schneller war als der rest. Das war aber bei mehrfachem laufen lassen nur sehr selten der fall)

<table border="1"><tr><td></td><td>Caches disabled</td><td>Instruction cache enabled</td><td>Data-cache enabled</td><td>Beide caches enabled</td></tr><tr><td>-O0</td><td>1.3545s</td><td>1.3545s</td><td>1.3545s</td><td>1.3545</td></tr><tr><td>-O1</td><td>0.6983s</td><td>0.6983s</td><td>0.6983s</td><td>0.6983s</td></tr><tr><td>-O2</td><td>0.6140s</td><td>0.6140s</td><td>0.6140s</td><td>0.6140s</td></tr><tr><td>-O3</td><td>0.6140s</td><td>0.6140s</td><td>0.6140s</td><td>0.6140s</td></tr></table>

In hardware_platform/microblaze_0/standalone_domain_bsp_microblaze_0/include/xparameters.h steht

#define XPAR_MICROBLAZE_USE_DCACHE 0

-> Vivado öffnen -> Im Blockdesing doppelklick auf MicrBlaze -> häcken bei "Use Instruction and Data

Caches -> Validate Desing ->

Critical Messages

There were two critical warning messages while validating this design.

Messages

[xilinx.com:ip:microblaze:11.0-24] /microblaze_0: No D-cache cacheable memory was found in the address space. Please either turn off the cache, add an IP core with cacheable memory to the design, or set external port address segment usage to memory.

[xilinx.com:ip:microblaze:11.0-24] /microblaze_0: No I-cache cacheable memory was found in the address space. Please either turn off the cache, add an IP core with cacheable memory to the design, or set external port address segment usage to memory.

OK

Open Messages View

-> connection automation -> die beiden neuen MicroBlaze Outputs M_AXI_DC und M_AXI_IC sind an die leitungen angeschlossen:

<div style='text-align: center;'><img src='https://maas-watermark-prod-new.cn-wlcb.ufileos.com/ocr%2Fcrop%2F202606240550197ff33505873b4cc1%2Fcrop_1_1782251431123.png?UCloudPublicKey=TOKEN_6df395df-5d8c-4f69-90f8-a4fe46088958&Signature=nh900Cp1jCpQaLzHOv3Wa2CTF40%3D&Expires=1782856231' alt='OCR图片'/></div>

<div align="center">

Hardwade geupdated -> #define XPAR_MICROBLAZE_USE_DCACHE 1

</div>

<div align="center">

Neue Messungen (alles nur einmal getestet / vereinzelt mehrfach)

</div>

<table border="1"><tr><td></td><td>Caches disabled</td><td>Instruction cache enabled</td><td>Data-cache enabled</td><td>Beide caches enabled</td></tr><tr><td>-O0</td><td>1.3545s</td><td>1.3545s</td><td>1.1637s</td><td>1.1637s</td></tr><tr><td>-O1</td><td>0.6983s</td><td>0.6982s</td><td>0.5025s</td><td>0.5024s/0.5025s</td></tr><tr><td>-O2</td><td>0.6140s</td><td>0.6140s</td><td>0.4870s</td><td>0.4870s</td></tr><tr><td>-O3</td><td>0.6140s</td><td>0.6140s</td><td>0.4870s</td><td>0.4870s</td></tr></table>