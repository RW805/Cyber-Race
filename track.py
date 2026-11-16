"""
Track definition -- pure Python (no pygame), so it can be unit tested headlessly.

The circuit is described by a handful of CONTROL_POINTS that a closed
centripetal Catmull-Rom spline is drawn through. That spline is resampled into evenly
spaced centreline samples, and everything else is derived from those samples:

  * Road:      any point within HALF_WIDTH of the centreline is "on track".
  * Grass:     a verge GRASS_WIDTH px wide runs along both sides of the road.
               It's drivable but slow.
  * Walls:     a hard barrier runs round the whole circuit at the outer edge of
               the grass (and round the edge of the screen). The car is pushed
               back and slides along it. Where two parts of the circuit run
               close together the verges merge and a single wall runs between them.
  * Laps:      ordered checkpoint gates around the centreline (see LapCounter).
               Works for any shape and either driving direction as long as the
               car follows the order the centreline is defined in.

To change the circuit, edit CONTROL_POINTS. Run `python3 track.py` to re-check that it doesn't overlap itself.
"""
import math

# --- Circuit definition ------------------------------------------------------
# (x, y) in screen pixels on a 1280x800 window. Listed in driving order; the
# first points form the start/finish straight along the bottom, driven left->right.
CONTROL_POINTS = [
    (330, 700), (620, 705), (900, 700),            # start/finish straight
    (1060, 685), (1155, 628), (1192, 540),         # T1: fast right-hand sweeper
    (1176, 446), (1110, 390), (1010, 402),         # T2: bends back into the infield
    (940, 455), (850, 470), (770, 415),            # T3-T4: chicane
    (760, 325), (830, 262), (940, 244),            # T5: climbing right
    (1060, 240), (1124, 216), (1150, 154),         # T6: hairpin at the top right
    (1120, 100), (1060, 82), (950, 86),
    (800, 110), (650, 160), (520, 110),            # top straight with a dip
    (380, 90), (265, 122), (185, 215),             # T7: sweeping left
    (200, 310), (280, 368), (345, 430),            # T8-T9: S-bend
    (350, 485), (312, 527), (250, 556),
    (185, 585), (150, 640), (174, 697),            # T10: big left-hander onto the straight
    (230, 722),
]

HALF_WIDTH = 48          # road is 96px wide
SAMPLE_SPACING = 6.0     # px between resampled centreline points
CAR_RADIUS = 10          # used for wall collisions

GRASS_WIDTH = 20         # px of grass between the road edge and the wall
WALL_THICKNESS = 6       # how thick the wall is drawn (px)
SCREEN_W, SCREEN_H = 1280, 800
SCREEN_WALL = 6          # wall drawn round the screen edge, same thickness

NUM_GATES = 16           # checkpoints per lap (gate 0 is the start/finish line)


# --- Spline helpers ------------------------------------------------------------
def _catmull_rom(p0, p1, p2, p3, t, alpha=0.5):
    """Centripetal Catmull-Rom (Barry-Goldman form). Unlike the uniform version it
    doesn't overshoot or loop when control points are unevenly spaced."""
    t0 = 0.0
    t1 = t0 + math.dist(p0, p1) ** alpha
    t2 = t1 + math.dist(p1, p2) ** alpha
    t3 = t2 + math.dist(p2, p3) ** alpha
    tt = t1 + t * (t2 - t1)

    def lerp(a, b, ta, tb):
        w = (tt - ta) / (tb - ta)
        return tuple(a[i] * (1 - w) + b[i] * w for i in (0, 1))

    a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
    b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
    return lerp(b1, b2, t1, t2)


def _dense_closed_spline(points, steps=30):
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        for s in range(steps):
            out.append(_catmull_rom(p0, p1, p2, p3, s / steps))
    return out


