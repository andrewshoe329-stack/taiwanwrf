# CWA Open Data API Reference

Base URL: `https://opendata.cwa.gov.tw/api/v1/rest/datastore/{endpoint_id}`

All endpoints require `Authorization` query param (API key from `CWA_OPENDATA_KEY`).
All support `limit`, `offset`, `format` (JSON/XML) params.

---

## Forecasts

### F-A0021-001 — 潮汐預報 (Tide Forecast, 1 month)

Official CWA tide predictions (high/low times + heights) for coastal townships.

| Param | Type | Description |
|-------|------|-------------|
| `LocationName` | array | Township names. Ignored if `LocationId` set. Default: all. |
| `LocationId` | array | Township IDs. Overrides `LocationName`. |
| `WeatherElement` | array | `LunarDate`, `TideRange`, `Tide`, `TideHeights` |
| `TideRange` | array | `大`, `中`, `小` |
| `Date` | array | `yyyy-MM-dd` |
| `hhmmss` | array | `hh:mm:ss` |
| `timeFrom`/`timeTo` | datetime | Ignored if `Date`/`hhmmss` used |
| `sort` | array | `Date`, `DateTime` |

**Used in:** `cwa_fetch.py` → `fetch_tide_forecasts_multi()`

**Response:** `records.TideForecasts[].Location.{LocationName, TimePeriods.Daily[].Time[].{DateTime, Tide, TideHeights.{AboveTWVD, AboveLocalMSL, AboveChartDatum}}}`. Heights in **cm**, we convert to metres. `AboveLocalMSL` preferred (centered on 0).

**Our tide stations (northern Taiwan):**

| LocationName | LocationId | Lat | Lon | Nearest Spot |
|-------------|-----------|-----|-----|-------------|
| 基隆市中正區 | 10017010 | 25.151 | 121.790 | Keelung |
| 新北市金山區 | 65000270 | 25.248 | 121.638 | Jinshan |
| 新北市萬里區 | 65000280 | 25.211 | 121.689 | Green Bay |
| 新北市貢寮區 | 65000260 | 25.022 | 121.950 | Fulong |
| 宜蘭縣頭城鎮 | 10002040 | 24.867 | 121.838 | Daxi/DL/Wushih/Chousui |

---

### F-C0032-001 — 一般天氣預報 36小時 (County-level)

| Param | Type | Values |
|-------|------|--------|
| `locationName` | array | County names |
| `elementName` | array | `Wx`, `PoP`, `CI`, `MinT`, `MaxT` |

Not used — less granular than township forecasts.

---

### F-D0047-{XXX} — 鄉鎮天氣預報 (Township Forecasts)

Odd numbers = 3-day (3h periods). Even+1 = 1-week (12h periods).

| Endpoint | County | Used? |
|----------|--------|-------|
| F-D0047-001 / 003 | 宜蘭縣 3d / 1wk | Yes |
| F-D0047-049 / 051 | 基隆市 3d / 1wk | Yes |
| F-D0047-069 / 071 | 新北市 3d / 1wk | Yes |
| F-D0047-089 / 091 | 全臺灣 3d / 1wk | Alternative (fetches all counties, filter by `LocationName`) |
| F-D0047-093 | 全臺灣跨縣市 | Batch: `locationId=F-D0047-001,F-D0047-049,F-D0047-069` (max 5) |

