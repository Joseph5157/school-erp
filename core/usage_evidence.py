"""The operator-only usage report (ADR 0027; spec sections 6.1 and 9), built and suppressed here.

`usage_report` (a management command run on the server) is the only reader. Nothing here is a web
page, and nothing is written anywhere but stdout.

**Cells and suppression.** Every printed number is a cell: the sum of a set of stored counter rows.
A cell from 1 to 4 prints as `<5` (primary suppression). Zero rows are left out, so a missing line
reads as zero. Every total or broader figure that is printed, and every split that adds up to one,
is found by comparing the rows behind the cells: when the cells of one table exactly cover the rows
of another cell, a reader can add or subtract them. If a hidden cell could then be recovered, the
smallest visible cell in that relation is hidden too and printed as `*` (complementary
suppression), until no hidden cell can be recovered from the printed figures. Totals that are only
implied, such as one week's page views (the same rows split by route, by display mode and by
platform), are tracked as unprinted cells so that two splits cannot reveal each other.

**Ratios.** A ratio prints `n/a` when its denominator is under the minimum stated for it. When its
numerator is hidden it prints only an upper bound (`<x%`), which says no more than `<5` does.
Triggers use three-valued logic: met, not met, or n/a (not enough data), which is never read as
met or missed. Triggers open a design gate only; they never approve a build.
"""

import math
from collections import defaultdict
from datetime import timedelta

from core import usage

MIN_CELL = 5
WINDOW_WEEKS = 4  # section 9: at least 4 instructional weeks
RATE_MINIMUM = 20  # weekly completion rate: started events needed (report rule, not section 9)
OTHER_SHARE_MINIMUM = 100  # 9.5 share of `other` among admin phone views (report rule)
STARTED_WORKFLOWS = ("attendance_capture", "marks_entry", "teacher_home", "find_student",
                     "missing_attendance_act", "guardian_first_view", "guardian_report_pdf")
SAVE_WORKFLOWS = ("attendance_capture", "marks_entry")
SAVE_STEP_ORDER = ("attempt", "saved", "network", "server", "csrf", "signed_out", "forbidden",
                   "conflict", "closed", "invalid", "retry_tapped", "retry_succeeded",
                   "fallback_save_used")
SIGN_IN_STEPS = {"sign_in": ("completed", "failed", "throttled", "password_changed_first"),
                 "session": ("expired_idle", "expired_limit", "expired_unsaved",
                             "relogin_after_expiry")}
DEVICE_COLUMNS = usage.DEVICES + ("",)
NO_TIMER = ""


def label(value, blank="unknown"):
    return value or blank


# --- the suppression engine ----------------------------------------------------------------------


class Cell:
    """A printed (or implied, unprinted) sum of stored counter rows."""

    def __init__(self, rows, counts, layer, printed=True):
        self.rows = frozenset(rows)
        self.value = sum(counts[i] for i in self.rows)
        self.layer = layer
        self.printed = printed
        self.secondary = False
        self.hidden = printed and 0 < self.value < MIN_CELL

    def text(self):
        if not self.hidden:
            return str(self.value)
        return "*" if self.secondary else f"<{MIN_CELL}"


