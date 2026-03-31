/**
 * Vercel serverless function: /api/live-obs
 *
 * Proxies real-time CWA observations so the frontend can show
 * truly live data without exposing the API key.
 *
 * Fetches in parallel:
 *   1. O-B0075-001 — tide stations + buoys (tide height, wave, sea temp)
 *   2. O-A0001-001 — weather stations (temp, wind, pressure)
 *
 * Returns merged JSON with per-spot observations.
 * Cached at edge for 5 minutes (CWA updates every 10-60 min).
 */

const CWA_BASE = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore'

// Stations to query — only northern Taiwan, keeps payload small
const MARINE_STATIONS = [
  'C4B01',  // 基隆 tide
  'C4A05',  // 福隆 tide (0.2km from spot!)
  'C4U02',  // 烏石 tide (0.4km from spot!)
  'C4A03',  // 麟山鼻 tide (Jinshan area)
  'C4A02',  // 龍洞 tide (Fulong area)
  'C4B03',  // 長潭里 tide (Keelung alt)
  '46694A', // 龍洞 buoy (wave data)
  '46708A', // 龜山島 buoy (NE coast)
  'C6AH2',  // 富貴角 buoy (north coast)
].join(',')

const WEATHER_STATIONS = [
  '466940', // 基隆 (staffed)
  'C0A940', // 金山
  'C0AJ20', // 野柳 (Green Bay)
  'C0B050', // 八斗子 (Keelung)
  'C2A880', // 福隆
  'C0UA80', // 大溪漁港 (Daxi)
  'C0U860', // 頭城 (Wushih/Chousui)
  'C0U880', // 北關 (Daxi area)
].join(',')

// Spot → nearest stations mapping (weather_alt: fallback stations for wind)
const SPOT_STATIONS = {
  keelung:     { weather: '466940', weather_alt: ['C0B050'],                   tide: 'C4B01',  buoy: '46694A' },
  jinshan:     { weather: 'C0A940', weather_alt: ['C0AJ20', '466940'],         tide: 'C4A03',  buoy: 'C6AH2'  },
  greenbay:    { weather: 'C0AJ20', weather_alt: ['C0B050', '466940'],         tide: 'C4B01',  buoy: '46694A' },
  fulong:      { weather: 'C2A880', weather_alt: ['C0AJ20', 'C0U880'],         tide: 'C4A05',  buoy: '46694A' },
  daxi:        { weather: 'C0UA80', weather_alt: ['C0U880', 'C0U860'],         tide: 'C4U02',  buoy: '46708A' },
  doublelions: { weather: 'C0U860', weather_alt: ['C0U880', 'C0UA80'],         tide: 'C4U02',  buoy: '46708A' },
  wushih:      { weather: 'C0U860', weather_alt: ['C0U880', 'C0UA80'],         tide: 'C4U02',  buoy: '46708A' },
  chousui:     { weather: 'C0U860', weather_alt: ['C0U880', 'C0UA80'],         tide: 'C4U02',  buoy: '46708A' },
}

async function fetchCwa(endpoint, params) {
  const url = new URL(`${CWA_BASE}/${endpoint}`)
  url.searchParams.set('Authorization', process.env.CWA_OPENDATA_KEY)
  url.searchParams.set('format', 'JSON')
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v)
  }

  const res = await fetch(url.toString(), {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(15000),
  })
  if (!res.ok) return null
  return res.json()
}

