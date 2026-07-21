# PET memory maps (per model)

All addresses hex. "All models" unless noted. I/O region details:
references/hardware.md. Generate annotated ROM listings with `c64 rom disasm`.

| Range       | What                                                    |
|-------------|---------------------------------------------------------|
| 0000-00FF   | Zero page (BASIC/kernal workspace — see zero-page.md)   |
| 0100-01FF   | 6502 stack                                              |
| 0200-03FF   | OS variables, input buffer, keyboard buffer, tape bufs  |
| 0401-RAMTOP | BASIC program text, then variables/arrays/strings       |
| 8000-83E7   | Screen RAM, 40-column models (1000 bytes)               |
| 8000-87CF   | Screen RAM, 80-column models (2000 bytes)               |
| 9000-AFFF   | Expansion ROM sockets ($9000, $A000)                    |
| B000-DFFF   | BASIC 4.0 ROM (BASIC 2.0: C000-DFFF; B000 socket free)  |
| E000-E7FF   | Screen editor ROM                                       |
| E800-EFFF   | I/O: PIA1 E810, PIA2 E820, VIA E840, CRTC E880          |
| F000-FFFF   | Kernal ROM; vectors NMI FFFA, RESET FFFC, IRQ FFFE      |

Model notes:
- pet2001: BASIC 1.0, 40 col. pet3032: BASIC 2.0, 40 col, RAM to $7FFF.
- pet4032: BASIC 4.0, 40 col, CRTC. pet8032: BASIC 4.0, 80 col, CRTC.
- pet8296: BASIC 4.0, 80 col; extra banked RAM under control of $FFF0
  (8096-style expansion) — treat $0401-$7FFF as normal BASIC RAM unless
  you are deliberately banking.
- The CRTC ($E880/$E881) exists on 4032/8032/8296 ("CRTC models") only.
