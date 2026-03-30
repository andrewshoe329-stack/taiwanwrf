# CWA Open Data API Reference

> **For Taiwan WRF pipeline use.** Documents the CWA endpoints we use or may use, with query parameters and response structures learned from implementation.

Base URL: `https://opendata.cwa.gov.tw/api/v1/rest/datastore/{endpoint_id}`

All endpoints require `Authorization` query param (API key from `CWA_OPENDATA_KEY`).

---

## Endpoints We Use

### F-A0021-001 — 潮汐預報 (Tide Forecast, 1 month)

**Purpose:** Official CWA tide predictions (high/low times + heights) for coastal townships.

**Used in:** `cwa_fetch.py` → `fetch_tide_forecasts_multi()`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `LocationName` | array\<string\> | Township names (e.g. `基隆市中正區,宜蘭縣頭城鎮`). Ignored if `LocationId` is set. Default: all. |
| `LocationId` | array\<string\> | Township IDs (e.g. `10017010,10002040`). Overrides `LocationName`. Default: all. |
| `WeatherElement` | array\<string\> | Filter elements: `LunarDate`, `TideRange`, `Tide`, `TideHeights`. If `Tide`/`TideHeight` not selected, `Time` won't show. |
| `TideRange` | array\<string\> | Filter by tidal range: `大`, `中`, `小` |
| `Date` | array\<string\> | Filter by date: `yyyy-MM-dd` |
| `hhmmss` | array\<string\> | Filter by time: `hh:mm:ss` |
| `timeFrom` / `timeTo` | datetime | Time range filter: `yyyy-MM-ddThh:mm:ss`. Ignored if `Date`/`hhmmss` used. |
| `sort` | array\<string\> | Sort by `Date` or `DateTime` |
| `limit` / `offset` | int | Pagination |

**Available Locations (northern Taiwan):**
| LocationName | LocationId | Lon | Lat | Nearest Spot |
|-------------|-----------|-----|-----|-------------|
| 新北市金山區 | 65000270 | 121.638 | 25.248 | Jinshan (1km) |
| 新北市萬里區 | 65000280 | 121.689 | 25.211 | Green Bay (2.5km) |
| 新北市瑞芳區 | 65000120 | 121.829 | 25.131 | — |
| 基隆市中正區 | 10017010 | 121.790 | 25.151 | Keelung (0.5km) |
| 基隆市中山區 | 10017050 | 121.752 | 25.155 | — |
| 基隆市安樂區 | 10017060 | 121.711 | 25.168 | — |
| 新北市貢寮區 | 65000260 | 121.950 | 25.022 | Fulong (0.7km) |
| 新北市石門區 | 65000220 | 121.531 | 25.293 | — |
| 宜蘭縣頭城鎮 | 10002040 | 121.838 | 24.867 | Daxi/Double Lions/Wushih/Chousui (0.6-8km) |
| 宜蘭縣壯圍鄉 | 10002060 | 121.843 | 24.760 | — |
| 宜蘭縣五結鄉 | 10002090 | 121.842 | 24.680 | — |
| 宜蘭縣蘇澳鎮 | 10002030 | 121.867 | 24.593 | — |
| 宜蘭縣南澳鄉 | 10002120 | 121.807 | 24.415 | — |

**Response Structure:**
```
records.TideForecasts[] → list of { "Location": {
  "LocationName": "基隆市中正區",
  "LocationId": "10017010",
  "Latitude": "25.1506",
  "Longitude": "121.79",
  "TimePeriods": {
    "Daily": [{
      "Date": "2026-04-01",
      "LunarDate": "三月初四",
      "TideRange": "中",
      "Time": [{
        "DateTime": "2026-04-01T00:03:00+08:00",
        "Tide": "乾潮",
        "TideHeights": {
          "AboveTWVD": "-55",       // cm, relative to Taiwan Vertical Datum
          "AboveLocalMSL": "-70",   // cm, relative to local mean sea level
          "AboveChartDatum": "47"   // cm, relative to chart datum
        }
      }, ...]
    }, ...]
  }
}}
```

**Height datums (all in cm, we convert to metres):**
- `AboveLocalMSL` — relative to local mean sea level (preferred, centered on 0)
- `AboveTWVD` — relative to Taiwan Vertical Datum (TWVD2001)
- `AboveChartDatum` — relative to chart datum (always positive, used for navigation)

