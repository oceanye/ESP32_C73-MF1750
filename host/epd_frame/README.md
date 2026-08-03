# MF-1750 host frame core

This package is the hardware-independent reference for the application frame
contract. It has no third-party dependencies and performs no network, GPIO, or
serial I/O.

The canonical frame is `1024x600`, row-major, and 4 bits per pixel. Logical
`(0, 0)` is the top-left pixel; even x occupies the high nibble and odd x the
low nibble. Valid physical codes are black `0`, white `1`, yellow `2`, red `3`,
blue `5`, and green `6`.

Example:

```python
from host.epd_frame import ControllerMapping, controller_stream, generate_fixture

frame = generate_fixture("map-orient-v1")
cs1_dtm = controller_stream(frame, ControllerMapping(source_half=0))
cs2_dtm = controller_stream(frame, ControllerMapping(source_half=1))
```

Run the host regression suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

The package does not claim hardware validation. Physical mapping remains owned
by the firmware configuration and must be accepted on the panel at home.

