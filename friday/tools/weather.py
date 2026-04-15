"""
Weather tools — current conditions via Open-Meteo (free, no API key required).
Geocoding via the Open-Meteo geocoding API.
"""

import httpx

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather Interpretation Codes → human-readable labels
_WMO = {
    0: "clear skies", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "heavy rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm",
}


async def _geocode(client: httpx.AsyncClient, city: str) -> dict | None:
    """Resolve city name to lat/lon via Open-Meteo geocoding."""
    r = await client.get(GEO_URL, params={"name": city, "count": 1, "format": "json"})
    r.raise_for_status()
    results = r.json().get("results")
    return results[0] if results else None


def register(mcp):

    @mcp.tool()
    async def get_weather(city: str) -> str:
        """
        Get current weather conditions for any city on Earth.
        Use when the boss asks about weather, temperature, or conditions in a location.
        """
        async with httpx.AsyncClient(timeout=8) as client:
            loc = await _geocode(client, city)
            if not loc:
                return f"Can't locate '{city}' on the map, sir."

            r = await client.get(WEATHER_URL, params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current_weather": "true",
                "hourly": "relative_humidity_2m",
                "forecast_days": 1,
                "timezone": "auto",
            })
            r.raise_for_status()
            data = r.json()

        cw = data["current_weather"]
        humidity = data["hourly"]["relative_humidity_2m"][0]
        condition = _WMO.get(int(cw["weathercode"]), "unknown conditions")
        name, country = loc["name"], loc.get("country", "")

        return (
            f"{name}, {country}: {cw['temperature']}°C, {condition}. "
            f"Wind {cw['windspeed']} km/h. Humidity {humidity}%."
        )
