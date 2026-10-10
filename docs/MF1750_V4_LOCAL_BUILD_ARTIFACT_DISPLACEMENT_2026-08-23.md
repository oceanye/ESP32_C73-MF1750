# MF1750 strict-V4 local build artifact displacement

- Scope: local offline build tree only; no relay, serial/COM, device HTTP,
  flashing, reset, or display refresh was performed.
- The already-executed strict-V4 evidence and runner remain immutably bound to
  the original 793728-byte BIN SHA-256
  `e3315ba1a337e041c156728693c4db92c9463ef195296ebaef351b7c07e5ad9c`.
- During offline regression checking, PlatformIO rebuilt the same local V4
  output path.  The resulting 793728-byte local BIN has SHA-256
  `884e89006438d9ca33a0bb237d087670ee461f1113066d671bd669807dbb7e4f`.
- The rebuilt hash is **not** rebound, authorized, canonical, or substituted
  into any prior V4 runner/evidence.  Do not use the displaced local V4 BIN for
  an action claiming the original identity.
- Strict-V4 source was restored after the check.  The new post-PON repeat-PTLW
  experiment is maintained in independent source files and an independent
  PlatformIO build directory.
