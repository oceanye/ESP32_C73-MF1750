from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_partial_hold_v4_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_v4_partial_dtm_is_exactly_120_complete_rows() -> None:
    report = pack.build_report()
    for action, window in zip(report["actions"][1:4], pack.WINDOWS):
        row_bytes = window.width // 2
        expected = bytes(
            [((window.cs1_code & 0x0F) << 4) | (window.cs1_code & 0x0F)]
        ) * (row_bytes * window.height)
        assert window.x % 2 == 0
        assert window.width % 2 == 0
        assert row_bytes == 80
        assert window.height == 120
        assert len(expected) == 9600
        assert action["cs1_dtm"]["bytes"] == len(expected)
        assert action["cs2_dtm"]["bytes"] == len(expected)
        assert action["cs1_dtm"]["sha256"] == hashlib.sha256(expected).hexdigest()
        assert action["cs2_dtm"]["sha256"] == hashlib.sha256(expected).hexdigest()


def test_v4_inclusive_endpoints_span_exact_window_geometry() -> None:
    report = pack.build_report()
    assert report["contract"]["geometry"]["ptlw_endpoint"] == "inclusive"
    for window in pack.WINDOWS:
        xe = window.x + window.width - 1
        ye = window.y + window.height - 1
        assert xe - window.x + 1 == window.width
        assert ye - window.y + 1 == window.height
    assert [
        (w.x, w.x + w.width - 1, w.y, w.y + w.height - 1) for w in pack.WINDOWS
    ] == [
        (48, 207, 64, 183),
        (304, 463, 240, 359),
        (48, 207, 416, 535),
    ]


def test_v4_has_no_host_drawn_border_or_guard_row() -> None:
    driver = (ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_driver.inc").read_text(
        encoding="utf-8"
    )
    # The expected-frame asset is a solid memset rectangle, not a framed box.
    assert "std::memset(frame +" in driver
    assert "pair, window.width / 2" in driver
    # The live partial stream is one uniform colour and exactly width*height/2.
    assert "phStreamUniformDtm(false, dtmBytes," in driver
    assert "phStreamUniformDtm(true, dtmBytes," in driver
    assert (
        "window->width) *\n                                    window->height / 2"
        in driver
    )
    assert "guard_rows" not in driver
    assert "guardRow" not in driver


def test_v4_current_transaction_does_not_repeat_ptlw_before_drf() -> None:
    driver = (ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_driver.inc").read_text(
        encoding="utf-8"
    )
    transaction = driver[driver.index("  const size_t roleIndex") :]
    assert transaction.count("phWritePartialWindow(*window)") == 1
    first_ptlw = transaction.index("phWritePartialWindow(*window)")
    cs1_dtm = transaction.index("phStreamUniformDtm(false")
    cs2_dtm = transaction.index("phStreamUniformDtm(true")
    pre_pon_cdi = transaction.index("epdCommand(CDI)", cs2_dtm)
    pre_pon_cdi_ff = transaction.index("epdData(0xFF)", pre_pon_cdi)
    refresh = transaction.index("epdSecondSettingAndRefresh()")
    assert first_ptlw < cs1_dtm < cs2_dtm < pre_pon_cdi < pre_pon_cdi_ff < refresh
    assert "phWritePartialWindow" not in transaction[cs2_dtm:refresh]

    shared = (ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
    refresh_body = shared[
        shared.index("bool epdSecondSettingAndRefresh()") : shared.index(
            "struct RevisionSample"
        )
    ]
    pon = refresh_body.index("epdCommand(PON)")
    btst2 = refresh_body.index("epdCommand(BTST2)")
    drf = refresh_body.index("epdCommand(DRF)")
    assert pon < btst2 < drf
    # The current shared refresher has no partial-window callback or 0x83
    # relock between a successful PON and DRF. The proposed diagnostic must
    # insert the relock here, not merely duplicate PTLW before PON.
    assert "phWritePartialWindow" not in refresh_body[pon:drf]
    assert "kPartialWindowCommand" not in refresh_body[pon:drf]
    assert "epdCommand(CDI)" not in refresh_body[pon:drf]


def test_gx_reference_relocks_ptlw_after_power_on_before_drf() -> None:
    gx = (ROOT / "tmp" / "GxEPD2_730c_GDEP073E01.cpp").read_text(encoding="utf-8")
    refresh = gx[
        gx.index("void GxEPD2_730c_GDEP073E01::refresh(int16_t x") : gx.index(
            "void GxEPD2_730c_GDEP073E01::powerOff()"
        )
    ]
    power_on = refresh.index("_PowerOn();")
    relock = refresh.index("_setPartialRamArea(x, y, w, h);")
    cdi = refresh.index("_writeCommand(0x50);")
    drf = refresh.index("_writeCommand(0x12);")
    assert power_on < relock < cdi < drf

    set_window = gx[
        gx.index("void GxEPD2_730c_GDEP073E01::_setPartialRamArea") : gx.index(
            "void GxEPD2_730c_GDEP073E01::_PowerOn()"
        )
    ]
    assert "uint16_t xe = x + w - 1;" in set_window
    assert "uint16_t ye = y + h; // controller issue (one more)" in set_window


def test_edge_guard_candidates_keep_original_colour_extent() -> None:
    for window in pack.WINDOWS:
        row_bytes = window.width // 2
        bottom_guard = {
            "ptlw_y0": window.y,
            "ptlw_y1": window.y + window.height,
            "colour_y0": window.y,
            "colour_y1": window.y + window.height - 1,
            "dtm_bytes": row_bytes * (window.height + 1),
        }
        symmetric_guard = {
            "ptlw_y0": window.y - 1,
            "ptlw_y1": window.y + window.height,
            "colour_y0": window.y,
            "colour_y1": window.y + window.height - 1,
            "dtm_bytes": row_bytes * (window.height + 2),
        }
        assert bottom_guard["ptlw_y1"] - bottom_guard["ptlw_y0"] + 1 == 121
        assert bottom_guard["dtm_bytes"] == 9680
        assert symmetric_guard["ptlw_y1"] - symmetric_guard["ptlw_y0"] + 1 == 122
        assert symmetric_guard["dtm_bytes"] == 9760
        assert bottom_guard["colour_y1"] - bottom_guard["colour_y0"] + 1 == 120
        assert symmetric_guard["colour_y1"] - symmetric_guard["colour_y0"] + 1 == 120
