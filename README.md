# Taiwan Sail & Surf Forecast

Automated weather forecasting pipeline for Taiwan sailing and surfing conditions. Downloads CWA (Central Weather Administration) WRF model data, combines it with ECMWF IFS and WAM wave forecasts, and delivers HTML email reports with 7-day surf spot forecasts for northern Taiwan.

Runs 4x daily via GitHub Actions (00, 06, 12, 18 UTC).

## Components

| Script | Purpose |
|--------|---------|
| `taiwan_wrf_download.py` | Download & subset CWA WRF GRIB2 files from S3 |
| `wrf_analyze.py` | Extract Keelung point forecast, compare runs, generate HTML |
| `ecmwf_fetch.py` | Fetch ECMWF IFS forecast from Open-Meteo API |
| `wave_fetch.py` | Fetch ECMWF WAM wave forecast from Open-Meteo marine API |
| `surf_forecast.py` | Generate 7-day surf forecast for 7 Taiwan surf spots |

## Requirements

- Python 3.10+
- System: `libeccodes-dev`, `rclone`
- Python: `eccodes`, `numpy` (see `requirements.txt`)

## Quick Start

```bash
pip install -r requirements.txt

# Download latest WRF data (Keelung subset)
python taiwan_wrf_download.py --keelung-only --info

# Fetch ECMWF forecast
python ecmwf_fetch.py --output ecmwf_keelung.json

# Fetch wave data
python wave_fetch.py --output wave_keelung.json

# Analyze and generate HTML report
python wrf_analyze.py --rundir wrf_downloads/<run_dir> \
    --ecmwf-json ecmwf_keelung.json \
    --wave-json wave_keelung.json

# Generate surf forecast
python surf_forecast.py --output surf_forecast.html
```

## Data Sources

- **CWA WRF** (3km M-A0064): `s3://cwaopendata` (public, no auth)
- **ECMWF IFS / WAM**: Open-Meteo API (free tier, no key)
- **GFS**: Open-Meteo API (fallback for wind gusts / visibility)
