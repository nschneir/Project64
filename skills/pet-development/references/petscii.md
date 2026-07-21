# PET text encodings: ASCII, PETSCII, screen codes

The PET uses three distinct byte encodings. The ground-truth conversion tables
live in `c64lib.text` (`ascii_to_petscii`, `screen_code_to_char`); this doc
describes them.

## The three encodings

- **ASCII** — host files and the CLI.
- **PETSCII** — the keyboard and ROM I/O routines (CHROUT/CHRIN). RETURN is
  `$0D`; letters use ASCII-uppercase codes.
- **Screen codes** — the bytes actually stored in screen RAM at `$8000`. These
  are **not** PETSCII.

`c64 screen` decodes screen RAM to text automatically. `c64 mem read '$8000'`
shows the raw screen codes.

## Screen-code table (uppercase/graphics set)

| Codes  | Characters                                             |
|--------|--------------------------------------------------------|
| 0      | `@`                                                    |
| 1–26   | `A`–`Z`                                                |
| 27–31  | `[` `\` `]` up-arrow left-arrow                         |
| 32–63  | matches ASCII `$20`–`$3F` (space, punctuation, digits) |
| 64–127 | graphics characters (enumerated below)                 |

Bit 7 (`+128`) means **reverse video**; strip it before decoding (screen code
`$81` is a reverse-video `A`, i.e. the same glyph as `1`).

The low 32 letters/symbols spell out, in order:
`@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]` then up-arrow and left-arrow.

## Graphics characters (codes 64–127)

Codes 64–127 are the PET's built-in graphics: line- and box-drawing pieces,
block/quadrant fills, shading, playing-card suits, and a few symbols. Codes
192–255 are the same 64 glyphs in **reverse video** (`code & $7F` gives the
base glyph; e.g. `$A0` = 160 is a reverse-video space, i.e. a solid block).

**How `c64 screen` renders them.** The text decoder only maps four graphics
codes to plain ASCII — **64 → `-`**, **66 → `|`**, **91 → `+`**, **96 → space**
— and strips the reverse-video bit first (so a solid block, code 160, decodes
to a blank space, and can vanish against the background). **Every other
graphics code decodes to a `·` placeholder**, so text output can't tell them
apart. To see any glyph exactly, poke it and screenshot the real machine:
`c64 mem write '$8000' 90` then `c64 screen --png out.png`.

The table below is read from the PET character ROM (BASIC 4). Row/column
positions count 0–7 within the 8×8 cell.

| Code | $hex | Glyph / description                         | Code | $hex | Glyph / description                        |
|------|------|---------------------------------------------|------|------|--------------------------------------------|
| 64   | $40  | horizontal line, centre (→ `-`)             | 96   | $60  | shifted space — blank (→ space)            |
| 65   | $41  | ♠ spade                                     | 97   | $61  | ▌ left half block (cols 0–3)               |
| 66   | $42  | vertical line, centre (→ `\|`)              | 98   | $62  | ▄ lower half block (rows 4–7)              |
| 67   | $43  | horizontal line, one above centre           | 99   | $63  | ▔ top-edge line (row 0)                    |
| 68   | $44  | horizontal line, upper                      | 100  | $64  | ▁ bottom-edge line (row 7)                 |
| 69   | $45  | horizontal line, near top                   | 101  | $65  | ▏ left-edge line (col 0)                   |
| 70   | $46  | horizontal line, lower                      | 102  | $66  | ▒ checkerboard (medium shade)              |
| 71   | $47  | vertical line, left of centre               | 103  | $67  | ▕ right-edge line (col 7)                  |
| 72   | $48  | vertical line, right of centre              | 104  | $68  | checkerboard, lower half                   |
| 73   | $49  | rounded corner: left edge → down            | 105  | $69  | ◤ filled triangle, upper-left              |
| 74   | $4A  | rounded corner: top → right edge            | 106  | $6A  | right quarter block (cols 6–7)             |
| 75   | $4B  | rounded corner: top → left edge             | 107  | $6B  | ├ vertical, branch right                   |
| 76   | $4C  | └ bottom-left corner (left+bottom edges)    | 108  | $6C  | ▗ lower-right quadrant block               |
| 77   | $4D  | ╲ diagonal, top-left to bottom-right        | 109  | $6D  | centre corner: arms up + right             |
| 78   | $4E  | ╱ diagonal, bottom-left to top-right        | 110  | $6E  | centre corner: arms left + down            |
| 79   | $4F  | ┌ top-left corner (top+left edges)          | 111  | $6F  | bottom quarter block (rows 6–7)            |
| 80   | $50  | ┐ top-right corner (top+right edges)        | 112  | $70  | centre corner: arms right + down           |
| 81   | $51  | ● filled circle (disc)                      | 113  | $71  | ┴ T-junction, branch up                    |
| 82   | $52  | horizontal line, low (row 6)                | 114  | $72  | ┬ T-junction, branch down                  |
| 83   | $53  | ♥ heart                                      | 115  | $73  | ┤ T-junction, branch left                  |
| 84   | $54  | vertical line, near left (col 1)            | 116  | $74  | left quarter block (cols 0–1)              |
| 85   | $55  | rounded corner: right edge → down           | 117  | $75  | left three-eighths block (cols 0–2)        |
| 86   | $56  | ╳ diagonal cross (X)                        | 118  | $76  | right three-eighths block (cols 5–7)       |
| 87   | $57  | ○ hollow circle                             | 119  | $77  | top quarter block (rows 0–1)               |
| 88   | $58  | ♣ club                                      | 120  | $78  | upper three-eighths block (rows 0–2)       |
| 89   | $59  | vertical line, near right (col 6)           | 121  | $79  | lower three-eighths block (rows 5–7)       |
| 90   | $5A  | ♦ diamond                                   | 122  | $7A  | ┘ bottom-right corner (right+bottom edges) |
| 91   | $5B  | ┼ cross / plus (→ `+`)                      | 123  | $7B  | ▖ lower-left quadrant block                |
| 92   | $5C  | light diagonal hatch (left half)            | 124  | $7C  | ▝ upper-right quadrant block               |
| 93   | $5D  | vertical line, centre (col 4)               | 125  | $7D  | centre corner: arms up + left              |
| 94   | $5E  | π (greek pi)                                | 126  | $7E  | ▘ upper-left quadrant block                |
| 95   | $5F  | ◥ filled triangle, upper-right              | 127  | $7F  | ▚ opposite quadrants (upper-left+lower-right)|

## PETSCII for keyboard input

When feeding the keyboard (as `c64 basic type` and `c64 key` do), text is
converted to PETSCII: `\n` → `$0D` (RETURN), letters → ASCII uppercase. Writing
lowercase source is the norm because lowercase ASCII → unshifted PETSCII, which
shows as uppercase on screen.

Only characters in the PET set are available. `ascii_to_petscii` (used by
`c64 basic type` and `c64 key type`) rejects anything it can't map rather
than mangling it — so "smart" typography like the em dash (`—`) or curly
quotes must be spelled with their plain ASCII equivalents (`-`, `"`).