def _resample_closed(poly, spacing):
    """Resample a closed polyline into points spaced `spacing` apart by arc length."""
    n = len(poly)
    seg_len = [math.dist(poly[i], poly[(i + 1) % n]) for i in range(n)]
    total = sum(seg_len)
    count = max(8, int(total / spacing))
    step = total / count
    out, seg, acc, target = [], 0, 0.0, 0.0
    for _ in range(count):
        while acc + seg_len[seg] < target:
            acc += seg_len[seg]
            seg += 1
        f = (target - acc) / seg_len[seg] if seg_len[seg] else 0.0
        a, b = poly[seg], poly[(seg + 1) % n]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        target += step
    return out


# --- Track ---------------------------------------------------------------------
class Track:
    def __init__(self, control_points=None, half_width=HALF_WIDTH, grass_width=GRASS_WIDTH,
                 spacing=SAMPLE_SPACING, num_gates=NUM_GATES, screen=(SCREEN_W, SCREEN_H)):
        pts = control_points if control_points is not None else CONTROL_POINTS
        self.half_width = half_width
        self.grass_width = grass_width
        self.wall_dist = half_width + grass_width   # centreline -> inner face of the wall
        self.screen = screen
        self.samples = _resample_closed(_dense_closed_spline(pts), spacing)
        self.n = len(self.samples)
        self.spacing = spacing

        # Unit tangents and left-hand normals at each sample.
        self.tangents, self.normals = [], []
        for i in range(self.n):
            a, b = self.samples[(i - 1) % self.n], self.samples[(i + 1) % self.n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy) or 1.0
            tx, ty = dx / length, dy / length
            self.tangents.append((tx, ty))
            self.normals.append((ty, -tx))

        self.gates = [round(i * self.n / num_gates) % self.n for i in range(num_gates)]

    # -- geometry ---------------------------------------------------------------
    def nearest(self, x, y, hint=None, window=60):
        """Index of the closest centreline sample, and the distance to it.

        With a `hint` (last known index) only a window around it is searched,
        which is faster and stops the result jumping to a different part of the
        track that happens to be nearby. Falls back to a full search if the
        windowed result is far from the road (e.g. the car is deep in the grass).
        """
        samples, n = self.samples, self.n
        best_i, best_d2 = 0, float("inf")
        if hint is not None:
            for k in range(-window, window + 1):
                i = (hint + k) % n
                sx, sy = samples[i]
                d2 = (sx - x) ** 2 + (sy - y) ** 2
                if d2 < best_d2:
                    best_i, best_d2 = i, d2
            if best_d2 <= (self.half_width * 3) ** 2:
                return best_i, math.sqrt(best_d2)
            best_d2 = float("inf")
        for i, (sx, sy) in enumerate(samples):
            d2 = (sx - x) ** 2 + (sy - y) ** 2
            if d2 < best_d2:
                best_i, best_d2 = i, d2
        return best_i, math.sqrt(best_d2)

    def is_on_track(self, x, y, hint=None):
        return self.nearest(x, y, hint)[1] <= self.half_width

    def resolve_wall(self, x, y, idx, radius=CAR_RADIUS):
        """Keep the car inside the walls.

        The wall runs at `wall_dist` from the centreline, so the car's centre may be
        at most `wall_dist - radius` from its nearest centreline sample. Returns
        (x, y, idx, normal): the corrected position, nearest sample, and the outward
        wall normal if a wall was hit (None if not).
        """
        limit = self.wall_dist - radius
        cx, cy = self.samples[idx]
        dist = math.hypot(x - cx, y - cy)
        normal = None
        if dist > limit:
            # The windowed search can miss a closer section of the circuit next
            # door (where verges merge), so confirm with a full search first.
            idx, dist = self.nearest(x, y)
            cx, cy = self.samples[idx]
        if dist > limit and dist > 0:
            nx, ny = (x - cx) / dist, (y - cy) / dist
            x, y = cx + nx * limit, cy + ny * limit
            normal = (nx, ny)

        # Wall round the edge of the screen.
        w, h = self.screen
        lo = SCREEN_WALL + radius
        if x < lo:
            x, normal = lo, (-1.0, 0.0)
        elif x > w - lo:
            x, normal = w - lo, (1.0, 0.0)
        if y < lo:
            y, normal = lo, (0.0, -1.0)
        elif y > h - lo:
            y, normal = h - lo, (0.0, 1.0)
        return x, y, idx, normal

    def edge_point(self, idx, side, offset=0.0):
        """Point on the left (+1) or right (-1) road edge, `offset` px beyond it."""
        cx, cy = self.samples[idx % self.n]
        nx, ny = self.normals[idx % self.n]
        d = self.half_width + offset
        return cx + nx * d * side, cy + ny * d * side

    def start_pose(self, behind=14):
        """Grid position `behind` samples before the start line, facing along the track."""
        i = (-behind) % self.n
        tx, ty = self.tangents[i]
        x, y = self.samples[i]
        return x, y, math.atan2(ty, tx), i

    def circ_delta(self, a, b):
        """Signed shortest index distance from a to b around the loop."""
        d = (b - a) % self.n
        return d - self.n if d > self.n // 2 else d


