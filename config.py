import os
from dotenv import load_dotenv

# Load environment variables from .env if available
load_dotenv()


class Config:
    # Required: OpenWeather API key
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    if not OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY is missing. Set it in .env or environment.")

    # Units: metric | imperial | standard
    DEFAULT_UNITS = os.getenv("DEFAULT_UNITS", "metric").lower()

    # Geocoding results limit
    GEO_LIMIT = int(os.getenv("GEO_LIMIT", "1"))

    # Cache TTL (seconds)
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # default: 5 min

    # HTTP timeouts (connect, read) → safe parsing
    _timeout_raw = os.getenv("HTTP_TIMEOUT", "3.5,7")
    try:
        parts = [float(x.strip()) for x in _timeout_raw.split(",")]
        HTTP_TIMEOUT = tuple(parts) if len(parts) == 2 else float(parts[0])
    except Exception:
        HTTP_TIMEOUT = (3.5, 7)

    # Allowed origin for CORS
    ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:5000")
