"""OpenCV side panel for live matches, records, and audit activity."""

import cv2
import numpy


PANEL_WIDTH = 420
BLUE = (138, 74, 0)  # OpenCV BGR for #004A8A
WHITE = (235, 235, 235)
MUTED = (150, 150, 150)
GREEN = (70, 220, 120)
RED = (80, 80, 235)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def render_live_window(
    frame, states, selected_track_id, events, window_size, license_result=None
):
    window_width, window_height = window_size
    if window_width <= 0 or window_height <= 0:
        return frame
    panel_width = min(round(PANEL_WIDTH * window_height / 720), window_width // 2)
    camera_width = window_width - panel_width
    canvas = numpy.zeros((window_height, window_width, 3), dtype=numpy.uint8)
    scale = min(camera_width / frame.shape[1], window_height / frame.shape[0])
    width, height = round(frame.shape[1] * scale), round(frame.shape[0] * scale)
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(frame, (width, height), interpolation=interpolation)
    left, top = (camera_width - width) // 2, (window_height - height) // 2
    canvas[top : top + height, left : left + width] = resized
    _draw_panel(
        canvas[:, camera_width:], states, selected_track_id, events, license_result
    )
    return canvas


def _draw_panel(panel, states, selected_track_id, events, license_result):
    cv2.line(panel, (0, 0), (0, panel.shape[0]), BLUE, max(1, round(2 * _scale(panel))))
    left = 20

    _text(panel, "LIVE ACTIVITY", left, 34, BLUE, 0.72, 2)
    matched_ids = [track_id for track_id, state in states.items() if state.name]
    state = states.get(selected_track_id) if selected_track_id in matched_ids else None

    if license_result:
        _draw_license(panel, license_result, left, 72)
    elif state:
        _text(panel, f"SUBJECT {selected_track_id}", left, 72, MUTED, 0.48)
        _text(panel, _clip(state.name, 31), left, 101, WHITE, 0.67, 2)
        _text(panel, f"IDENTITY MATCH  {state.similarity:.2f}", left, 127, GREEN, 0.47)
        if len(matched_ids) > 1:
            _text(panel, "TAB cycles matched subjects", left, 150, MUTED, 0.4)
        records_top = 182
        _text(panel, "SYNTHETIC CRIMINAL RECORDS", left, records_top, BLUE, 0.48, 2)
        _draw_records(panel, state, left, records_top + 29)
    else:
        _text(panel, "WAITING FOR IDENTITY MATCH", left, 78, WHITE, 0.48)
        y = 111
        active_states = [(track_id, state) for track_id, state in states.items() if state.active]
        for track_id, active_state in active_states[-5:]:
            status = (active_state.status or "detected").replace("_", " ").upper()
            _text(panel, f"SUBJECT {track_id}  {status}", left, y, MUTED, 0.42)
            y += 24

    timeline_top = 505
    factor = _scale(panel)
    cv2.rectangle(
        panel,
        (round(factor), round((timeline_top - 25) * factor)),
        (panel.shape[1], panel.shape[0]),
        (8, 8, 8),
        -1,
    )
    _text(panel, "EVENT LOG", left, timeline_top, BLUE, 0.48, 2)
    available = (720 - timeline_top - 12) // 25
    y = timeline_top + 27
    for event in events[-available:]:
        timestamp = event.get("timestamp", "")[11:19]
        message = _clip(event.get("message", ""), 36)
        _text(panel, f"{timestamp}  {message}", left, y, WHITE, 0.44)
        y += 25


def _draw_license(panel, result, left, top):
    scan, record = result.scan, result.record or {}
    value = lambda name: record.get(name) or getattr(scan, name)
    name = " ".join(filter(None, (value("first_name"), value("last_name"))))
    status, color = {
        "searching": ("SEARCHING DMV RECORDS...", WHITE),
        "license_found": ("DMV RECORD FOUND", GREEN),
        "license_expired": ("LICENSE EXPIRED", RED),
        "license_mismatch": ("DMV DATA MISMATCH", RED),
        "license_not_found": ("NO DMV RECORD FOUND", RED),
        "lookup_unavailable": ("DMV LOOKUP UNAVAILABLE", RED),
    }[result.status]

    _text(panel, "SCANNED DRIVER LICENSE", left, top, BLUE, 0.5, 2)
    _text(panel, _clip(name or "UNKNOWN NAME", 31), left, top + 34, WHITE, 0.65, 2)
    _text(panel, status, left, top + 66, color, 0.46, 2)
    lines = (
        ("NUMBER", value("number")),
        ("STATE", value("state")),
        ("DATE OF BIRTH", value("date_of_birth")),
        ("ISSUED", value("issue_date")),
        ("EXPIRES", value("expiration_date")),
        ("SEX", value("sex")),
    )
    y = top + 101
    for label, item in lines:
        if item:
            _text(panel, f"{label}: {_clip(str(item).upper(), 25)}", left, y, WHITE, 0.44)
            y += 25
    if result.mismatches:
        fields = ", ".join(name.replace("_", " ") for name in result.mismatches)
        _text(panel, _clip("MISMATCH: " + fields.upper(), 34), left, y + 6, RED, 0.4, 2)


def _draw_records(canvas, state, left, top):
    status = state.records_status
    if status == "searching":
        _text(canvas, "Searching records...", left, top, WHITE, 0.46)
        return
    if status == "records_unavailable":
        _text(canvas, "RECORDS SYSTEM UNAVAILABLE", left, top, RED, 0.44, 2)
        return
    if status == "no_records":
        _text(canvas, "No synthetic records returned", left, top, WHITE, 0.44)
        return
    if status != "records_found" or not state.records:
        _text(canvas, "Awaiting records lookup", left, top, MUTED, 0.44)
        return

    record = state.records[0]
    lines = [
        ("STATUS", record.get("record_status", "unspecified")),
        ("WANTED LEVEL", record.get("wanted_level", 0)),
        ("ACTIVE WARRANT", _boolean(record.get("active_warrant"))),
        ("PRIMARY OFFENSE", record.get("primary_offense")),
        ("WARRANT", record.get("warrant_number")),
        ("ARRESTS", record.get("arrest_count", 0)),
        ("CONVICTIONS", record.get("conviction_count", 0)),
        ("LAST ARREST", record.get("last_arrest_date")),
        ("WARRANT ISSUED", record.get("warrant_issue_date")),
    ]
    y = top
    if len(state.records) > 1:
        _text(canvas, f"{len(state.records)} RECORDS RETURNED", left, y, WHITE, 0.42)
        y += 25
    for label, value in lines:
        if value is None or y >= 475:
            continue
        color = RED if label == "ACTIVE WARRANT" and value == "YES" else WHITE
        _text(canvas, f"{label}: {_clip(str(value).upper(), 28)}", left, y, color, 0.42)
        y += 24


def _boolean(value):
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return "UNKNOWN"


def _clip(value, length):
    value = str(value)
    return value if len(value) <= length else value[: length - 1] + "…"


def _text(image, text, x, y, color, scale, thickness=1):
    factor = _scale(image)
    cv2.putText(
        image,
        text,
        (round(x * factor), round(y * factor)),
        FONT,
        scale * factor,
        color,
        max(1, round(thickness * factor)),
        cv2.LINE_AA,
    )


def _scale(image):
    return image.shape[0] / 720
