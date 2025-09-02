from __future__ import annotations

import os
import time
from typing import Dict, Tuple, Any, Optional

import requests
from flask import Flask, jsonify, render_template, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cachetools import TTLCache

try:
    from config import Config
except ImportError:
    raise RuntimeError("Missing config.py with Config class.")

app = Flask(__name__)
app.config.from_object(Config)

if not app.config.get("OPENWEATHER_API_KEY"):
    raise RuntimeError(
        "Missing OPENWEATHER_API_KEY. Put it in .env or environment."
    )


# --- Robust requests session with retries ---
def build_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=4,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


session = build_session()

# --- Simple in-memory cache (city/coords + units) ---
# cache key: (kind, query_string, units) where kind ∈ {"city","coords"}
cache: TTLCache[Tuple[str, str, str], Dict[str, Any]] = TTLCache(
    maxsize=512, ttl=app.config["CACHE_TTL"]
)


# --- Helpers ---
def corsify(resp):
    # Basic CORS for simple demos (same-origin preferred)
    resp.headers["Access-Control-Allow-Origin"] = app.config["ALLOWED_ORIGIN"]
    resp.headers["Vary"] = "Origin"
    return resp


def owm_geo(q: str):
    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {
        "q": q,
        "limit": app.config["GEO_LIMIT"],
        "appid": app.config["OPENWEATHER_API_KEY"],
    }
    r = session.get(url, params=params, timeout=app.config["HTTP_TIMEOUT"])
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    # return first match
    hit = data[0]
    return {
        "name": hit.get("name"),
        "lat": hit.get("lat"),
        "lon": hit.get("lon"),
        "country": hit.get("country"),
        "state": hit.get("state"),
    }


def owm_current(lat: float, lon: float, units: str):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": app.config["OPENWEATHER_API_KEY"],
        "units": units,
    }
    r = session.get(url, params=params, timeout=app.config["HTTP_TIMEOUT"])
    r.raise_for_status()
    return r.json()


def owm_forecast(lat: float, lon: float, units: str):
    # 5 day / 3-hour forecast
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": app.config["OPENWEATHER_API_KEY"],
        "units": units,
    }
    r = session.get(url, params=params, timeout=app.config["HTTP_TIMEOUT"])
    r.raise_for_status()
    return r.json()


def cache_key_for_coords(lat: float, lon: float, units: str) -> Tuple[str, str, str]:
    return ("coords", f"{lat},{lon}", units)


def cache_key_for_city(q: str, units: str) -> Tuple[str, str, str]:
    return ("city", q, units)


def get_cached_or_none(key):
    return cache.get(key) if key in cache else None


def resolve_place(
    lat: Optional[str], lon: Optional[str], q: Optional[str], units: str
):
    """
    Return ((key, place_dict), None) on success
    Or (None, (error_response, status)) on error
    """
    if lat and lon:
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            return None, (corsify(jsonify({"error": "lat/lon must be numbers"})), 400)
        key = cache_key_for_coords(lat_f, lon_f, units)
        return (key, {"name": None, "lat": lat_f, "lon": lon_f}), None

    q = (q or "").strip()
    if not q:
        return None, (corsify(jsonify({"error": "q (city) must be non-empty"})), 400)
    if len(q) > 100:
        return None, (corsify(jsonify({"error": "q too long"})), 400)

    key = cache_key_for_city(q, units)
    geo = owm_geo(q)
    if not geo:
        return None, (corsify(jsonify({"error": f"No geocode results for '{q}'"})), 404)
    return (key, geo), None


def combine_payload(place, current, forecast, units):
    main = current.get("main", {}) if isinstance(current, dict) else {}
    wind = current.get("wind", {}) if isinstance(current, dict) else {}
    clouds = current.get("clouds", {}) if isinstance(current, dict) else {}
    weather_arr = current.get("weather", []) if isinstance(current, dict) else []

    return {
        "place": place,
        "units": units,
        "fetched_at": int(time.time()),
        "current": {
            "dt": current.get("dt") if isinstance(current, dict) else None,
            "temp": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
            "wind_speed": wind.get("speed"),
            "wind_deg": wind.get("deg"),
            "clouds": clouds.get("all"),
            # keep full array to match frontend expectations (weather[0])
            "weather": weather_arr,
            "visibility": current.get("visibility")
            if isinstance(current, dict)
            else None,
            "sunrise": current.get("sys", {}).get("sunrise")
            if isinstance(current, dict)
            else None,
            "sunset": current.get("sys", {}).get("sunset")
            if isinstance(current, dict)
            else None,
        },
        "forecast": {
            "city": forecast.get("city", {}) if isinstance(forecast, dict) else {},
            "list": forecast.get("list", []) if isinstance(forecast, dict) else [],
        },
    }


# --- Routes ---
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/weather")
def api_weather():
    """
    Query params:
        - q: city name (e.g. "London,UK" or "San Francisco,US")
        - lat, lon: coordinates (if provided, takes precedence over q)
        - units: "metric" | "imperial" | "standard"
    """
    units = (request.args.get("units") or app.config["DEFAULT_UNITS"]).lower()
    if units not in {"metric", "imperial", "standard"}:
        units = app.config["DEFAULT_UNITS"].lower()
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    q = request.args.get("q")

    if not ((lat and lon) or q):
        return corsify(jsonify({"error": "Provide either (lat & lon) or q=<city>"})), 400

    try:
        resolved, err = resolve_place(lat, lon, q, units)
        if err:
            return err
        key, place = resolved

        cached = get_cached_or_none(key)
        if cached is not None:
            return corsify(jsonify({**cached, "cached": True}))

        current = owm_current(place["lat"], place["lon"], units)
        forecast = owm_forecast(place["lat"], place["lon"], units)
        payload = combine_payload(place, current, forecast, units)
        cache[key] = payload
        return corsify(jsonify(payload))
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        owm_message = None
        try:
            if (
                e.response is not None
                and e.response.headers.get("Content-Type", "").startswith("application/json")
            ):
                body = e.response.json()
                owm_message = body.get("message") or body.get("error")
        except Exception:
            pass
        payload = {"error": "OpenWeather request failed", "status": status}
        if owm_message:
            payload["owm_message"] = owm_message
        return corsify(jsonify(payload)), status
    except Exception as e:
        return corsify(jsonify({"error": "Server error", "detail": str(e)})), 500


# Optional: health endpoint
@app.get("/healthz")
def health():
    return corsify(jsonify({"status": "ok"}))


if __name__ == "__main__":
    # Flask dev server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
