from services.weather_service import get_weather_data

def get_weather(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)
