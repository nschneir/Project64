; Bank 0 HIROM — the boot window. An EasyFlash cart powers up in Ultimax mode
; and the CPU takes RESET from $FFFC, which lives here; the CBM80 signature is
; never scanned.
;
; The file has no code on purpose. The manifest must still give bank 0 a `hi:`
; window — the build refuses a manifest without one, because that is where the
; reset vector has to come from — but the boot code itself is generated:
; `c64 cart build` links a stub into this window that includes cart.inc and
; points $FFFA/$FFFC/$FFFE at its ef_boot. Including cart.inc here as well
; only adds a second, never-executed copy of the resident block (89 bytes of
; dead ROM, measured): the vectors resolve against the stub's copy.
;
; This file is the author's hook for code that must live in bank 0 HI —
; anything put here links alongside the generated stub. Declaring a STARTUP
; segment in it suppresses the stub and takes over the boot sequence instead.
