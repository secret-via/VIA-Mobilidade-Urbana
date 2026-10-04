def calculate_congestion(vehicle_count, zone_occupancy=0.0, average_speed_kmh=None,
                         stopped_vehicles=0, stopped_time_seconds=0.0, flow_per_minute=0):
    """Indicador heurístico para futura calibração; não é fórmula científica validada."""
    speed_penalty = 0.0 if average_speed_kmh is None else max(0.0, 1 - average_speed_kmh / 20)
    score = (vehicle_count * 0.20 + zone_occupancy * 0.35 + stopped_vehicles * 0.25
             + min(stopped_time_seconds / 60, 1) * 0.10 + min(flow_per_minute / 60, 1) * 0.10
             + speed_penalty * 0.10)
    score = round(min(score, 1.0), 2)
    level = "baixo" if score < .35 else "moderado" if score < .65 else "alto"
    return {"score": score, "level": level, "estimated": True,
            "note": "Indicador heurístico; requer calibração para uso operacional."}
