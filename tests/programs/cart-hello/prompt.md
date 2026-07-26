Write a Commodore 64 cartridge in ca65 assembly that prints `CART HELLO`
using the ROM character-output routine at $FFD2 as soon as the machine is
powered on, then keeps running. There is no BASIC stub and no load address:
the program is cartridge-native, exports `cart_main`, and is built into a
bootable 8K `.crt` whose CBM80 boot header is generated for it.
