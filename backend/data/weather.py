"""Weather data fetcher using Open-Meteo Ensemble API and NWS observations."""
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import statistics
import time

logger = logging.getLogger("trading_bot")

# City configurations — AIRPORT coordinates matching METAR stations used by Polymarket
# Using airport lat/lon eliminates the systematic 3-8°F error from city-center coords
CITY_CONFIG: Dict[str, dict] = {
    # US cities — airport coordinates (NOT city centers)
    "nyc":          {"name": "New York City",  "lat": 40.7772,  "lon": -73.8726,  "nws_station": "KLGA",  "unit": "F"},  # LaGuardia
    "chicago":      {"name": "Chicago",        "lat": 41.9742,  "lon": -87.9073,  "nws_station": "KORD",  "unit": "F"},  # O'Hare
    "miami":        {"name": "Miami",          "lat": 25.7959,  "lon": -80.2870,  "nws_station": "KMIA",  "unit": "F"},  # Miami Intl
    "dallas":       {"name": "Dallas",         "lat": 32.8471,  "lon": -96.8518,  "nws_station": "KDAL",  "unit": "F"},  # Love Field (NOT DFW!)
    "seattle":      {"name": "Seattle",        "lat": 47.4502,  "lon": -122.3088, "nws_station": "KSEA",  "unit": "F"},  # Sea-Tac
    "atlanta":      {"name": "Atlanta",        "lat": 33.6407,  "lon": -84.4277,  "nws_station": "KATL",  "unit": "F"},  # Hartsfield
    "los_angeles":  {"name": "Los Angeles",    "lat": 33.9425,  "lon": -118.4081, "nws_station": "KLAX",  "unit": "F"},  # LAX
    "denver":       {"name": "Denver",         "lat": 39.8561,  "lon": -104.6737, "nws_station": "KDEN",  "unit": "F"},  # Denver Intl
    # European cities — airport coordinates
    "london":       {"name": "London",         "lat": 51.5048,  "lon": 0.0495,    "nws_station": "EGLC",  "unit": "C"},  # London City
    "paris":        {"name": "Paris",          "lat": 48.9962,  "lon": 2.5979,    "nws_station": "LFPG",  "unit": "C"},  # CDG
    "munich":       {"name": "Munich",         "lat": 48.3537,  "lon": 11.7750,   "nws_station": "EDDM",  "unit": "C"},  # Munich Intl
    "ankara":       {"name": "Ankara",         "lat": 40.1281,  "lon": 32.9951,   "nws_station": "LTAC",  "unit": "C"},  # Esenboga
    # Asian cities
    "seoul":        {"name": "Seoul",          "lat": 37.4691,  "lon": 126.4505,  "nws_station": "RKSI",  "unit": "C"},  # Incheon
    "tokyo":        {"name": "Tokyo",          "lat": 35.7647,  "lon": 140.3864,  "nws_station": "RJTT",  "unit": "C"},  # Haneda
    "shanghai":     {"name": "Shanghai",       "lat": 31.1443,  "lon": 121.8083,  "nws_station": "ZSPD",  "unit": "C"},  # Pudong
    "singapore":    {"name": "Singapore",      "lat": 1.3502,   "lon": 103.9940,  "nws_station": "WSSS",  "unit": "C"},  # Changi
    # Other regions
    "toronto":      {"name": "Toronto",        "lat": 43.6772,  "lon": -79.6306,  "nws_station": "CYYZ",  "unit": "C"},  # Pearson
    "sao_paulo":    {"name": "Sao Paulo",      "lat": -23.4356, "lon": -46.4731,  "nws_station": "SBGR",  "unit": "C"},  # Guarulhos
    "buenos_aires": {"name": "Buenos Aires",   "lat": -34.8222, "lon": -58.5358,  "nws_station": "SAEZ",  "unit": "C"},  # Ezeiza
    "wellington":   {"name": "Wellington",     "lat": -41.3272, "lon": 174.8052,  "nws_station": "NZWN",  "unit": "C"},  # Wellington Intl
}


