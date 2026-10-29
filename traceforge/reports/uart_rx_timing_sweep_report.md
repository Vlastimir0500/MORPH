# TRACEFORGE UART RX Timing Sweep

- Payload: `0xA6`
- Nominal bit period: 436 cycles
- Swept periods: 400–470 cycles, step 1
- Cases: 71
- Cycle-by-cycle RTL/model mismatches: 0

## Classification counts

- `correct_decode`: 54
- `silent_misdecode`: 17

## Correct-decode period ranges

Ranges include only periods that decoded the expected byte without an error flag or core fault.

- 410–463 cycles

## Individual results

| Period | Shift register | Error flag | Classification | RTL/model match |
|---:|---|---|---|---|
| 400 | 0x6B | False | silent_misdecode | True |
| 401 | 0x63 | False | silent_misdecode | True |
| 402 | 0x63 | False | silent_misdecode | True |
| 403 | 0x63 | False | silent_misdecode | True |
| 404 | 0x63 | False | silent_misdecode | True |
| 405 | 0x63 | False | silent_misdecode | True |
| 406 | 0x67 | False | silent_misdecode | True |
| 407 | 0x67 | False | silent_misdecode | True |
| 408 | 0x67 | False | silent_misdecode | True |
| 409 | 0x67 | False | silent_misdecode | True |
| 410 | 0x65 | False | correct_decode | True |
| 411 | 0x65 | False | correct_decode | True |
| 412 | 0x65 | False | correct_decode | True |
| 413 | 0x65 | False | correct_decode | True |
| 414 | 0x65 | False | correct_decode | True |
| 415 | 0x65 | False | correct_decode | True |
| 416 | 0x65 | False | correct_decode | True |
| 417 | 0x65 | False | correct_decode | True |
| 418 | 0x65 | False | correct_decode | True |
| 419 | 0x65 | False | correct_decode | True |
| 420 | 0x65 | False | correct_decode | True |
| 421 | 0x65 | False | correct_decode | True |
| 422 | 0x65 | False | correct_decode | True |
| 423 | 0x65 | False | correct_decode | True |
| 424 | 0x65 | False | correct_decode | True |
| 425 | 0x65 | False | correct_decode | True |
| 426 | 0x65 | False | correct_decode | True |
| 427 | 0x65 | False | correct_decode | True |
| 428 | 0x65 | False | correct_decode | True |
| 429 | 0x65 | False | correct_decode | True |
| 430 | 0x65 | False | correct_decode | True |
| 431 | 0x65 | False | correct_decode | True |
| 432 | 0x65 | False | correct_decode | True |
| 433 | 0x65 | False | correct_decode | True |
| 434 | 0x65 | False | correct_decode | True |
| 435 | 0x65 | False | correct_decode | True |
| 436 | 0x65 | False | correct_decode | True |
| 437 | 0x65 | False | correct_decode | True |
| 438 | 0x65 | False | correct_decode | True |
| 439 | 0x65 | False | correct_decode | True |
| 440 | 0x65 | False | correct_decode | True |
| 441 | 0x65 | False | correct_decode | True |
| 442 | 0x65 | False | correct_decode | True |
| 443 | 0x65 | False | correct_decode | True |
| 444 | 0x65 | False | correct_decode | True |
| 445 | 0x65 | False | correct_decode | True |
| 446 | 0x65 | False | correct_decode | True |
| 447 | 0x65 | False | correct_decode | True |
| 448 | 0x65 | False | correct_decode | True |
| 449 | 0x65 | False | correct_decode | True |
| 450 | 0x65 | False | correct_decode | True |
| 451 | 0x65 | False | correct_decode | True |
| 452 | 0x65 | False | correct_decode | True |
| 453 | 0x65 | False | correct_decode | True |
| 454 | 0x65 | False | correct_decode | True |
| 455 | 0x65 | False | correct_decode | True |
| 456 | 0x65 | False | correct_decode | True |
| 457 | 0x65 | False | correct_decode | True |
| 458 | 0x65 | False | correct_decode | True |
| 459 | 0x65 | False | correct_decode | True |
| 460 | 0x65 | False | correct_decode | True |
| 461 | 0x65 | False | correct_decode | True |
| 462 | 0x65 | False | correct_decode | True |
| 463 | 0x65 | False | correct_decode | True |
| 464 | 0x64 | False | silent_misdecode | True |
| 465 | 0x64 | False | silent_misdecode | True |
| 466 | 0x64 | False | silent_misdecode | True |
| 467 | 0x64 | False | silent_misdecode | True |
| 468 | 0x66 | False | silent_misdecode | True |
| 469 | 0x66 | False | silent_misdecode | True |
| 470 | 0x66 | False | silent_misdecode | True |

This is an empirical sweep for the tested payload and receiver program. It is not a universal UART timing guarantee.

Production RTL SHA-256: `6a395e2d635920070fd31c1c20c9722e4aafcad64c8c37a3921dd26ef5399552`

