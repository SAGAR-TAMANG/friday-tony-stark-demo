"""
Weather tools — Open-Meteo (no API key, free, global).
Geocoding via Open-Meteo's geocoding endpoint; weather via forecast endpoint.
"""

from typing import Any

import httpx

GEOCODE_URL  = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → human phrase. Subset covering 90% of real-world cases.
WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "rain showers", 81: "heavy showers", 82: "violent showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm",
}


async def _geocode(place: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.get(GEOCODE_URL, params={"name": place, "count": 1, "language": "en"})
        r.raise_for_status()
        data = r.json()
    hits = data.get("results") or []
    return hits[0] if hits else None


async def _current(lat: float, lon: float, days: int = 1) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": days,
    }
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.get(FORECAST_URL, params=params)
        r.raise_for_status()
        return r.json()


def register(mcp):

    @mcp.tool()
    async def get_weather(location: str) -> str:
        """Current weather for a location (city name, landmark, or 'lat,lon')."""
        place = await _geocode(location)
        if not place:
            return f"Couldn't locate {location!r}, boss."
        data = await _current(place["latitude"], place["longitude"])
        c = data.get("current", {})
        code = c.get("weather_code", -1)
        summary = WMO_CODES.get(code, "unknown conditions")
        return (
            f"{place['name']}, {place.get('country', '')}: "
            f"{c.get('temperature_2m', '?')}°C ({summary}), "
            f"feels like {c.get('apparent_temperature', '?')}°C, "
            f"humidity {c.get('relative_humidity_2m', '?')}%, "
            f"wind {c.get('wind_speed_10m', '?')} km/h."
        )

    @mcp.tool()
    async def get_forecast(location: str, days: int = 3) -> str:
        """Multi-day forecast for a location (default 3 days, max 16)."""
        days = max(1, min(int(days), 16))
        place = await _geocode(location)
        if not place:
            return f"Couldn't locate {location!r}, boss."
        data = await _current(place["latitude"], place["longitude"], days=days)
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        rain = daily.get("precipitation_probability_max", [])
        rows = [f"Forecast for {place['name']}, {place.get('country', '')}:"]
        for i, date in enumerate(dates):
            summary = WMO_CODES.get(codes[i] if i < len(codes) else -1, "mixed")
            high = highs[i] if i < len(highs) else "?"
            low  = lows[i]  if i < len(lows)  else "?"
            pop  = rain[i]  if i < len(rain)  else 0
            rows.append(f"  {date}: {low}–{high}°C, {summary}, rain {pop}%")
        return "\n".join(rows)