class Cells:
    """All cells of one report. Each layer is a set of cells with disjoint rows."""

    def __init__(self, counts):
        self.counts = counts
        self.layers = defaultdict(list)
        self.implied = []
        self.relations = []  # (total, parts) known without comparing rows

    def add(self, layer, rows):
        cell = Cell(rows, self.counts, layer)
        self.layers[layer].append(cell)
        return cell

    def imply(self, rows):
        cell = Cell(rows, self.counts, None, printed=False)
        self.implied.append(cell)
        return cell

    def relate(self, total, parts):
        self.relations.append((total, list(parts)))

    def _relations(self):
        found = list(self.relations)
        targets = [c for layer in self.layers.values() for c in layer] + self.implied
        for total in targets:
            if not total.rows:
                continue
            for name, layer in self.layers.items():
                if name == total.layer:
                    continue
                parts = [c for c in layer if c.rows and c.rows <= total.rows]
                if parts and frozenset().union(*(c.rows for c in parts)) == total.rows:
                    found.append((total, parts))
        return found

    @staticmethod
    def _bounds(relations, cells):
        """What a reader can infer about every cell from the printed figures.

        A visible cell is exact; `<5` is 1 to 4; `*` may be any value, at least 1 (the legend says
        so, and a printed line is never 0); an implied total is at least 0. Each relation total = sum(parts) then narrows the
        bounds of its members, repeated until nothing changes. This catches subtraction (one
        unknown part) and range arguments too: 8 split into two `<5` cells forces both to be 4.
        """
        inf = math.inf
        low, high = {}, {}
        for c in cells:
            if not c.printed:
                low[id(c)], high[id(c)] = 0, inf
            elif not c.hidden:
                low[id(c)] = high[id(c)] = c.value
            elif c.secondary:
                low[id(c)], high[id(c)] = 1, inf  # `*`: any value; a printed line is never 0
            else:
                low[id(c)], high[id(c)] = 1, MIN_CELL - 1
        changed = True
        while changed:
            changed = False
            for total, parts in relations:
                t = id(total)
                sum_low = sum(low[id(p)] for p in parts)
                sum_high = sum(high[id(p)] for p in parts)
                if sum_low > low[t]:
                    low[t], changed = sum_low, True
                if sum_high < high[t]:
                    high[t], changed = sum_high, True
                for p in parts:
                    others_low = sum(low[id(q)] for q in parts if q is not p)
                    others_high = sum(high[id(q)] for q in parts if q is not p)
                    new_low = low[t] - others_high
                    new_high = high[t] - others_low
                    if new_low > low[id(p)]:
                        low[id(p)], changed = new_low, True
                    if new_high < high[id(p)]:
                        high[id(p)], changed = new_high, True
        return low, high

    @staticmethod
    def _leaks(cells, low, high):
        """Primary hidden cells a reader can narrow below the full range 1 to 4."""
        return [c for c in cells if c.printed and c.hidden and not c.secondary
                and (low[id(c)] > 1 or high[id(c)] < MIN_CELL - 1)]

    @staticmethod
    def _hide_near(cell, relations):
        """Hide the smallest visible printed cell that shares a relation with `cell`, looking
        through implied totals when the cell's own relations have no visible member left."""
        frontier, seen = [cell], {id(cell)}
        while frontier:
            visible, implied, small = [], [], []
            for current in frontier:
                for total, parts in relations:
                    members = [total, *parts]
                    if not any(m is current for m in members):
                        continue
                    for m in members:
                        if id(m) in seen:
                            continue
                        if m.printed and not m.hidden:
                            visible.append(m)
                        elif not m.printed:
                            implied.append(m)
                        elif not m.secondary:
                            # A `<5` neighbour; a total first, as hiding it frees all its parts.
                            small.insert(0, m) if m is total else small.append(m)
            if visible:
                smallest = min(visible, key=lambda m: m.value)
                smallest.hidden = smallest.secondary = True
                return True
            if small:
                # Nothing visible is left to hide: widen a `<5` neighbour to `*` (any value), for
                # example a `<5` window total over four weekly lines, which would make each 1.
                small[0].secondary = True
                return True
            for m in implied:
                seen.add(id(m))
            frontier = implied
        return False

    def protect(self):
        cells = [c for layer in self.layers.values() for c in layer] + self.implied
        relations = self._relations()
        while True:
            low, high = self._bounds(relations, cells)
            leaks = self._leaks(cells, low, high)
            if not leaks:
                return
            if not self._hide_near(leaks[0], relations):
                raise ProtectionError("a hidden cell could not be protected")


class ProtectionError(RuntimeError):
    """The report cannot be printed without revealing a small cell; nothing is printed."""


# --- ratios and triggers -------------------------------------------------------------------------


class Ratio:
    """Read only after suppression: its text and interval follow the cells' final state."""

    def __init__(self, num, den, minimum):
        self.num, self.den, self.minimum = num, den, minimum

    def _resolve(self):
        num, den = self.num, self.den
        if den.hidden or den.value < self.minimum:
            return "n/a", None
        if num.hidden:
            if num.secondary:
                return "n/a (hidden)", None
            bound = math.ceil(1000 * MIN_CELL / den.value) / 10
            return f"<{bound:.1f}%", (1 / den.value, (MIN_CELL - 1) / den.value)
        value = num.value / den.value
        return f"{100 * value:.1f}%", (value, value)

    @property
    def text(self):
        return self._resolve()[0]

    @property
    def interval(self):
        return self._resolve()[1]

    def at_least(self, threshold):
        if self.interval is None:
            return None
        if self.interval[0] >= threshold:
            return True
        return False if self.interval[1] < threshold else None

    def above(self, threshold):
        if self.interval is None:
            return None
        if self.interval[0] > threshold:
            return True
        return False if self.interval[1] <= threshold else None

    def below(self, threshold):
        result = self.at_least(threshold)
        return None if result is None else not result