# --- Lap counting --------------------------------------------------------------
class LapCounter:
    """Counts laps with ordered checkpoint gates.

    Gate 0 is the start/finish line. A lap only counts once the car has driven
    forward across every gate in order and then back across gate 0, so reversing
    over the line, jittering on it, or cutting across the infield can't add laps.
    The first time the car crosses the line from the grid doesn't count as a lap.
    """

    def __init__(self, track):
        self.track = track
        self.laps = 0
        self.expected = 0       # next gate the car must cross
        self.started = False    # becomes True when the car first crosses the line
        self.last_lap_idx = None
        self._prev = None

    def update(self, idx):
        prev, self._prev = self._prev, idx
        if prev is None:
            return self.laps
        t = self.track
        step = t.circ_delta(prev, idx)
        if step == 0 or abs(step) > t.n // 4:   # no movement, or a discontinuity: ignore
            return self.laps
        # Several gates can be crossed in a single update if the step is large.
        for _ in range(len(t.gates)):
            gate = t.gates[self.expected]
            d_prev = t.circ_delta(gate, prev)
            d_cur = t.circ_delta(gate, idx)
            if d_prev < 0 <= d_cur:     # crossed forward over this gate
                if self.expected == 0:
                    if self.started:
                        self.laps += 1
                    self.started = True
                self.expected = (self.expected + 1) % len(t.gates)
            else:
                break
        return self.laps


def min_corner_radius(track, k=6):
    """Tightest corner radius (px) on the centreline, from circles through
    samples k steps either side. Too small and the road edge pinches shut."""
    best = float("inf")
    for i in range(track.n):
        a, b, c = track.samples[(i - k) % track.n], track.samples[i], track.samples[(i + k) % track.n]
        area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))
        if area2:
            best = min(best, math.dist(a, b) * math.dist(b, c) * math.dist(c, a) / (2 * area2))
    return best


def _self_check(track):
    """Return the smallest distance between parts of the centreline that are far
    apart along the lap. Must exceed the road width or the track overlaps itself."""
    pts, n = track.samples, track.n
    gap = int(4 * track.half_width / track.spacing)  # ignore neighbours along the lap
    worst = float("inf")
    for i in range(0, n, 2):
        for j in range(i + gap, n, 2):
            if min(j - i, n - (j - i)) < gap:
                continue
            worst = min(worst, math.dist(pts[i], pts[j]))
    return worst


# Module-level default circuit used by the game.
TRACK = Track()