function parseMarineObs(data) {
  if (!data) return {}
  const records = data.records || data.Records || {}
  const locations = records?.SeaSurfaceObs?.Location || []
  const result = {}

  for (const loc of locations) {
    const station = loc.Station || {}
    const id = station.StationID
    if (!id) continue

    const obsTimes = loc.StationObsTimes?.StationObsTime || []
    const latest = obsTimes[obsTimes.length - 1]
    if (!latest) continue

    const we = latest.WeatherElements || {}
    const entry = {
      station_id: id,
      station_name: station.StationName,
      obs_time: latest.DateTime,
      attribute: station.StationAttribute,
    }

    // Tide data
    const tideH = we.TideHeight
    if (tideH != null && tideH !== 'None' && tideH !== '') {
      entry.tide_height_m = parseFloat(tideH)
    }
    if (we.TideLevel) entry.tide_level = we.TideLevel

    // Wave data
    if (we.WaveHeight != null && we.WaveHeight !== 'None') {
      entry.wave_height_m = parseFloat(we.WaveHeight)
    }
    if (we.WavePeriod != null && we.WavePeriod !== 'None') {
      entry.wave_period_s = parseFloat(we.WavePeriod)
    }
    if (we.WaveDirection != null && we.WaveDirection !== 'None') {
      entry.wave_dir = parseFloat(we.WaveDirection)
    }

    // Sea temperature
    if (we.SeaTemperature != null && we.SeaTemperature !== 'None') {
      entry.sea_temp_c = parseFloat(we.SeaTemperature)
    }

    // Wind (from buoys/some tide stations)
    const anemometer = we.PrimaryAnemometer
    if (anemometer && typeof anemometer === 'object') {
      if (anemometer.WindSpeed != null && anemometer.WindSpeed !== 'None') {
        entry.wind_speed_ms = parseFloat(anemometer.WindSpeed)
      }
      if (anemometer.WindDirection != null && anemometer.WindDirection !== 'None') {
        entry.wind_dir = parseFloat(anemometer.WindDirection)
      }
    }

    // Sea currents
    if (we.CurrentSpeed != null && we.CurrentSpeed !== 'None') {
      entry.current_speed_ms = parseFloat(we.CurrentSpeed)
    }
    if (we.CurrentDirection != null && we.CurrentDirection !== 'None') {
      entry.current_dir = parseFloat(we.CurrentDirection)
    }

    result[id] = entry
  }

  return result
}

function parseWeatherObs(data) {
  if (!data) return {}
  const records = data.records || data.Records || {}
  const stations = records.Station || records.station || []
  const result = {}

  for (const stn of Array.isArray(stations) ? stations : [stations]) {
    const id = stn.StationId || stn.stationId
    if (!id) continue

    // WeatherElement can be an object or an array of {ElementName, ElementValue}
    let obs = stn.WeatherElement || stn.weatherElement || {}
    if (Array.isArray(obs)) {
      const converted = {}
      for (const el of obs) {
        const name = el.ElementName || el.elementName
        const val = el.ElementValue ?? el.elementValue ?? el.Value ?? el.value
        if (name) converted[name] = val
      }
      obs = converted
    }
    const obsTime = stn.ObsTime?.DateTime || stn.obsTime?.dateTime

    const entry = {
      station_id: id,
      station_name: stn.StationName || stn.stationName,
      obs_time: obsTime,
    }

    // Temperature
    const temp = obs.AirTemperature
    if (temp != null && typeof temp === 'object') {
      entry.temp_c = parseFloat(temp.value ?? temp.Value ?? temp)
    } else if (temp != null) {
      entry.temp_c = parseFloat(temp)
    }

    // Wind — handle both object {value: "3.2"} and plain number/string formats
    const ws = obs.WindSpeed
    if (ws != null) {
      const v = parseFloat(typeof ws === 'object' ? (ws.value ?? ws.Value ?? ws) : ws)
      if (!isNaN(v)) entry.wind_kt = v * 1.94384 // m/s → kt
    }
    const wd = obs.WindDirection
    if (wd != null) {
      const v = parseFloat(typeof wd === 'object' ? (wd.value ?? wd.Value ?? wd) : wd)
      if (!isNaN(v)) entry.wind_dir = v
    }

    // Gust
    const gust = obs.GustInfo?.PeakGustSpeed
    if (gust != null) {
      const v = parseFloat(typeof gust === 'object' ? (gust.value ?? gust.Value ?? gust) : gust)
      if (!isNaN(v)) entry.gust_kt = v * 1.94384
    }

    // Pressure
    const pres = obs.AirPressure
    if (pres != null) {
      const v = parseFloat(typeof pres === 'object' ? (pres.value ?? pres.Value ?? pres) : pres)
      if (!isNaN(v)) entry.pressure_hpa = v
    }

    // Humidity
    const rh = obs.RelativeHumidity
    if (rh != null) {
      const v = parseFloat(typeof rh === 'object' ? (rh.value ?? rh.Value ?? rh) : rh)
      if (!isNaN(v)) entry.humidity_pct = v
    }

    // Visibility (from O-A0003-001 10-min obs)
    const vis = obs.VisibilityDescription
    if (vis != null && typeof vis === 'string' && vis !== '') {
      // CWA returns visibility as text like "10.0" or ">10" in km
      const visNum = parseFloat(vis.replace('>', '').replace('<', ''))
      if (!isNaN(visNum)) entry.visibility_km = visNum
    } else if (vis != null && typeof vis === 'object') {
      const v = parseFloat(vis.value ?? vis.Value ?? '')
      if (!isNaN(v)) entry.visibility_km = v
    }

    // UV Index (from O-A0003-001 10-min obs)
    const uv = obs.UVIndex
    if (uv != null && typeof uv === 'object') {
      const v = parseFloat(uv.value ?? uv.Value ?? uv)
      if (!isNaN(v)) entry.uv_index = v
    } else if (uv != null && typeof uv === 'number') {
      entry.uv_index = uv
    } else if (uv != null && typeof uv === 'string' && uv !== '') {
      const v = parseFloat(uv)
      if (!isNaN(v)) entry.uv_index = v
    }

    // Filter out NaN values
    for (const [k, v] of Object.entries(entry)) {
      if (typeof v === 'number' && isNaN(v)) delete entry[k]
    }

    result[id] = entry
  }

  return result
}