def all_of(*values):
    if any(v is False for v in values):
        return False
    return True if all(v is True for v in values) else None


def any_of(*values):
    if any(v is True for v in values):
        return True
    return False if all(v is False for v in values) else None


def verdict(value):
    if value is None:
        return "n/a (not enough data: not met or missed)"
    return "met" if value else "not met"


# --- building the report -------------------------------------------------------------------------


class Report:
    """Counter rows in; cells and a plan of sections out, suppressed before anything is printed."""

    def __init__(self, rows, weeks, *, filtered, window_weeks):
        self.rows = rows
        self.weeks = weeks
        self.filtered = filtered
        self.window_weeks = window_weeks
        self.cells = Cells([r["count"] for r in rows])
        self.plan = []

    def select(self, **conditions):
        def matches(row):
            for name, wanted in conditions.items():
                value = row[name]
                if isinstance(wanted, (tuple, list, set, frozenset)):
                    if value not in wanted:
                        return False
                elif value != wanted:
                    return False
            return True
        return [i for i, row in enumerate(self.rows) if matches(row)]

    def cell(self, layer, keep_zero=False, **conditions):
        rows = self.select(**conditions)
        if not rows and not keep_zero:
            return None
        return self.cells.add(layer, rows)

    def build(self):
        for week in self.weeks:
            self.week_sections(week)
        if not self.filtered and self.window_weeks >= WINDOW_WEEKS:
            self.evidence()
        self.cells.protect()

    def week_sections(self, week):
        out = []
        self.plan.append(("week", week, out))
        w = {"week": week}
        flows = []
        for workflow in STARTED_WORKFLOWS:
            started = self.cell("flow", **w, workflow=workflow, step="started")
            completed = self.cell("flow", **w, workflow=workflow, step="completed")
            if not (started or completed):
                continue
            sizes, durations = [], []
            if workflow in usage.SIZED_WORKFLOWS:
                for size in usage.SIZE_BUCKETS + ("",):
                    s = self.cell("flow-size", **w, workflow=workflow, step="started",
                                  size_bucket=size)
                    c = self.cell("flow-size", **w, workflow=workflow, step="completed",
                                  size_bucket=size)
                    took = [(b, self.cell("flow-took", **w, workflow=workflow, step="completed",
                                          size_bucket=size, duration_bucket=b))
                            for b in usage.DURATION_BUCKETS + (NO_TIMER,)]
                    if s or c:
                        sizes.append((size, s, c, [(b, t) for b, t in took if t]))
            else:
                durations = [(b, self.cell("flow-took", **w, workflow=workflow, step="completed",
                                           duration_bucket=b))
                             for b in usage.DURATION_BUCKETS + (NO_TIMER,)]
                durations = [(b, t) for b, t in durations if t]
            flows.append((workflow, started, completed, sizes, durations))
        out.append(("flows", flows))
        saves = []
        for workflow in SAVE_WORKFLOWS:
            for step in SAVE_STEP_ORDER:
                c = self.cell("saves", **w, workflow=workflow, step=step)
                if c:
                    saves.append((workflow, step, c))
        out.append(("saves", saves))
        signin = []
        for workflow, steps in SIGN_IN_STEPS.items():
            for step in steps:
                for area in usage.AREAS:
                    c = self.cell("signin", **w, workflow=workflow, step=step, area=area)
                    if c:
                        signin.append((workflow, step, area, c))
        out.append(("signin", signin))
        pages, splits = [], []
        for area in usage.SURFACES + ("public",):
            routes = [r for r in usage.PAGE_ROUTES
                      if r == usage.OTHER_ROUTE or usage.PAGE_ROUTE_AREAS[r] == area]
            for route in routes:
                by_device = [(d, self.cell("pages", **w, workflow="page", area=area,
                                           page_route=route, device=d)) for d in DEVICE_COLUMNS]
                by_device = [(d, c) for d, c in by_device if c]
                if by_device:
                    pages.append((area, route, by_device))
            total = self.select(**w, workflow="page", area=area)
            if total:
                self.cells.imply(total)  # one week's page views: three splits add up to it
                display = [(v, self.cell("display", **w, workflow="page", area=area, display=v))
                           for v in usage.DISPLAYS + ("",)]
                platform = [(v, self.cell("platform", **w, workflow="page", area=area,
                                          platform=v)) for v in usage.PLATFORMS + ("",)]
                splits.append((area, [(v, c) for v, c in display if c],
                               [(v, c) for v, c in platform if c]))
        out.append(("pages", pages))
        out.append(("splits", splits))
        notices = [(a, self.cell("notices", **w, workflow="notice_view", age_bucket=a))
                   for a in usage.AGE_BUCKETS]
        out.append(("notices", [(a, c) for a, c in notices if c]))
        installs = [(s, self.cell("install", **w, workflow="install", step=s))
                    for s in ("shown", "installed", "dismissed")]
        out.append(("install", [(s, c) for s, c in installs if c]))

    def evidence(self):
        out = []
        self.plan.append(("evidence", None, out))
        serial = [0]

        def ev(**conditions):
            serial[0] += 1
            return self.cell(f"evidence-{serial[0]}", keep_zero=True, **conditions)

        def ratio(name, definition, num, den, minimum, unit, *, subset=False):
            if subset:  # den = num + rest; rest is implied by the two printed figures
                rest = self.cells.imply(den.rows - num.rows)
                self.cells.relate(den, [num, rest])
            r = Ratio(num, den, minimum)
            out.append(("ratio", name, definition, r, unit))
            return r

        saves = {"workflow": SAVE_WORKFLOWS, "device": "phone"}
        out.append(("heading", "9.1 Offline write and sync (MOB-08, MOB-09): phone, attendance "
                               "and marks. Client-reported counts are lower bounds; network "
                               "means observed network failures, which miss complete "
                               "disconnects."))
        N = ratio("N, observed network failure rate", "network / attempt",
                  ev(**saves, step="network"), ev(**saves, step="attempt"), 500, "attempts")
        R = ratio("R, retry success rate", "retry_succeeded / retry_tapped",
                  ev(**saves, step="retry_succeeded"), ev(**saves, step="retry_tapped"), 20,
                  "retry taps")
        ratio("F, fallback rate (supporting)", "fallback_save_used / attempt",
              ev(**saves, step="fallback_save_used"), ev(**saves, step="attempt"), 500,
              "attempts")
        # Triggers and verdict notes are callables: they read the cells after suppression.
        out.append(("trigger", "9.1 offline write and sync",
                    lambda: all_of(N.at_least(0.02), R.below(0.80))))

        out.append(("heading", "9.2 Push notifications (MOB-06). These count events, not people "
                               "or notices; S describes only notices that were viewed and cannot "
                               "show notices nobody opened."))
        notice = {"workflow": "notice_view", "area": "guardian"}
        S = ratio("S, share of recorded notice-view events on the publication day",
                  "same_day / all notice views", ev(**notice, age_bucket="same_day"),
                  ev(**notice), 100, "notice-view events", subset=True)
        pages = {"workflow": "page", "area": "guardian"}
        P = ratio("P, share of guardian page-view events on phones", "phone / known device",
                  ev(**pages, device="phone"), ev(**pages, device=usage.DEVICES), 200,
                  "page-view events", subset=True)
        ios = ratio("I, share of iOS guardian page-view events in the installed app "
                    "(supporting)", "iOS installed / iOS",
                    ev(**pages, platform="ios", display="installed"), ev(**pages, platform="ios"),
                    50, "iOS page-view events", subset=True)
        def push():
            return all_of(S.below(0.50), P.at_least(0.70))

        out.append(("trigger", "9.2 push notifications", push))

        out.append(("heading", "9.3 Login convenience (MOB-04, G-06). E and L cover all devices; "
                               "sign-in posts carry no device."))
        teacher_sign_ins = ev(workflow="sign_in", step="completed", area="teacher")
        E = ratio("E, expired-unsaved rate", "teacher expired_unsaved / teacher sign-ins",
                  ev(workflow="session", step="expired_unsaved", area="teacher"),
                  teacher_sign_ins, 200, "teacher sign-ins")
        L = ratio("L, re-sign-in rate", "teacher relogin_after_expiry / teacher sign-ins",
                  ev(workflow="session", step="relogin_after_expiry", area="teacher"),
                  teacher_sign_ins, 200, "teacher sign-ins")
        out.append(("count", "multi-area sign-ins (shown next to E, not in its denominator)",
                    ev(workflow="sign_in", step="completed", area="multi")))
        failed = ev(workflow="sign_in", step="failed")
        G = ratio("G, overall sign-in failure rate", "failed / (failed + completed)", failed,
                  ev(workflow="sign_in", step=("failed", "completed")), 300, "sign-in attempts",
                  subset=True)
        ratio("T, throttle share (supporting)", "throttled / failed",
              ev(workflow="sign_in", step="throttled"), failed, 50, "failures")
        out.append(("trigger", "9.3 login convenience",
                    lambda: any_of(E.above(0.05), L.above(0.30))))
        out.append(("note", lambda: f"Guardian recovery: G part {verdict(G.at_least(0.20))}; it "
                                    "also needs the office to confirm that guardian password "
                                    "resets are a recurring burden."))

        out.append(("heading", "9.4 Native apps (MOB-10), a meta-trigger per platform."))
        per_platform = {}
        # Every platform value is printed, including unknown (server-seen saves can come without
        # the device header), so the 9.1 totals minus the platform cells leave no hidden residual.
        for platform in usage.PLATFORMS + ("",):
            phone = {**saves, "platform": platform}
            name = label(platform)
            n_x = ratio(f"N on {name}", "network / attempt", ev(**phone, step="network"),
                        ev(**phone, step="attempt"), 500, "attempts")
            r_x = ratio(f"R on {name}", "retry_succeeded / retry_tapped",
                        ev(**phone, step="retry_succeeded"), ev(**phone, step="retry_tapped"),
                        20, "retry taps")
            if platform:  # unknown is printed but is not a platform for condition A
                per_platform[platform] = (n_x, r_x)

        def condition_a():
            met = {p: all_of(n.at_least(0.02), r.below(0.80)) for p, (n, r) in per_platform.items()}
            met_on = [p for p, value in met.items() if value is True]
            if len(met_on) == 1:
                return True, met_on[0]
            if met_on:
                return False, ""  # met on several platforms: not a one-platform shortfall
            return (False if all(v is False for v in met.values()) else None), ""

        def a_note():
            value, platform = condition_a()
            return f"A, offline on one platform: {verdict(value)}" + (
                f" ({platform})" if value else "")

        out.append(("note", a_note))
        out.append(("note", lambda: "B, iOS push reach: "
                                    + verdict(all_of(push(), ios.below(0.20)))))
        out.append(("note", "The rule also needs documented PWA capability testing on real "
                            "devices of that platform, so the counters alone never meet it."))

        out.append(("heading", "9.5 Admin phone coverage (G-04): admin page-view events on phones "
                               "over the window, by route."))
        admin_phone = {"workflow": "page", "area": "admin", "device": "phone"}
        routes = []
        for route in usage.PAGE_ROUTES:
            if route != usage.OTHER_ROUTE and usage.PAGE_ROUTE_AREAS[route] != "admin":
                continue
            c = self.cell("evidence-admin-routes", **admin_phone, page_route=route)
            if c:
                routes.append((route, c))
        out.append(("routes", routes, 5 * self.window_weeks))
        ratio("Share of other among admin phone views", "other / all admin phone views",
              ev(**admin_phone, page_route=usage.OTHER_ROUTE), ev(**admin_phone),
              OTHER_SHARE_MINIMUM, "admin phone views", subset=True)

        out.append(("heading", "9.6 Marks entry (G-05 follow-up): no trigger, comparison only."))
        marks = {"workflow": "marks_entry"}
        for size in usage.SIZE_BUCKETS:
            done = ev(**marks, step="completed", size_bucket=size)
            if done.hidden or done.value < 20:
                out.append(("note", f"marks completions, size {size}: n/a (below the minimum "
                                    "of 20)"))
                continue
            took = [(b, self.cell(f"evidence-took-{size}", **marks, step="completed",
                                  size_bucket=size, duration_bucket=b))
                    for b in usage.DURATION_BUCKETS + (NO_TIMER,)]
            out.append(("took", size, done, [(b, c) for b, c in took if c]))
        attempts = ev(**marks, step="attempt")
        ratio("invalid per attempt", "invalid / attempt", ev(**marks, step="invalid"), attempts,
              200, "attempts")
        ratio("conflict per attempt", "conflict / attempt", ev(**marks, step="conflict"),
              attempts, 200, "attempts")