**Our mapping (config.py `SPOT_TIDE_STATION`):**
- Keelung → 基隆市中正區
- Jinshan → 新北市金山區
- Green Bay → 新北市萬里區
- Fulong → 新北市貢寮區
- Daxi/Double Lions/Wushih/Chousui → 宜蘭縣頭城鎮

---

### O-A0001-001 — 氣象觀測站 (Weather Stations, hourly)

**Purpose:** Real-time hourly weather observations from all CWA stations.

**Used in:** `cwa_fetch.py` → `fetch_station_obs()`, `cwa_discover.py` → `fetch_all_weather_stations()`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `StationId` | array\<string\> | Station codes (case-sensitive). See [station list](https://hdps.cwa.gov.tw/static/state.html). Overrides `StationName`. |
| `StationName` | array\<string\> | Station names. Ignored if `StationId` is set. |
| `WeatherElement` | array\<string\> | Filter elements (see below). Default: all. |
| `GeoInfo` | array\<string\> | Filter geo fields (see below). Default: all. |

**Available WeatherElement values:**
`Weather`, `Now`, `WindDirection`, `WindSpeed`, `AirTemperature`, `RelativeHumidity`, `AirPressure`, `GustInfo`, `DailyHigh`, `DailyLow`

**Available GeoInfo values:**
`Coordinates`, `StationAltitude`, `CountyName`, `TownName`, `CountyCode`, `TownCode`

**Notes:**
- `StationId` is case-sensitive (e.g. `C0A520` not `c0a520`)
- Full station list: https://hdps.cwa.gov.tw/static/state.html
- Stations near our spots are mapped in `cwa_stations.json` (produced by `cwa_discover.py`)
- For pipeline efficiency, we could use `WeatherElement=AirTemperature,WindSpeed,WindDirection,GustInfo,AirPressure,RelativeHumidity` to skip unused fields

**Weather stations near our spots (from CWA station list):**

| StationId | Name | Type | Lat | Lon | City | Nearest Spot |
|-----------|------|------|-----|-----|------|-------------|
| 466940 | 基隆 | 署屬有人站 | 25.133 | 121.740 | 基隆市 | Keelung (1.8km) |
| C0B050 | 八斗子 | 署屬自動站 | 25.145 | 121.792 | 基隆市 | Keelung (0.5km) |
| C0B040 | 大武崙 | 署屬自動站 | 25.167 | 121.707 | 基隆市 | — |
| C0A940 | 金山 | 署屬自動站 | 25.224 | 121.644 | 新北市 | Jinshan (1.9km) |
| C0AJ20 | 野柳 | 署屬自動站 | 25.207 | 121.690 | 新北市 | Green Bay (2.1km) |
| C0A860 | 大坪 | 署屬自動站 | 25.166 | 121.633 | 新北市 | — |
| C0AJ40 | 石門 | 署屬自動站 | 25.274 | 121.601 | 新北市 | — |
| C0A950 | 鼻頭角 | 署屬自動站 | 25.129 | 121.923 | 新北市 | Fulong area |
| C0A890 | 雙溪 | 署屬自動站 | 25.036 | 121.864 | 新北市 | Fulong (4km) |
| C2A880 | 福隆 | 農業站 | 25.018 | 121.942 | 新北市 | Fulong (0.7km) |
| C0UA80 | 大溪漁港 | 署屬自動站 | 24.942 | 121.903 | 宜蘭縣 | Daxi (1.9km) |
| C0U860 | 頭城 | 署屬自動站 | 24.853 | 121.831 | 宜蘭縣 | Wushih/Chousui (2km) |
| C0U600 | 礁溪 | 署屬自動站 | 24.818 | 121.766 | 宜蘭縣 | — |
| C0UA90 | 石城 | 署屬自動站 | 24.980 | 121.951 | 宜蘭縣 | Fulong area |
| C0U880 | 北關 | 署屬自動站 | 24.907 | 121.873 | 宜蘭縣 | Daxi (5km) |
| C0UB10 | 蘇澳 | 署屬自動站 | 24.597 | 121.857 | 宜蘭縣 | — |
| C0U750 | 龜山島 | 署屬自動站 | 24.842 | 121.953 | 宜蘭縣 | Offshore reference |

---

### O-A0003-001 — 氣象觀測站 10分鐘綜觀氣象 (10-min conventional obs)

**Purpose:** Higher-frequency conventional weather observations.

**Used in:** Referenced in CLAUDE.md but not currently used in pipeline.

---

### O-A0002-001 — 雨量觀測站 (Rain gauge data)

**Purpose:** Automatic rain gauge readings.

**Used in:** Referenced but not actively used.

---

### O-B0075-001 — 海象監測 48h (Marine obs: buoys + tide stations)

**Purpose:** Combined buoy wave data + tide station sea level observations, 48-hour window.

**Used in:** `cwa_fetch.py` → `_fetch_marine_stations()`, `fetch_buoy_obs()`, `fetch_tide_obs()`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `StationID` | array\<string\> | Station codes. See [O-B0076-001](https://opendata.cwa.gov.tw/dataset/observation/O-B0076-001) for full list. |
| `WeatherElement` | array\<string\> | Filter elements (see below). Default: all. |
| `DataTime` | array\<string\> | Exact time filter (`yyyy-MM-ddThh:mm:ss`). Default: all. |
| `timeFrom` / `timeTo` | datetime | Time range filter (`yyyy-MM-ddThh:mm:ss`). Ignored if `DataTime` used. |
| `sort` | string | `StationID` or `DataTime` ascending sort |

**Available WeatherElement values:**
`TideHeight`, `TideLevel`, `WaveHeight`, `WaveDirection`, `WaveDirectionDescription`, `WavePeriod`, `SeaTemperature`, `Temperature`, `StationPressure`, `PrimaryAnemometer`, `SeaCurrents`

**Response Structure:**
```
Records.SeaSurfaceObs.Location[] → [{
  "Station": { "StationID": "C4B01", "StationName": "基隆" },
  "StationObsTimes": { "StationObsTime": [{
    "DateTime": "...",
    "WeatherElements": {
      "TideHeight": "0.44",
      "TideLevel": "退潮",
      "SeaTemperature": "20.1",
      "StationPressure": "1014.7",
      "WaveHeight": "1.2",
      "WavePeriod": "6.5",
      "WaveDirection": "45",
      "WaveDirectionDescription": "NE",
      "PrimaryAnemometer": { "WindSpeed": "1.8", ... },
      "SeaCurrents": { ... }
    }
  }]}
}]
```

**Key station IDs (northern Taiwan):**
| ID | Name | Type | Notes |
|----|------|------|-------|
| 46694A | 龍洞 | Buoy | Primary wave buoy for Keelung area |
| 46708A | 富貴角 | Buoy | North coast |
| 46714C | 蘇澳 | Buoy | NE coast (near Chousui) |
| C4B01 | 基隆 | Tide station | Keelung harbour tide gauge |
| C6AH2 | 基隆 | Buoy | Keelung area |

---

### O-B0075-002 — 海象監測 30天 (Marine obs, 30-day window)

**Purpose:** Same structure as O-B0075-001 but covers 30-day history. Useful for accuracy tracking.

**Not currently used.** Could supplement `accuracy_track.py` with longer observation history.

**Query Parameters:** Same as O-B0075-001 (`StationID`, `WeatherElement`, `sort`, `DataTime`, `timeFrom`, `timeTo`).

**Key difference from O-B0075-001:** The `timeFrom`/`timeTo` window is limited to **24 hours per request** even though 30 days of data is available. To get the full 30-day history, you must make multiple requests with sliding 24h windows.

- If neither `timeFrom` nor `timeTo` is set: returns the **earliest** 24h of data (not latest!)
- `timeFrom` alone: returns 24h starting from `timeFrom`
- `timeTo` alone: returns 24h ending at `timeTo`
- Both: returns from `timeFrom` to `timeTo`, capped at 24h
- `DataTime` overrides `timeFrom`/`timeTo`

---

### F-D0047-{XXX} — 鄉鎮天氣預報 (Township weather forecast)

**Purpose:** Per-township 3-day or 1-week weather forecasts.

**Used in:** `cwa_fetch.py` → `fetch_township_forecast()`

**Endpoint numbering:** Odd = 3-day, even+1 = 1-week.

| Endpoint | County | Used? |
|----------|--------|-------|
| F-D0047-001 | 宜蘭縣 (Yilan) | Yes — Daxi, Wushih, Double Lions, Chousui |
| F-D0047-049 | 基隆市 (Keelung) | Yes — Keelung harbour |
| F-D0047-069 | 新北市 (New Taipei) | Yes — Fulong, Green Bay, Jinshan |
| F-D0047-093 | 全臺灣 (All Taiwan) | Not used yet — could replace all 3 above |

**Response Structure (F-D0047-049 example):**
```
records.Locations[].Location[] → [{
  "LocationName": "中正區",
  "WeatherElement": [{
    "ElementName": "天氣現象",    // Wx
    "Time": [{
      "StartTime": "...",
      "EndTime": "...",
      "ElementValue": [{ "value": "陰" }]
    }]
  }, ...]
}]
```

**Note:** `records.Locations[]` is a wrapper array containing `LocationsName` (county) and `Location[]` (districts).

---

### W-C0033-002 — 天氣特報 (Weather warnings)

**Purpose:** Active weather warnings and advisories with affected areas.

**Used in:** `cwa_fetch.py` → `fetch_warnings()`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `locationName` | array\<string\> | Filter by affected area. See [warnings area list PDF](https://opendata.cwa.gov.tw/opendatadoc/Opendata_Warnings.pdf) Appendix B. |
| `phenomena` | array\<string\> | Filter by warning type (see below). Default: all active. |

**Available phenomena values:**
`濃霧` (dense fog), `大雨` (heavy rain), `豪雨` (torrential rain), `大豪雨` (extreme rain), `超大豪雨` (super extreme rain), `陸上強風` (land gale), `颱風` (typhoon)

**Notes:**
- Returns only **currently active** warnings — empty result means no warnings in effect
- For our pipeline, we could filter by `locationName` for northern Taiwan areas only, but currently fetch all and filter client-side
- Sailors/surfers care most about: `陸上強風`, `颱風`, `濃霧`, `大雨`/`豪雨`

---

### F-D0047-093 — 全臺灣各鄉鎮市區預報 (All-Taiwan township forecast)

**Purpose:** Cross-county township forecast in a single call (max 5 county endpoints per call).

**Not yet used.** Could replace our 3 separate F-D0047 calls (001, 049, 069) with 1 call.

**Key constraint:** `locationId` is **required** — pass the county endpoint IDs (e.g. `F-D0047-001,F-D0047-049,F-D0047-069`). Max 5 per call.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `locationId` * | array\<string\> | **Required.** County endpoint IDs (F-D0047-001 to F-D0047-091, odd only). Min 1, max 5. |
| `LocationName` | array\<string\> | Township names within the selected counties. See [township list PDF](https://opendata.cwa.gov.tw/opendatadoc/Opendata_City.pdf). |
| `ElementName` | array\<string\> | Weather elements to return (Chinese names). |
| `timeFrom` / `timeTo` | datetime | Time range filter (`yyyy-MM-ddThh:mm:ss`) |
| `sort` | string | `time` for ascending time sort |

**Available ElementName values:**
`露點溫度`, `天氣預報綜合描述`, `舒適度指數`, `風向`, `3小時降雨機率`, `12小時降雨機率`, `溫度`, `風速`, `天氣現象`, `相對濕度`, `體感溫度`, `最高溫度`, `平均相對濕度`, `最高體感溫度`, `平均露點溫度`, `最低體感溫度`, `平均溫度`, `最大舒適度指數`, `最小舒適度指數`, `紫外線指數`, `最低溫度`

**For our pipeline**, a single call would be:
```
locationId=F-D0047-001,F-D0047-049,F-D0047-069
```
This fetches 宜蘭縣 + 基隆市 + 新北市 in one request.

---

## Endpoints Not Used But Potentially Useful

| Endpoint | Name | Potential Use |
|----------|------|---------------|
| O-A0003-001 | 10分鐘綜觀氣象 | Higher-frequency weather obs |
| A-B0062-001 | 日出日沒時刻 | Official sunrise/sunset (currently computed offline) |
| W-C0034-001 | 颱風警報 | Typhoon warnings |
| O-A0005-001 | 紫外線指數 | UV index for surf/sail planning |

---

## Common API Patterns

**Key casing varies by endpoint:**
- Some use `"Success"`, `"Result"`, `"Records"` (capitalized)
- Others use `"success"`, `"records"` (lowercase)
- Our parsing always checks both: `data.get("records") or data.get("Records")`

**Retry strategy:** 3 attempts with 5-second delay (`_cwa_get()` in `cwa_fetch.py`).

**Rate limits:** Not officially documented, but we keep calls modest (one burst of ~5 parallel calls per pipeline run, 4x daily).