@dataclass
class EnsembleForecast:
    """Ensemble weather forecast with per-member data."""
    city_key: str
    city_name: str
    target_date: date
    member_highs: List[float]  # Daily max temps (F) per ensemble member
    member_lows: List[float]   # Daily min temps (F) per ensemble member
    mean_high: float = 0.0
    std_high: float = 0.0
    mean_low: float = 0.0
    std_low: float = 0.0
    num_members: int = 0
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.member_highs:
            self.mean_high = statistics.mean(self.member_highs)
            self.std_high = statistics.stdev(self.member_highs) if len(self.member_highs) > 1 else 0.0
            self.num_members = len(self.member_highs)
        if self.member_lows:
            self.mean_low = statistics.mean(self.member_lows)
            self.std_low = statistics.stdev(self.member_lows) if len(self.member_lows) > 1 else 0.0

    def probability_high_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high above threshold."""
        if not self.member_highs:
            return 0.5
        count = sum(1 for h in self.member_highs if h > threshold_f)
        return count / len(self.member_highs)

    def probability_high_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high below threshold."""
        return 1.0 - self.probability_high_above(threshold_f)

    def probability_low_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low above threshold."""
        if not self.member_lows:
            return 0.5
        count = sum(1 for m in self.member_lows if m > threshold_f)
        return count / len(self.member_lows)

    def probability_low_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low below threshold."""
        return 1.0 - self.probability_low_above(threshold_f)

    @property
    def ensemble_agreement(self) -> float:
        """How one-sided the ensemble is (0.5 = split, 1.0 = unanimous)."""
        if not self.member_highs:
            return 0.5
        median = statistics.median(self.member_highs)
        above = sum(1 for h in self.member_highs if h > median)
        frac = above / len(self.member_highs)
        return max(frac, 1 - frac)


# Simple cache: (city_key, target_date_str) -> (timestamp, EnsembleForecast)
_forecast_cache: Dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


async def fetch_ensemble_forecast(city_key: str, target_date: Optional[date] = None) -> Optional[EnsembleForecast]:
    """
    Fetch ensemble forecast from Open-Meteo Ensemble API (free, 31-member GFS).
    Returns per-member daily max/min temperatures in Fahrenheit.
    """
    if city_key not in CITY_CONFIG:
        logger.warning(f"Unknown city key: {city_key}")
        return None

    if target_date is None:
        target_date = date.today()

    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    if cache_key in _forecast_cache:
        cached_time, cached_forecast = _forecast_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            return cached_forecast

    city = CITY_CONFIG[city_key]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Open-Meteo Ensemble API — GFS ensemble with 31 members
            # For non-US cities (unit="C"), fetch Celsius and convert to Fahrenheit locally
            city_unit = city.get("unit", "F")
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "daily": "temperature_2m_max,temperature_2m_min",
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
                "models": "gfs_seamless",
            }
            if city_unit == "F":
                params["temperature_unit"] = "fahrenheit"
            # If unit is "C", omit temperature_unit — Open-Meteo returns Celsius by default

            response = await client.get(
                "https://ensemble-api.open-meteo.com/v1/ensemble",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})

            # Open-Meteo returns each ensemble member as a separate key:
            #   temperature_2m_max (control), temperature_2m_max_member01, ..., _member30
            # Collect all member values for highs and lows
            # All member temps stored in Fahrenheit regardless of source unit
            member_highs = []
            member_lows = []

            for key, values in daily.items():
                if not isinstance(values, list) or not values:
                    continue
                val = values[0]
                if val is None:
                    continue
                if "temperature_2m_max" in key:
                    temp_f = float(val) if city_unit == "F" else _celsius_to_fahrenheit(float(val))
                    member_highs.append(temp_f)
                elif "temperature_2m_min" in key:
                    temp_f = float(val) if city_unit == "F" else _celsius_to_fahrenheit(float(val))
                    member_lows.append(temp_f)

            if not member_highs:
                logger.warning(f"No ensemble data for {city_key} on {target_date}")
                return None

            forecast = EnsembleForecast(
                city_key=city_key,
                city_name=city["name"],
                target_date=target_date,
                member_highs=member_highs,
                member_lows=member_lows,
            )

            _forecast_cache[cache_key] = (now, forecast)
            logger.info(f"Ensemble forecast for {city['name']} on {target_date}: "
                        f"High {forecast.mean_high:.1f}F +/- {forecast.std_high:.1f}F "
                        f"({forecast.num_members} members)")

            return forecast

    except Exception as e:
        logger.warning(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return None


async def fetch_nws_observed_temperature(city_key: str, target_date: Optional[date] = None) -> Optional[Dict[str, float]]:
    """
    Fetch observed temperature from NWS API for settlement.
    Returns dict with 'high' and 'low' in Fahrenheit, or None if not available.
    """
    if city_key not in CITY_CONFIG:
        return None

    city = CITY_CONFIG[city_key]
    if target_date is None:
        target_date = date.today()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # NWS observations endpoint
            station = city["nws_station"]
            url = f"https://api.weather.gov/stations/{station}/observations"
            headers = {"User-Agent": "(trading-bot, contact@example.com)"}

            # Get observations for the target date
            start = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
            end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

            response = await client.get(url, params={"start": start, "end": end}, headers=headers)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return None

            temps = []
            for obs in features:
                props = obs.get("properties", {})
                temp_c = props.get("temperature", {}).get("value")
                if temp_c is not None:
                    temps.append(_celsius_to_fahrenheit(temp_c))

            if not temps:
                return None

            return {
                "high": max(temps),
                "low": min(temps),
            }

    except Exception as e:
        logger.warning(f"Failed to fetch NWS observations for {city_key}: {e}")
        return None