## How `c64 screen` decodes the screen

`c64 screen` reads screen RAM and maps each screen code to text
(`c64lib.text.screen_code_to_char`). Since v1.2 the default style is
**unicode**: graphics decode to real box-drawing / block-element /
geometric glyphs, so mazes, sprites, and blobs read naturally. The rules:

1. **Graphics map to Unicode equivalents.** Lines/corners/tees become
   `─ │ ╭ ╮ ╰ ╯ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼`, blocks and quadrants become
   `▌ ▄ ▖ ▗ ▘ ▝ ▚`, shapes become `● ○ ♥ ◆ ♠ ♣ ▒ ╲ ╱ ╳ ◣ ◤`.
2. **Reverse video keeps the base glyph — except where Unicode has the
   pixel complement.** Reverse `A` ($81) reads as `A`, but reverse-space
   $A0 (the solid block) decodes as `█`, reverse half-blocks flip
   (`▌`↔`▐`, `▄`↔`▀`), reverse quadrants become three-quarter blocks
   (`▛ ▜ ▙ ▟`), and reverse ball/ring become `◘ ◙`. Pass
   `--ansi-reverse` to wrap the remaining reverse cells in terminal
   inverse-video escapes.
3. **Genuinely unmappable graphics become `·`.** And `--style ascii`
   restores the old conservative mapping (all graphics collapse to `·`
   except `- | +`).

Letters, digits, and punctuation round-trip faithfully — text output is
fully trustworthy. When you need exact glyph identity (e.g. asserting a
specific character code, not its look-alike), read the numbers instead:
`c64 screen --codes` prints the raw screen-code matrix, or
`c64 mem get $80D2` for row 5, column 10 on a 40-column model (row stride
80 on 80-column models), or use `c64 screen --png` when pixel appearance
matters.
