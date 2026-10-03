import argparse
from pathlib import Path
from services.region_manager import load_regions, get_region
from services.weather_service import get_weather_data
from services.flood_api import get_discharge_analysis
from services.water_level import get_water_level_analysis
from services.flood_state import analyze_flood_state
from services.semantic_priority import (
    build_semantic_priorities,
    select_transmission_parameters,
    generate_semantic_message,
)
from services.channel_predictor import predict_channel
from semantic_transmission import transmit_semantic_message

def show(value, unit=""):
    return "UNAVAILABLE" if value is None else f"{value}{unit}"

def run(region, communication_attempts=5):
    print(f"\nFlood monitoring - {region['name']} ({region['river']})")
    weather = get_weather_data(region["latitude"], region["longitude"], region.get("timezone", "Asia/Kolkata"))
    discharge = get_discharge_analysis(region["latitude"], region["longitude"])
    water = get_water_level_analysis(region)
    data = analyze_flood_state(weather, discharge, water)

    current = weather["current"]
    print("\nWEATHER (Open-Meteo model data)")
    for label, key, unit in [
        ("Observation", "time", ""),
        ("Temperature", "temperature_c", " C"),
        ("Humidity", "humidity_pct", " %"),
        ("Current rain", "rain_mm", " mm"),
        ("Wind speed", "wind_speed_kmh", " km/h"),
    ]:
        print(f"{label}: {show(current.get(key), unit)}")

    print("\nRAINFALL ACCUMULATION (observed hourly precipitation)")
    for hours in (1, 3, 6, 24):
        print(f"Last {hours}h: {show(data['rainfall'][f'last_{hours}h_precipitation_mm'], ' mm')}")

    print("\nHYDROLOGY")
    print(f"Modeled daily discharge forecast: {show(discharge.get('discharge_m3s'), ' m3/s')} for {discharge.get('time') or 'unknown date'}")
    print(f"Forecast source status: {discharge.get('reason') or 'available'}")
    print(f"Configured station: {water.get('station')}")
    if water.get("is_recent"):
        print(f"Fresh station water level: {show(water.get('current_level_m'), ' m')} at {water.get('current_time')}")
    elif water.get("latest_observed_m") is not None:
        print(f"Latest file observation: {water['latest_observed_m']} m at {water['current_time']} ({water['age_hours']:.1f} hours old)")
        print(f"Live station reading: UNAVAILABLE - {water.get('reason')}")
    else:
        print(f"Live station reading: UNAVAILABLE - {water.get('reason')}")

    assessment = data["flood_assessment"]
    print("\nFLOOD ASSESSMENT")
    print("Status: NOT ASSESSED")
    print("Risk score: NOT AVAILABLE")
    print(assessment["reason"])
    print("Missing/unconfigured: " + "; ".join(assessment["missing_or_unconfigured"]))
    print("Use official local warnings and emergency guidance for decisions.")

    priorities = build_semantic_priorities(weather, data)
    selected = select_transmission_parameters(priorities)
    print("\nSEMANTIC PRIORITIES")
    for key, item in priorities.items():
        value = item["value"] if item["available"] else "UNAVAILABLE"
        print(f"{key}: {value} [{item['priority']}]")
    print("\nSEMANTIC MESSAGE")
    semantic_message = generate_semantic_message(region["name"], data, selected)
    print(semantic_message)

    print("\nSIMULATED SEMANTIC COMMUNICATION + VIRTUAL RIS")
    print("All channel measurements, RIS effects, and packet outcomes below are simulated.")
    policy_path = Path(__file__).resolve().parent / "models" / "ris_q_table.npz"
    result = transmit_semantic_message(
        packet=semantic_message,
        priorities=priorities,
        policy_path=policy_path,
        max_attempts=communication_attempts,
    )
    print(f"Message priority: {result['priority']}")
    for item in result["attempts"]:
        if item["waited"]:
            print(f"Attempt {item['attempt']}: no candidate met the simulated availability threshold; message queued")
        else:
            print(
                f"Attempt {item['attempt']}: {item['candidate']} | "
                f"RIS config {item['ris_configuration']} | "
                f"{item['channel_condition']} | SNR {item['snr_db']:.2f} dB | "
                f"latency {item['latency_ms']:.1f} ms | "
                f"{'DELIVERED' if item['delivered'] else 'NOT DELIVERED'}"
            )
    if result["delivered"]:
        print("Receiver: packet decoded and semantic message received:")
        print(result["packet_received"])
    else:
        print("Receiver: packet not delivered within the attempt limit; remains queued for a later retry.")
    print(f"Agent updated from simulated feedback; policy saved to {result['policy_path']}")

    channel = predict_channel(None, None, None, None, None)
    print("\nCHANNEL MODEL")
    print(f"Rician K: {show(channel.get('rician_k'))}")
    if not channel["available"]:
        print(channel["reason"])
    print("Channel condition bands (K-factor rules):")
    for band in channel["condition_bands"]:
        print(f"  {band['condition']}: {band['status']} ({band['rule']})")
    print(f"Radio-link availability: {channel['link_availability']} (requires link measurements such as SNR, packet success, or outage criteria)")
    if not channel["available"]:
        print("Required measured inputs: water_depth, los_obstruction, debris_density, flow_velocity, reflection_dominance.")
        print("Do not substitute river gauge level or synthetic guesses for these measurements.")
    else:
        print(channel["model_note"])
    print("No channel quality percentage is reported.")

def main():
    parser = argparse.ArgumentParser(description="Regional flood and semantic monitoring")
    parser.add_argument("--region", help="Configured region ID (interactive selection if omitted)")
    parser.add_argument("--communication-attempts", type=int, default=5,
                        help="Maximum simulated transmission attempts for the semantic message")
    args = parser.parse_args()
    regions = load_regions()
    region_id = args.region
    if not region_id:
        for region in regions:
            print(f"{region['id']} - {region['name']} ({region['river']})")
        region_id = input("Enter region ID: ").strip()
    if args.communication_attempts < 1:
        parser.error("--communication-attempts must be at least 1")
    run(get_region(region_id), communication_attempts=args.communication_attempts)

if __name__ == "__main__":
    main()
