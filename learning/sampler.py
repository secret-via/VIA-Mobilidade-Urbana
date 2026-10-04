from time import monotonic


class LearningSampler:
    def __init__(self, low_threshold, intermediate_threshold, min_interval, max_cases):
        self.low_threshold, self.intermediate_threshold = low_threshold, intermediate_threshold
        self.min_interval, self.max_cases = min_interval, max_cases
        self.last_saved, self.count = {}, 0

    def should_collect(self, detection):
        if self.count >= self.max_cases or detection["confidence"] >= self.intermediate_threshold:
            return False
        key, now = detection.get("class_name", "unknown"), monotonic()
        if now - self.last_saved.get(key, -float("inf")) < self.min_interval:
            return False
        self.last_saved[key] = now
        self.count += 1
        return True