# --- rendering: (section, period, item, value, text line) ----------------------------------------


def _week_name(week):
    return week  # already "YYYY-Www"


def _text(cell):
    return cell.text() if cell else "0"


def _rate(started, completed):
    if not started or started.hidden or started.value < RATE_MINIMUM:
        return "n/a"
    if not completed:
        return "0.0%"
    if not completed.hidden and completed.value > started.value:
        # Starts and completions are never joined: work started last week, or two Sections
        # sharing one attendance timer, can complete more than started this week.
        return "n/a (more completions than starts)"
    return Ratio(completed, started, RATE_MINIMUM).text


def _left(started, completed):
    """Derived from two printed cells, so printed only when both are visible."""
    if not started or started.hidden:
        return "n/a"
    if completed is None:
        return str(started.value)
    if completed.hidden:
        return "n/a"
    return str(max(0, started.value - completed.value))


def _line(period, text):
    return ("", period, "", "", text)


def render(report):
    for kind, week, out in report.plan:
        if kind == "week":
            period = _week_name(week)
            yield _line(period, f"\n== {period} ==")
            yield from _render_week(period, out)
        else:
            yield _line("window", "\nSection 9 review triggers over the whole window. These are "
                                  "review triggers: meeting one can open a design gate only; they "
                                  "never approve offline, push, login or native-app builds. Below "
                                  "a minimum a figure is n/a, which is not met or missed.")
            yield from _render_evidence("window", out)


