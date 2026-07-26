Write a bank-switched EasyFlash cartridge for the Commodore 64. Put the
entry point in bank 0 and a routine that sets the border colour in bank 1,
call across the bank boundary, and return. Both cartridge windows switch
together, so the cross-bank call has to go through a trampoline in RAM;
`cart.inc` supplies one, along with the `$9F00` jump-table convention that
lets a caller name an entry index instead of an address. Describe the banks
in an `.ef.yaml` manifest and build it with `c64 cart build`.
