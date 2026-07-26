; Bank 0 HIROM — the boot window. An EasyFlash cart powers up in Ultimax mode
; and the CPU takes RESET from $FFFC, which lives here; the CBM80 signature is
; never scanned. cart.inc supplies ef_boot and the resident trampoline, and
; `c64 cart build` generates the vectors that point at ef_boot.
.include "cart.inc"