def _took(period, item, bucket, cell, indent):
    name = label(bucket, "no timer")
    return ("workflows", period, f"{item} {name}", cell.text(),
            f"{indent}took {name:<10} {cell.text()}")


def _render_week(period, out):
    for kind, data in out:
        if not data:
            continue
        if kind == "flows":
            yield _line(period, "Workflows. Left incomplete = started - completed, an upper bound "
                                "on unfinished work, not a count of people: one person may start "
                                "several times, and work started one week and finished the next "
                                "counts in both.")
            for workflow, started, completed, sizes, durations in data:
                rate, left = _rate(started, completed), _left(started, completed)
                yield ("workflows", period, f"{workflow} started", _text(started), None)
                yield ("workflows", period, f"{workflow} completed", _text(completed), None)
                yield ("workflows", period, f"{workflow} rate", rate, None)
                yield ("workflows", period, f"{workflow} left incomplete", left, None)
                yield _line(period, f"  {workflow:<24} started {_text(started)}   completed "
                                    f"{_text(completed)}   rate {rate}   left incomplete {left}")
                for size, s, c, took in sizes:
                    name = label(size)
                    yield ("workflows", period, f"{workflow} size {name} started", _text(s), None)
                    yield ("workflows", period, f"{workflow} size {name} completed", _text(c),
                           None)
                    yield _line(period, f"    size {name:<8} started {_text(s)}   completed "
                                        f"{_text(c)}")
                    for bucket, cell in took:
                        yield _took(period, f"{workflow} size {name} completed", bucket, cell,
                                    "      ")
                for bucket, cell in durations:
                    yield _took(period, f"{workflow} completed", bucket, cell, "    ")
        elif kind == "saves":
            yield _line(period, "Saves. Browser-reported counts (attempt, network, server, csrf, "
                                "retries, fallback) are lower bounds; network means observed "
                                "network failures, which miss complete disconnects.")
            for workflow, step, cell in data:
                yield ("saves", period, f"{workflow} {step}", cell.text(),
                       f"  {workflow:<24} {step:<20} {cell.text()}")
        elif kind == "signin":
            yield _line(period, "Sign-in and session (a failed sign-in is always public).")
            for workflow, step, area, cell in data:
                yield ("signin", period, f"{workflow} {step} {area}", cell.text(),
                       f"  {workflow:<10} {step:<22} {area:<9} {cell.text()}")
        elif kind == "pages":
            yield _line(period, "Page views (events, not people), by route and device.")
            for area, route, by_device in data:
                for device, cell in by_device:
                    yield ("pages", period, f"{area} {route} {label(device)}", cell.text(), None)
                columns = "   ".join(f"{label(d)} {c.text()}" for d, c in by_device)
                yield _line(period, f"  {area:<9} {route:<34} {columns}")
        elif kind == "splits":
            yield _line(period, "Display mode and platform of page views (events).")
            for area, display, platform in data:
                for name, split in (("display", display), ("platform", platform)):
                    for value, cell in split:
                        yield ("splits", period, f"{area} {name} {label(value)}", cell.text(),
                               None)
                    columns = "   ".join(f"{label(v)} {c.text()}" for v, c in split)
                    yield _line(period, f"  {area:<9} {name:<9} {columns}")
        elif kind == "notices":
            yield _line(period, "Notice views by notice age, among notices that were viewed "
                                "(events, not people; notices nobody opened are not shown).")
            for age, cell in data:
                yield ("notices", period, f"notice_view {age}", cell.text(),
                       f"  {age:<10} {cell.text()}")
        elif kind == "install":
            yield _line(period, "Install (separate outcomes; a dismissal is never an "
                                "installation).")
            for step, cell in data:
                yield ("install", period, f"install {step}", cell.text(),
                       f"  install    {step:<10} {cell.text()}")


