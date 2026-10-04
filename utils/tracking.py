from collections import defaultdict, deque
from math import hypot
from time import monotonic


class TrackHistory:
    """Histórico temporal e estado de movimento por ID do ByteTrack."""
    def __init__(self, trail_length, stop_threshold, stop_time):
        self.positions = defaultdict(lambda: deque(maxlen=trail_length))
        self.last_motion = {}
        self.stop_threshold = stop_threshold
        self.stop_time = stop_time

    def update(self, track_id, point):
        now = monotonic()
        points = self.positions[track_id]
        moved = True
        if points:
            previous = points[-1][0]
            moved = hypot(point[0] - previous[0], point[1] - previous[1]) >= self.stop_threshold
        points.append((point, now))
        if moved or track_id not in self.last_motion:
            self.last_motion[track_id] = now
        stopped_for = now - self.last_motion[track_id]
        return "PARADO" if stopped_for >= self.stop_time else "MOVENDO"

    def trail(self, track_id):
        return [point for point, _ in self.positions.get(track_id, [])]
