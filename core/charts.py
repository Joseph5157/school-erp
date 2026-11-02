"""Pure geometry helpers for server-drawn inline SVG charts.

Every function returns plain dicts or lists for templates. There is no database access here
and nothing imports `core.analytics`. `None` means "nothing to draw". A real zero is a value,
so values are compared with `is None`, never by truthiness.
"""

import math


def shares(counts):
    """Whole-number percentages of `counts` that always add up to 100 (largest remainder)."""
    total = sum(counts)
    if not total:
        return [0] * len(counts)
    exact = [count * 100 / total for count in counts]
    floors = [int(value) for value in exact]
    order = sorted(range(len(counts)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[: 100 - sum(floors)]:
        floors[i] += 1
    return floors


def _r(value):
    """Round an SVG coordinate to 2 decimals (and never emit -0.0)."""
    return round(value, 2) + 0.0


def _clamp(value, low, high):
    return max(low, min(high, value))


def ring(done, total, size=76, stroke=8):
    """A single progress ring. `dash` is the filled length on the circle's circumference."""
    if not total:
        return None
    done = _clamp(done, 0, total)
    # Rounded, but 100 only when everything is done and 0 only when nothing is.
    percent = _clamp(round(done * 100 / total), 1 if done > 0 else 0, 100 if done == total else 99)
    radius = (size - stroke) / 2
    circumference = _r(2 * math.pi * radius)
    return {
        "percent": percent,
        "done": done,
        "total": total,
        "size": size,
        "center": size / 2,
        "radius": radius,
        "stroke": stroke,
        "circumference": circumference,
        "dash": _r(circumference * done / total),
    }


def donut(parts, size=110, stroke=15):
    """A donut of (label, count) parts. Zero-count parts stay listed but draw nothing."""
    counts = [count for _, count in parts]
    total = sum(counts)
    if not total:
        return None
    radius = (size - stroke) / 2
    circumference = 2 * math.pi * radius
    part_shares = shares(counts)
    segments = []
    used = 0.0
    for index, ((label, count), share) in enumerate(zip(parts, part_shares, strict=True)):
        dash = circumference * count / total
        segments.append(
            {
                "label": label,
                "count": count,
                "share": share,
                "dash": _r(dash),
                "gap": _r(circumference - dash),
                "offset": _r(-used),
                "index": index,
            }
        )
        used += dash
    return {
        "total": total,
        "size": size,
        "center": size / 2,
        "radius": radius,
        "stroke": stroke,
        "headline_percent": part_shares[0],
        "segments": segments,
    }


_GAUGE_CX, _GAUGE_CY, _GAUGE_R = 100, 100, 80


def _gauge_point(percent, radius):
    angle = math.pi * (1 - _clamp(percent, 0, 100) / 100)
    return (
        _r(_GAUGE_CX + radius * math.cos(angle)),
        _r(_GAUGE_CY - radius * math.sin(angle)),
    )


def gauge(percent, target):
    """A semicircle gauge in a 200x122 viewBox with a tick at `target`."""
    if percent is None:
        return None
    start_x, start_y = _gauge_point(0, _GAUGE_R)
    end_x, end_y = _gauge_point(100, _GAUGE_R)
    value_x, value_y = _gauge_point(percent, _GAUGE_R)
    arc = f"A {_GAUGE_R} {_GAUGE_R} 0 0 1"
    x1, y1 = _gauge_point(target, _GAUGE_R - 10)
    x2, y2 = _gauge_point(target, _GAUGE_R + 6)
    return {
        "percent": percent,
        "target": target,
        "track_d": f"M {start_x:g} {start_y:g} {arc} {end_x:g} {end_y:g}",
        "value_d": f"M {start_x:g} {start_y:g} {arc} {value_x:g} {value_y:g}",
        "tick": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "met": percent >= target,
    }


def columns(rows, height=120, max_value=100):
    """Add `bar_height` and `bar_y` to each row. A zero value has no height."""
    result = []
    for row in rows:
        bar_height = _r(height * _clamp(row["value"], 0, max_value) / max_value)
        result.append({**row, "bar_height": bar_height, "bar_y": _r(height - bar_height)})
    return result


def bullet(score, pass_percent, comparison):
    """0-100 coordinates for a `viewBox="0 0 100 16"` bullet bar."""
    return {
        "score": score,
        "pass_width": None if pass_percent is None else _clamp(pass_percent, 0, 100),
        "marker_x": None if comparison is None else _clamp(comparison, 0, 100),
    }


def radar(axes, outlines, size=(280, 180)):
    """A radar chart. First axis at the top, clockwise. Values are 0-100."""
    if not 3 <= len(axes) <= 8:
        return None
    if len(outlines) > 2:
        raise ValueError("A radar chart draws at most 2 outlines.")
    width, height = size
    cx, cy = width / 2, height / 2
    radius = min(width / 2 - 50, height / 2 - 24)
    count = len(axes)

    def point(index, distance):
        angle = 2 * math.pi * index / count
        return cx + distance * math.sin(angle), cy - distance * math.cos(angle)

    def polygon(distances):
        return " ".join(
            f"{_r(x):g},{_r(y):g}" for x, y in (point(i, d) for i, d in enumerate(distances))
        )

    labels = []
    for index, text in enumerate(axes):
        x, y = point(index, radius + 12)
        dx = x - cx
        anchor = "middle" if abs(dx) < 1 else ("start" if dx > 0 else "end")
        labels.append({"text": text, "x": _r(x), "y": _r(y), "anchor": anchor})

    drawn = []
    for outline in outlines:
        if len(outline["values"]) != count:
            raise ValueError("Each radar outline needs one value per axis.")
        distances = [radius * _clamp(value, 0, 100) / 100 for value in outline["values"]]
        drawn.append(
            {"key": outline["key"], "label": outline["label"], "points": polygon(distances)}
        )

    spokes = []
    for index in range(count):
        x, y = point(index, radius)
        spokes.append({"x1": _r(cx), "y1": _r(cy), "x2": _r(x), "y2": _r(y)})

    return {
        "width": width,
        "height": height,
        "grid": [polygon([radius * level / 100] * count) for level in (25, 50, 75, 100)],
        "spokes": spokes,
        "labels": labels,
        "outlines": drawn,
    }