def _render_evidence(period, out):
    for entry in out:
        kind = entry[0]
        if kind == "heading":
            yield _line(period, "\n" + entry[1])
        elif kind == "note":
            text = entry[1]() if callable(entry[1]) else entry[1]
            yield _line(period, "  " + text)
        elif kind == "ratio":
            _, name, definition, r, unit = entry
            yield ("evidence", period, f"{name} numerator", r.num.text(), None)
            yield ("evidence", period, f"{name} denominator", r.den.text(), None)
            yield ("evidence", period, name, r.text, None)
            note = (f"below the minimum of {r.minimum} {unit}: not met or missed"
                    if r.text == "n/a" else f"minimum {r.minimum} {unit}")
            yield _line(period, f"  {name} ({definition}): {r.text}   "
                                f"({r.num.text()} of {r.den.text()}; {note})")
        elif kind == "count":
            _, name, cell = entry
            yield ("evidence", period, name, cell.text(), f"  {name}: {cell.text()}")
        elif kind == "trigger":
            _, name, rule = entry
            value = rule()
            yield ("trigger", period, name, verdict(value), f"  {name}: {verdict(value)}")
        elif kind == "routes":
            _, routes, needed = entry
            for route, cell in routes:
                flag = ("   (at least 5 a week: check its phone layout)"
                        if not cell.hidden and cell.value >= needed else "")
                yield ("evidence", period, f"admin phone {route}", cell.text(),
                       f"  {route:<34} {cell.text()}{flag}")
        elif kind == "took":
            _, size, done, took = entry
            if done.hidden:  # hidden by suppression after the minimum check: print nothing more
                yield _line(period, f"  marks completions, size {size}: n/a (hidden)")
                continue
            yield ("evidence", period, f"marks completions size {size}", done.text(),
                   f"  marks completions, size {size}: {done.text()}")
            for bucket, cell in took:
                name = label(bucket, "no timer")
                yield ("evidence", period, f"marks completions size {size} {name}", cell.text(),
                       f"    took {name:<10} {cell.text()}")


def build_report(queryset, *, today, weeks, filtered):
    """The report for `weeks` ISO weeks ending this week, from already-filtered counter rows."""
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=weeks - 1)
    fields = ("day", "area", "workflow", "step", "page_route", "duration_bucket", "size_bucket",
              "age_bucket", "device", "display", "platform", "count")
    rows = []
    for row in queryset.filter(day__gte=start, day__lte=today).values(*fields):
        year, week, _ = row["day"].isocalendar()
        row["week"] = f"{year}-W{week:02d}"  # a string: select() reads tuples as allowed values
        rows.append(row)
    report = Report(rows, sorted({row["week"] for row in rows}), filtered=filtered,
                    window_weeks=weeks)
    report.start = start
    report.build()
    return report
