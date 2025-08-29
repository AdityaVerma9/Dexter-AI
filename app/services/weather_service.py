import os
import aiohttp
from app.utils.config import Settings
from app.state import SESSION_KEYS

settings = Settings()

async def get_weather(city: str, api_key: str = None, session_id: str = None):
    """
    Fetch weather data using WeatherAPI.
    Priority: api_key param > session keys > env default
    """
    key = api_key
    if not key and session_id:
        session_keys = SESSION_KEYS.get(session_id, {})
        key = session_keys.get("WEATHER")
    if not key:
        key = settings.WEATHER_API_KEY
    
    if not city.strip():
        return {"error": "City name is required"}
    
    if not key:
        return {"error": "Weather API key not provided"}

    url = f"http://api.weatherapi.com/v1/current.json?key={key}&q={city.strip()}&aqi=no"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 401:
                    return {"error": "Invalid Weather API key"}
                elif resp.status != 200:
                    error_text = await resp.text()
                    return {"error": f"Weather API error: {resp.status} - {error_text}"}
                    
                data = await resp.json()
                
                # Handle API error responses
                if "error" in data:
                    return {"error": data["error"].get("message", "Weather API error")}
                
                return {
                    "location": data.get("location", {}).get("name"),
                    "country": data.get("location", {}).get("country"),
                    "temperature_c": data.get("current", {}).get("temp_c"),
                    "condition": data.get("current", {}).get("condition", {}).get("text"),
                }
                
    except aiohttp.ClientTimeout:
        return {"error": "Weather request timed out"}
    except Exception as e:
        return {"error": f"Weather service error: {str(e)}"}