function buildSpotObs(marineObs, weatherObs) {
  const spots = {}
  for (const [spotId, mapping] of Object.entries(SPOT_STATIONS)) {
    const entry = {}

    // Weather station — try primary, then fallbacks for wind
    const ws = weatherObs[mapping.weather]
    if (ws) {
      entry.station = {
        station_id: ws.station_id,
        station_name: ws.station_name,
        obs_time: ws.obs_time,
        temp_c: ws.temp_c,
        wind_kt: ws.wind_kt != null ? Math.round(ws.wind_kt * 10) / 10 : undefined,
        wind_dir: ws.wind_dir,
        gust_kt: ws.gust_kt != null ? Math.round(ws.gust_kt * 10) / 10 : undefined,
        pressure_hpa: ws.pressure_hpa,
        humidity_pct: ws.humidity_pct,
        visibility_km: ws.visibility_km,
        uv_index: ws.uv_index,
      }
    }

    // If primary station has no wind, try fallback stations
    if (entry.station?.wind_kt == null && mapping.weather_alt) {
      for (const altId of mapping.weather_alt) {
        const alt = weatherObs[altId]
        if (alt?.wind_kt != null) {
          entry.station = entry.station || {
            station_id: alt.station_id,
            station_name: alt.station_name,
            obs_time: alt.obs_time,
          }
          entry.station.wind_kt = Math.round(alt.wind_kt * 10) / 10
          entry.station.wind_dir = alt.wind_dir
          if (alt.gust_kt != null) entry.station.gust_kt = Math.round(alt.gust_kt * 10) / 10
          entry.station.wind_source = altId
          break
        }
      }
    }

    // If no station at all, create one from the best fallback that has data
    if (!entry.station && mapping.weather_alt) {
      for (const altId of mapping.weather_alt) {
        const alt = weatherObs[altId]
        if (alt) {
          entry.station = {
            station_id: alt.station_id,
            station_name: alt.station_name,
            obs_time: alt.obs_time,
            temp_c: alt.temp_c,
            wind_kt: alt.wind_kt != null ? Math.round(alt.wind_kt * 10) / 10 : undefined,
            wind_dir: alt.wind_dir,
            gust_kt: alt.gust_kt != null ? Math.round(alt.gust_kt * 10) / 10 : undefined,
            pressure_hpa: alt.pressure_hpa,
            humidity_pct: alt.humidity_pct,
            wind_source: altId,
          }
          break
        }
      }
    }

    // Inherit visibility/UV from Keelung if local station doesn't have it
    if (entry.station && entry.station.visibility_km == null) {
      const kl = weatherObs['466940']
      if (kl?.visibility_km != null) entry.station.visibility_km = kl.visibility_km
      if (kl?.uv_index != null && entry.station.uv_index == null) entry.station.uv_index = kl.uv_index
    }

    // Tide station
    const ts = marineObs[mapping.tide]
    if (ts) {
      entry.tide = {
        station_id: ts.station_id,
        station_name: ts.station_name,
        obs_time: ts.obs_time,
        tide_height_m: ts.tide_height_m,
        tide_level: ts.tide_level,
        sea_temp_c: ts.sea_temp_c,
      }
    }

    // Buoy
    const buoy = marineObs[mapping.buoy]
    if (buoy) {
      entry.buoy = {
        station_id: buoy.station_id,
        station_name: buoy.station_name,
        obs_time: buoy.obs_time,
        wave_height_m: buoy.wave_height_m,
        wave_period_s: buoy.wave_period_s,
        wave_dir: buoy.wave_dir,
        sea_temp_c: buoy.sea_temp_c,
        wind_kt: buoy.wind_speed_ms != null ? Math.round(buoy.wind_speed_ms * 1.94384 * 10) / 10 : undefined,
        wind_dir: buoy.wind_dir,
        current_speed_ms: buoy.current_speed_ms,
        current_dir: buoy.current_dir,
      }
    }

    // If buoy has no wind, try tide station's anemometer (many tide stations report wind)
    if (entry.buoy && entry.buoy.wind_kt == null) {
      const ts = marineObs[mapping.tide]
      if (ts?.wind_speed_ms != null) {
        entry.buoy.wind_kt = Math.round(ts.wind_speed_ms * 1.94384 * 10) / 10
        entry.buoy.wind_dir = ts.wind_dir
      }
    }

    if (Object.keys(entry).length > 0) {
      spots[spotId] = entry
    }
  }
  return spots
}

