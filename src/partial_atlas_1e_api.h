#pragma once

// Partial-block route A (P0): compiled 1E multi-code atlas fixture.  The
// complete frame, layout, and 1E tuple identities are compiled into the
// binary and validated before any panel I/O.  This API accepts no frame,
// coordinate, colour code, LUT, voltage, timing, SPI-frequency, retry, or
// recovery parameter.
bool epdValidateCompiledPartialAtlas1EFixture();
bool epdDisplayCompiledPartialAtlas1E();