if __name__ == "__main__":
    t = TRACK
    length = t.n * t.spacing
    print(f"Track: {t.n} samples, ~{length:.0f}px long, {t.grass_width}px grass verge, walls all round")

    # 1) The circuit must not overlap itself and must fit on a 1280x800 screen.
    gap = _self_check(t)
    print(f"Closest approach between separate sections: {gap:.0f}px (road is {2 * t.half_width}px wide)")
    assert gap > 2 * t.half_width + 12, "track sections overlap -- move some control points"
    # Where two sections run side by side there must be room for both grass
    # verges and a visible wall between them.
    assert gap >= 2 * t.wall_dist + WALL_THICKNESS, "sections too close for grass + wall between them"
    # ...with room for the grass verge and the wall on screen too
    room = t.wall_dist + WALL_THICKNESS + 2
    for (x, y) in t.samples:
        assert room < x < SCREEN_W - room, f"too close to the screen edge x={x:.0f}"
        assert room < y < SCREEN_H - room, f"too close to the screen edge y={y:.0f}"

    radius = min_corner_radius(t)
    print(f"Tightest corner radius: {radius:.0f}px (road half-width is {t.half_width}px)")
    assert radius >= t.half_width + 6, "a corner is too tight -- the inside edge would pinch shut"

    # 2) Walls: everywhere round the circuit, the car is stopped at the outer edge
    #    of the grass -- never on the road, never beyond the grass.
    limit = t.wall_dist - CAR_RADIUS
    for idx in range(0, t.n, 5):
        cx, cy = t.samples[idx]
        for side in (+1, -1):
            nx, ny = t.normals[idx]
            nx, ny = nx * side, ny * side
            # a car well inside the grass verge doesn't touch the wall
            gx, gy = cx + nx * (t.half_width + 5), cy + ny * (t.half_width + 5)
            *_, hit = t.resolve_wall(gx, gy, idx)
            assert hit is None, f"wall hit on the grass at sample {idx}"
            # a car pushed just past the wall is brought back to it (skip spots
            # where that point is actually on a neighbouring part of the circuit)
            ox, oy = cx + nx * (t.wall_dist + 4), cy + ny * (t.wall_dist + 4)
            if t.nearest(ox, oy)[1] <= limit:
                continue
            px, py, j, hit = t.resolve_wall(ox, oy, idx)
            assert hit is not None, f"no wall at sample {idx}"
            assert t.nearest(px, py)[1] <= limit + 1e-6
            assert t.nearest(px, py)[1] > t.half_width - CAR_RADIUS, "wall must leave grass by the road"
    print(f"Walls: {t.grass_width}px of grass either side of the road, then the barrier")

    # 4) Laps: driving the centreline in order for 3.5 laps from the grid -> exactly 3 laps.
    def drive(counter, indices):
        prev_laps = 0
        for i in indices:
            counter.update(i % t.n)
            assert counter.laps - prev_laps in (0, 1)
            prev_laps = counter.laps
        return counter.laps

    grid = t.start_pose()[3]
    lc = LapCounter(t)
    assert drive(lc, range(grid, grid + int(3.5 * t.n))) == 3

    # fast driver: large index steps still count every lap
    lc = LapCounter(t)
    assert drive(lc, range(grid, grid + int(3.5 * t.n), 7)) == 3

    # Reversing back and forth over the start line adds nothing.
    lc = LapCounter(t)
    for i in list(range(grid, grid + 60)) + list(range(grid + 60, grid - 5, -1)) * 3:
        lc.update(i % t.n)
    assert lc.laps == 0

    # Cutting across the infield (skipping gates) gives no lap.
    lc = LapCounter(t)
    lc_idx = list(range(grid, grid + 60)) + [t.n // 2 + k for k in range(0, 40)] + list(range(t.n - 40, t.n + 40))
    for i in lc_idx:
        lc.update(i % t.n)
    assert lc.laps == 0, f"skipping checkpoints must not count, got {lc.laps}"

    print("OK: circuit fits, doesn't overlap, walls all round behind the grass, laps count correctly.")
