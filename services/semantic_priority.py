def build_semantic_priorities(weather, flood_state_data):
    rainfall = flood_state_data["rainfall"]
    river = flood_state_data["river"]
    water = flood_state_data["water_level"]
    assessment = flood_state_data["flood_assessment"]
    items = {
        "assessment_status": (assessment["status"], True, 10),
        "assessment_reason": (assessment["reason"], True, 10),
        "rainfall_current": (rainfall["current_rain_mm"], rainfall["current_rain_mm"] is not None, 4),
        "rainfall_last_6h": (rainfall["last_6h_precipitation_mm"], rainfall["last_6h_precipitation_mm"] is not None, 5),
        "water_level": (water["current_m"], water["available"], 8 if water["available"] else 10),
        "water_level_rate": (water["rate_of_change_m_per_hour"], water["rate_of_change_m_per_hour"] is not None, 8 if water["rate_of_change_m_per_hour"] is not None else 10),
        "river_discharge_forecast": (river["discharge_m3s"], river["available"], 3)
    }
    out = {}
    for name, (value, available, score) in items.items():
        priority = "CRITICAL" if score >= 9 else "HIGH" if score >= 6 else "MEDIUM" if score >= 3 else "LOW"
        out[name] = {"value": value, "available": available, "score": score, "priority": priority}
    return out

def select_transmission_parameters(priorities, minimum_priority="HIGH"):
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    if minimum_priority not in order:
        raise ValueError(f"Unknown priority: {minimum_priority}")
    threshold = order[minimum_priority]
    return {key: item for key, item in priorities.items()
            if item["available"] and order[item["priority"]] >= threshold}

def generate_semantic_message(region_name, flood_state_data, selected_parameters):
    parts = [f"REGION={region_name}", "FLOOD_ASSESSMENT=NOT_ASSESSED"]
    for key, item in selected_parameters.items():
        if key not in ("assessment_status", "assessment_reason"):
            parts.append(f"{key.upper()}={item['value']}")
    return " | ".join(parts)

def calculate_semantic_compression(total_parameters, transmitted_parameters):
    if total_parameters <= 0:
        return 0.0
    return (1 - transmitted_parameters / total_parameters) * 100