export default async function handler(req, res) {
  if (!process.env.CWA_OPENDATA_KEY) {
    return res.status(503).json({ error: 'CWA API key not configured' })
  }

  try {
    // Fetch marine obs + weather obs + 10-min obs in parallel (3 API calls)
    // Use allSettled so partial failures don't kill the entire response
    const today = new Date().toISOString().slice(0, 10)
    const results = await Promise.allSettled([
      fetchCwa('O-B0075-001', {
        StationID: MARINE_STATIONS,
        WeatherElement: 'TideHeight,TideLevel,WaveHeight,WaveDirection,WavePeriod,SeaTemperature,PrimaryAnemometer,SeaCurrents',
        sort: 'DataTime',
      }),
      fetchCwa('O-A0001-001', {
        StationId: WEATHER_STATIONS,
      }),
      fetchCwa('O-A0003-001', {
        StationId: '466940',
        WeatherElement: 'VisibilityDescription,UVIndex',
      }),
      fetchCwa('A-B0062-001', {
        CountyName: '基隆市',
        Date: today,
        parameter: 'SunRiseTime,SunSetTime,BeginCivilTwilightTime,EndCivilTwilightTime',
      }),
    ])

    const marineData = results[0].status === 'fulfilled' ? results[0].value : null
    const weatherData = results[1].status === 'fulfilled' ? results[1].value : null
    const tenMinData = results[2].status === 'fulfilled' ? results[2].value : null
    const sunData = results[3].status === 'fulfilled' ? results[3].value : null

    const marineObs = parseMarineObs(marineData)
    const weatherObs = parseWeatherObs(weatherData)

    // Parse 10-min obs for visibility/UV
    const tenMinObs = parseWeatherObs(tenMinData)
    // Merge visibility/UV into Keelung weather station
    const keelungTenMin = tenMinObs['466940']
    if (keelungTenMin) {
      if (!weatherObs['466940']) weatherObs['466940'] = keelungTenMin
      else {
        if (keelungTenMin.visibility_km != null) weatherObs['466940'].visibility_km = keelungTenMin.visibility_km
        if (keelungTenMin.uv_index != null) weatherObs['466940'].uv_index = keelungTenMin.uv_index
      }
    }

    const spots = buildSpotObs(marineObs, weatherObs)

    let sun = null
    if (sunData) {
      try {
        const records = sunData.records || sunData.Records || {}
        const locations = records.locations?.location || records.Location || []
        const loc = Array.isArray(locations) ? locations[0] : locations
        const timeData = loc?.time?.[0] || {}
        sun = {
          civil_twilight_start: timeData.BeginCivilTwilightTime || timeData.parameter?.find?.(p => p.parameterName === 'BeginCivilTwilightTime')?.parameterValue,
          sunrise: timeData.SunRiseTime || timeData.parameter?.find?.(p => p.parameterName === 'SunRiseTime')?.parameterValue,
          sunset: timeData.SunSetTime || timeData.parameter?.find?.(p => p.parameterName === 'SunSetTime')?.parameterValue,
          civil_twilight_end: timeData.EndCivilTwilightTime || timeData.parameter?.find?.(p => p.parameterName === 'EndCivilTwilightTime')?.parameterValue,
          date: today,
        }
      } catch { /* ignore parse errors */ }
    }

    const result = {
      fetched_utc: new Date().toISOString(),
      spots,
      marine_stations: marineObs,
      weather_stations: weatherObs,
      sun,
    }

    // Cache at edge for 5 minutes, stale-while-revalidate for 15 min
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=900')
    res.setHeader('Access-Control-Allow-Origin', '*')
    return res.status(200).json(result)

  } catch (err) {
    console.error('live-obs error:', err)
    return res.status(502).json({ error: 'CWA fetch failed', message: err.message })
  }
}