| Param | Type | Description |
|-------|------|-------------|
| `LocationName` | array | Township names ([PDF](https://opendata.cwa.gov.tw/opendatadoc/Opendata_City.pdf)) |
| `ElementName` | array | See below |
| `timeFrom`/`timeTo` | datetime | Time range filter |
| `sort` | string | `time` |

**3-day ElementName:** `露點溫度`, `天氣預報綜合描述`, `舒適度指數`, `風向`, `3小時降雨機率`, `溫度`, `風速`, `天氣現象`, `相對濕度`, `體感溫度`

**1-week ElementName:** Above + `最高溫度`, `12小時降雨機率`, `最高體感溫度`, `平均露點溫度`, `最低體感溫度`, `平均溫度`, `最大舒適度指數`, `最小舒適度指數`, `紫外線指數`, `最低溫度`

**Response:** `records.Locations[].Location[].{LocationName, WeatherElement[].{ElementName, Time[].{StartTime, EndTime, ElementValue[]}}}`

---

### F-A0085-002/003 — 冷傷害指數 (Cold Injury Index)

| Endpoint | Resolution | Elements |
|----------|-----------|----------|
| F-A0085-002 | 5-day per township | `ColdInjuryIndex`, `ColdInjuryWarning` |
| F-A0085-003 | 72h 3-hourly | Same |

Params: `CountyName`, `TownName`, `WeatherElements`, `timeFrom`/`timeTo`

### F-A0085-004/005 — 溫差提醒 (Temperature Swing)

| Endpoint | Resolution | Elements |
|----------|-----------|----------|
| F-A0085-004 | 5-day | `MaxTemperature`, `MinTemperature`, `TemperatureDifferenceWarning` |
| F-A0085-005 | 72h 3-hourly | `TemperatureDifferenceIndex`, `TemperatureDifferenceWarning` |

### M-A0085-001 — 熱傷害指數 (Heat Injury, 5-day 3-hourly)

Elements: `HeatInjuryIndex`, `HeatInjuryWarning`. Params: `CountyName`, `TownName`.

---

## Observations

### O-A0001-001 — 氣象觀測站 逐時 (Weather Stations, hourly)

| Param | Type | Description |
|-------|------|-------------|
| `StationId` | array | Case-sensitive. [Station list](https://hdps.cwa.gov.tw/static/state.html). Overrides `StationName`. |
| `StationName` | array | Ignored if `StationId` set. |
| `WeatherElement` | array | `Weather`, `Now`, `WindDirection`, `WindSpeed`, `AirTemperature`, `RelativeHumidity`, `AirPressure`, `GustInfo`, `DailyHigh`, `DailyLow` |
| `GeoInfo` | array | `Coordinates`, `StationAltitude`, `CountyName`, `TownName`, `CountyCode`, `TownCode` |

**Used in:** `cwa_fetch.py` → `fetch_station_obs()`, `_fetch_spot_stations()`

**Nearby stations:**

| ID | Name | Lat | Lon | Nearest Spot |
|----|------|-----|-----|-------------|
| 466940 | 基隆 | 25.133 | 121.740 | Keelung |
| C0A940 | 金山 | 25.224 | 121.644 | Jinshan |
| C0AJ20 | 野柳 | 25.207 | 121.690 | Green Bay |
| C0B050 | 八斗子 | 25.145 | 121.792 | Keelung |
| C2A880 | 福隆 | 25.018 | 121.942 | Fulong |
| C0UA80 | 大溪漁港 | 24.942 | 121.903 | Daxi |
| C0U860 | 頭城 | 24.853 | 121.831 | Wushih/Chousui |
| C0U880 | 北關 | 24.907 | 121.873 | Daxi |

---

### O-A0002-001 — 雨量觀測站 (Rain Gauges)

| Param | Type | Description |
|-------|------|-------------|
| `StationId` | array | Same station list as O-A0001-001 |
| `RainfallElement` | array | `Now`, `Past10Min`, `Past1hr`, `Past3hr`, `Past6hr`, `Past12hr`, `Past24hr`, `Past2days`, `Past3days` |
| `GeoInfo` | array | Same as O-A0001-001 |

**Used in:** `accuracy_track.py` — `Past6hr` for precipitation verification.

---

### O-A0003-001 — 氣象觀測站 10分鐘 (10-min conventional obs)

Same params as O-A0001-001 plus extra elements:

**WeatherElement:** All of O-A0001-001 + `VisibilityDescription`, `SunshineDuration`, `UVIndex`, `Max10MinAverage`

**Used in:** `api/live-obs.js` — fetches visibility + UV for Keelung.

---

### O-A0005-001 — 紫外線指數 (Daily max UV)

Params: `StationID`. Published ~2PM daily. Simple endpoint.

---

### O-B0075-001 — 海象監測 48h (Marine: buoys + tide stations)

| Param | Type | Description |
|-------|------|-------------|
| `StationID` | array | [Station list](https://opendata.cwa.gov.tw/dataset/observation/O-B0076-001) |
| `WeatherElement` | array | `TideHeight`, `TideLevel`, `WaveHeight`, `WaveDirection`, `WaveDirectionDescription`, `WavePeriod`, `SeaTemperature`, `Temperature`, `StationPressure`, `PrimaryAnemometer`, `SeaCurrents` |
| `DataTime` | array | Exact times |
| `timeFrom`/`timeTo` | datetime | Ignored if `DataTime` used |
| `sort` | string | `StationID`, `DataTime` |

**Used in:** `cwa_fetch.py` → `_fetch_marine_stations()`, `fetch_buoy_obs()`, `fetch_tide_obs()`; `api/live-obs.js`

**Response:** `Records.SeaSurfaceObs.Location[].{Station.{StationID, StationName}, StationObsTimes.StationObsTime[].{DateTime, WeatherElements.{...}}}`

**Tide stations (潮位站):**

| ID | Name | Lat | Lon | Nearest Spot |
|----|------|-----|-----|-------------|
| C4B01 | 基隆 | 25.155 | 121.752 | Keelung |
| C4B03 | 長潭里 | 25.141 | 121.800 | Keelung (0.5km) |
| C4A03 | 麟山鼻 | 25.284 | 121.510 | Jinshan area |
| C4A02 | 龍洞 | 25.098 | 121.918 | Fulong area |
| C4A05 | 福隆 | 25.022 | 121.950 | **Fulong (0.2km!)** |
| C4U02 | 烏石 | 24.869 | 121.840 | **Wushih (0.4km!)** |
| C4U01 | 蘇澳 | 24.593 | 121.866 | — |

**Buoys (浮標站):**

| ID | Name | Lat | Lon | Nearest Spot |
|----|------|-----|-----|-------------|
| C6AH2 | 富貴角 | 25.304 | 121.531 | Jinshan (7km) |
| 46694A | 龍洞 | 25.099 | 121.923 | Fulong area |
| OAC004 | 潮境 | 25.144 | 121.808 | Keelung (1km) |
| 46708A | 龜山島 | 24.847 | 121.927 | NE coast |
| 46706A | 蘇澳 | 24.625 | 121.876 | — |
| OAC005 | 蜜月灣 | 24.949 | 121.929 | **Daxi (2km) — OFFLINE** |

`StationStatus`/`ObsStatus` = 1 active, 0 offline.

---

### O-B0075-002 — 海象監測 30天 (Marine, 30-day window)

Same as O-B0075-001 but 30-day history. **24h per request limit.** Default returns earliest 24h (not latest). Use `timeTo=now` to get recent data.

---

## Climate

### C-B0024-001 — 30天觀測 (30-day station obs + daily stats)

| Param | Type | Description |
|-------|------|-------------|
| `StationID` | array | Same station list |
| `WeatherElement` | array | `AirPressure`, `AirTemperature`, `RelativeHumidity`, `WindSpeed`, `WindDirection`, `Precipitation`, `SunshineDuration` |
| `StatisticsElement` | array | `Maximum`, `Minimum`, `Mean` |
| `DataType` | string | `stationObsTimes` (raw), `stationObsStatistics` (daily stats) |

Default returns latest 24h if no time params set.

### C-B0025-001 — 每日雨量 (Daily rainfall)

Params: `StationID`, `Date` (yyyy-MM-dd), `YearMonth` (yyyy-MM).

### C-B0027-001 — 月平均 (Monthly averages)

Params: `StationID`, `weatherElement` (same as C-B0024-001), `Month` (1-12).

### C-B0074-001/002 — 測站基本資料 (Station metadata)

001 = staffed, 002 = automated. Filter: `StationID`, `status` (`現存測站`/`已撤銷`).

---

## Warnings

### W-C0033-001 — 各縣市警特報情形 (County-level quick check)

| Param | Type | Values |
|-------|------|--------|
| `locationName` | array | County names |
| `phenomena` | array | `濃霧`, `大雨`, `豪雨`, `大豪雨`, `超大豪雨`, `陸上強風`, `海上陸上颱風` |

### W-C0033-002 — 天氣警特報詳情 (Detailed warnings)

| Param | Type | Values |
|-------|------|--------|
| `locationName` | array | Area names ([PDF](https://opendata.cwa.gov.tw/opendatadoc/Opendata_Warnings.pdf)) |
| `phenomena` | array | `濃霧`, `大雨`, `豪雨`, `大豪雨`, `超大豪雨`, `陸上強風`, `颱風` |

**Used in:** `cwa_fetch.py` → `fetch_warnings()`

### W-C0033-003 — 豪大雨特報 (Heavy Rain, CAP format)

Township-level. Params: `CountyName`, `TownName`, `geocode`, `severity_level` (`超大豪雨`/`大豪雨`/`豪雨`/`大雨`), `expires` (true/false).

### W-C0033-004 — 低溫特報 (Cold, CAP format)

`severity_level`: `低溫紅色燈號`, `低溫橙色燈號1`, `低溫橙色燈號2`, `低溫黃色燈號`

### W-C0033-005 — 高溫資訊 (Heat, CAP format)

`severity_level`: `高溫紅色燈號`, `高溫橙色36燈號`, `高溫橙色38燈號`, `高溫黃色燈號`

All CAP endpoints support: `info` filter (language, event, severity, headline, etc.), `parameter` filter, `geocode`, `expires=true`.

**Used in:** `cwa_fetch.py` → `fetch_specialized_warnings()`

### W-C0034-001 — 颱風警報 (Typhoon, CAP format)

| Param | Type | Values |
|-------|------|--------|
| `areaDesc` | array | Sea areas (`臺灣北部海面`, `臺灣東北部海面`) + counties |
| `headline` | string | `海上颱風警報`, `海上陸上颱風警報`, `解除颱風警報` |
| `cwaTyNo` | int | Typhoon number |
| `typhoonName` | array | English name |
| `description` | array | `typhoon-info`, `命名與位置`, `強度與半徑`, `移速與預測`, `颱風動態`, `警戒區域及事項` |
| `expires` | string | `true`/`false` |

### W-C0034-005 — 熱帶氣旋路徑 (Tropical cyclone tracks)

Params: `CwaTdNo`, `Dataset` (`AnalysisData`/`ForecastData`), `ForecastHour` (6-120).

---

## Astronomy

### A-B0062-001 — 日出日沒時刻 (Sunrise/Sunset)

| Param | Type | Description |
|-------|------|-------------|
| `CountyName` | array | County names |
| `Date` | array | `yyyy-MM-dd` (max 180 days) |
| `parameter` | array | `BeginCivilTwilightTime`, `SunRiseTime`, `SunRiseAZ`, `SunTransitTime`, `SunTransitAlt`, `SunSetTime`, `SunSetAZ`, `EndCivilTwilightTime` |
| `sort` | array | `CountyName`, `Date` |

**Used in:** `api/live-obs.js` — civil twilight for dawn patrol.

### A-B0063-001 — 月出月沒時刻 (Moonrise/Moonset)

Same params. Elements: `MoonRiseTime`, `MoonRiseAZ`, `MoonTransitTime`, `MoonTransitAlt`, `MoonSetTime`, `MoonSetAZ`.

---

## Common Patterns

**Key casing:** Some endpoints use `"Records"` (capitalized), others `"records"` (lowercase). Always check both.

**Retry:** 3 attempts, 5s delay (`_cwa_get()` in `cwa_fetch.py`).

**Rate limits:** Not officially documented. We use ~10 calls per pipeline run, 4x daily.

**Time format:** `yyyy-MM-ddThh:mm:ss` for all `timeFrom`/`timeTo` params.
