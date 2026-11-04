# Memory structures of Zeus.exe (GOG)

Source of truth for field names shared by all RE docs. Add fields as they are verified.
Base layout from refs/zeus-poseidon-arm64/formats/sav.md (save-block table = simulation state).

## Building record — `buildings[4000]` at `0x0092E658`, 280 (0x118) bytes, index 0 unused
| Off | Type | Name | Status / evidence |
|---|---|---|---|
| +0x00 | u8 | state (0 free, 3 on creation, 1 active) | verified (sav.md) |
| +0x06,+0x08 | i16 | x, y | verified |
| +0x0C | i32 | tile index | verified |
| +0x10 | i16 | type (BUILD_* id, = model row) | verified |
| +0x12 | i16 | house level (type−2 for houses) | verified (0x00484660) |
| +0x16 | i16 | creation serial | verified |
| +0x32 | u8 | per-type: sanctuary_activity months (sanctuaries); spawn timer (service buildings) | verified (religion, services) |
| +0x35 | u8 | has water | verified (evolve check vs col 3) |
| +0x54 | i16[] | goods held (slot per resource) | verified (evolve check) |
| +0x64 | i16 | wine held | verified |
| +0x66 | i16 | oil held | verified |
| +0x68 | i16 | fleece held | verified |
| +0x6A | i16 | arms held | verified |
| +0x6C | u8 | education/stadium access | verified (vs col 4) |
| +0x72 | i16 | horses held | verified |
| +0x80 | i8 | culture/appeal level | verified (vs col 2) |
| +0x83 | u8 | house evolve reason code | verified |
| +0xCE | i8 | desirability at the house | verified |

## Figure record — `figures[2000]` at `0x00DBD788`, 388 bytes
See sav.md "Personnage" table; to be extended.

## God records — 14 × 52 bytes at `0x00EF5DD8`
+0x14 = god id (→ sanctuary type via `0x004E8B40`: 0→84 Zeus … ). God order 0 Zeus … 6 Aphrodite … 10 Dionysus … 13 Atlas (verified, religion.md).

## Grids — 228 × 228 = 51,984 tiles, index = 0x00DA2F80 + 228*y + x
See sav.md ranks 15–27, 99–112.
