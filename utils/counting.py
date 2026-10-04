from collections import Counter, defaultdict, deque
from time import monotonic


def _side(point, line):
    (x1, y1), (x2, y2) = line
    return (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)


class LineCounter:
    """Conta cada ID apenas uma vez por linha ao trocar de lado."""
    def __init__(self, lines):
        self.lines = lines
        self.previous_sides = {}
        self.counted = set()
        self.totals = Counter()
        self.by_class = defaultdict(Counter)
        self.events = deque()

    def update(self, track_id, class_name, point):
        now = monotonic()
        for line_name, line in self.lines.items():
            key = (track_id, line_name)
            side = _side(point, line)
            old_side = self.previous_sides.get(key)
            self.previous_sides[key] = side
            if old_side is None or old_side == 0 or side == 0 or old_side * side > 0 or key in self.counted:
                continue
            self.counted.add(key)
            self.totals[line_name] += 1
            self.by_class[line_name][class_name] += 1
            self.events.append(now)
            return line_name
        return None

    def flow_per_minute(self):
        now = monotonic()
        while self.events and now - self.events[0] > 60:
            self.events.popleft()
        return len(self.events)
