from math import hypot


def estimate_speed_kmh(previous, current, distance_meters, distance_pixels):
    """Retorna None quando a câmera não foi calibrada."""
    if not distance_meters or not distance_pixels or current[2] <= previous[2]:
        return None
    pixels = hypot(current[0] - previous[0], current[1] - previous[1])
    return round((pixels * distance_meters / distance_pixels) / (current[2] - previous[2]) * 3.6, 2)
