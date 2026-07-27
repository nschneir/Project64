; data.s: not code — the DATA file loader.s pulls off the disk at runtime.
;
; The LOADADDR segment is the file's 2-byte PRG header, and under secondary
; address 1 that header is the ONLY thing that decides where LOAD puts the
; payload. $C000 is the free 4K block above BASIC's RAM, so the load cannot
; disturb the program that asked for it.
;
; A data file assembled rather than committed as a binary: the header is the
; subject of the test, and two bytes of a `.d64`-adjacent blob are exactly the
; kind of thing nobody re-checks. `c64 disk build` assembles `.s` entries, so
; the manifest stays a plain list of files either way.

        .segment "LOADADDR"
        .word   $C000

        .segment "CODE"
        .byte   "DISK LOAD OK", $0D, $00
