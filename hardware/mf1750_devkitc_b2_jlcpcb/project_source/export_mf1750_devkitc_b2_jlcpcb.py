"""Export the fail-closed JLCPCB engineering-first-article package for MF1750 B2.

This module is generated from the mature B1 exporter but is intentionally a
separate B2 release tool.  The verified B2 PCB/SCH are immutable inputs.  A
temporary manufacturing variant removes paste only from DNP R15, while the
canonical board, fitted R16, copper, mask, holes, and outline remain unchanged.
"""

from __future__ import annotations

# The implementation is kept in the sibling implementation module so this
# project-specific release entry point stays obvious and import-safe.
from export_mf1750_devkitc_b2_jlcpcb_impl import main


if __name__ == "__main__":
    main()
