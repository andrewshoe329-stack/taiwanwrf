/**
 * Vercel serverless function: /api/himawari
 *
 * Proxies Himawari-9 satellite imagery with automatic fallback:
 *   1. NICT (himawari8-dl.nict.go.jp) — primary, tile-based
 *   2. RAMMB/CIRA SLIDER — tile-based fallback (same projection)
 *   3. JMA MSC SE2 — regional image fallback
 *
 * Endpoints:
 *   GET /api/himawari?q=latest&band=INFRARED_FULL
 *     → Returns { date, band, source }
 *
 *   GET /api/himawari?q=tile&band=INFRARED_FULL&z=8&x=2&y=2&time=20260331120000
 *     → Proxies tile PNG (NICT → SLIDER fallback)
 *
 *   GET /api/himawari?q=regional&band=INFRARED_FULL&jmaBand=b13&hhmm=0510
 *     → Proxies JMA MSC SE2 regional JPEG
 */

const NICT_BASE = 'https://himawari8-dl.nict.go.jp/himawari8/img'
const SLIDER_BASE = 'https://rammb-slider.cira.colostate.edu/data'
const JMA_BASE = 'https://www.data.jma.go.jp/mscweb/data/himawari/img/se2'
const VALID_BANDS = ['INFRARED_FULL', 'D531106']
const VALID_ZOOMS = [1, 2, 4, 8, 16, 20]

// Band mapping across providers
const NICT_TO_SLIDER = { 'INFRARED_FULL': 'band_13', 'D531106': 'geocolor' }
const NICT_TO_JMA = { 'INFRARED_FULL': 'b13', 'D531106': 'trm' }

const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Accept': 'application/json, image/png, image/jpeg, */*',
}

/** Build SLIDER tile URL from NICT-style params */
function sliderTileUrl(band, zoom, tx, ty, time) {
  const product = NICT_TO_SLIDER[band] || 'band_13'
  const sliderZoom = Math.round(Math.log2(zoom))
  const yyyy = time.slice(0, 4)
  const mm = time.slice(4, 6)
  const dd = time.slice(6, 8)
  const pad2 = (n) => String(n).padStart(2, '0')
  const pad3 = (n) => String(n).padStart(3, '0')
  return `${SLIDER_BASE}/imagery/${yyyy}/${mm}/${dd}/himawari---full_disk/${product}/${time}/${pad2(sliderZoom)}/${pad3(ty)}_${pad3(tx)}.png`
}

export default async function handler(req, res) {
  const { q, band = 'INFRARED_FULL', z, x, y, time } = req.query

  if (!VALID_BANDS.includes(band)) {
    return res.status(400).json({ error: 'Invalid band' })
  }

  if (q === 'latest') {
    // 1. Try NICT
    try {
      const resp = await fetch(`${NICT_BASE}/${band}/latest.json`, {
        signal: AbortSignal.timeout(5000),
        headers: { ...FETCH_HEADERS, Referer: 'https://himawari8.nict.go.jp/' },
      })
      if (resp.ok) {
        const data = await resp.json()
        res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
        res.setHeader('Access-Control-Allow-Origin', '*')
        return res.status(200).json({ date: data.date, band, source: 'nict' })
      }
    } catch { /* fall through */ }

    // 2. Try SLIDER
    const sliderProduct = NICT_TO_SLIDER[band] || 'band_13'
    try {
      const resp = await fetch(
        `${SLIDER_BASE}/json/himawari/full_disk/${sliderProduct}/latest_times.json`,
        { signal: AbortSignal.timeout(5000), headers: FETCH_HEADERS }
      )
      if (resp.ok) {
        const data = await resp.json()
        const ts = data.timestamps_int?.[0]
        if (ts) {
          // Convert SLIDER timestamp (YYYYMMDDHHmmSS) to ISO date
          const iso = `${ts.slice(0,4)}-${ts.slice(4,6)}-${ts.slice(6,8)}T${ts.slice(8,10)}:${ts.slice(10,12)}:${ts.slice(12,14)}Z`
          res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
          res.setHeader('Access-Control-Allow-Origin', '*')
          return res.status(200).json({ date: iso, band, source: 'slider', sliderTime: String(ts) })
        }
      }
    } catch { /* fall through */ }

    // 3. Try JMA MSC
    const now = new Date()
    const avail = new Date(now.getTime() - 50 * 60 * 1000)
    const mm = Math.floor(avail.getUTCMinutes() / 10) * 10
    avail.setUTCMinutes(mm, 0, 0)
    const jmaBand = NICT_TO_JMA[band] || 'b13'
    const hhmm = String(avail.getUTCHours()).padStart(2, '0') + String(mm).padStart(2, '0')
    try {
      const jmaUrl = `${JMA_BASE}/se2_${jmaBand}_${hhmm}.jpg`
      const resp = await fetch(jmaUrl, {
        method: 'HEAD', signal: AbortSignal.timeout(5000), headers: FETCH_HEADERS,
      })
      if (resp.ok) {
        res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
        res.setHeader('Access-Control-Allow-Origin', '*')
        return res.status(200).json({ date: avail.toISOString(), band, source: 'jma', jmaBand, hhmm })
      }
    } catch { /* fall through */ }

    return res.status(502).json({ error: 'All satellite sources unavailable (NICT, SLIDER, JMA)' })
  }

  if (q === 'tile') {
    const zoom = parseInt(z, 10)
    const tx = parseInt(x, 10)
    const ty = parseInt(y, 10)

    if (!VALID_ZOOMS.includes(zoom) || isNaN(tx) || isNaN(ty) || !time) {
      return res.status(400).json({ error: 'Invalid tile params' })
    }
    if (tx < 0 || tx >= zoom || ty < 0 || ty >= zoom) {
      return res.status(400).json({ error: 'Tile coords out of range' })
    }
    if (!/^\d{14}$/.test(time)) {
      return res.status(400).json({ error: 'Invalid time format' })
    }

    const yyyy = time.slice(0, 4)
    const mm = time.slice(4, 6)
    const dd = time.slice(6, 8)
    const hhmmss = time.slice(8, 14)

    // 1. Try NICT
    const nictUrl = `${NICT_BASE}/${band}/${zoom}d/550/${yyyy}/${mm}/${dd}/${hhmmss}_${tx}_${ty}.png`
    try {
      const resp = await fetch(nictUrl, {
        signal: AbortSignal.timeout(8000),
        headers: { ...FETCH_HEADERS, Referer: 'https://himawari8.nict.go.jp/' },
      })
      if (resp.ok) {
        const buffer = await resp.arrayBuffer()
        res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=1800')
        res.setHeader('Access-Control-Allow-Origin', '*')
        res.setHeader('Content-Type', 'image/png')
        return res.status(200).send(Buffer.from(buffer))
      }
    } catch { /* fall through */ }

    // 2. Try SLIDER (zoom must be power of 2 and ≤ 16)
    const sliderZoom = Math.log2(zoom)
    if (Number.isInteger(sliderZoom) && sliderZoom <= 4) {
      try {
        const sUrl = sliderTileUrl(band, zoom, tx, ty, time)
        const resp = await fetch(sUrl, {
          signal: AbortSignal.timeout(10000),
          headers: FETCH_HEADERS,
        })
        if (resp.ok) {
          const buffer = await resp.arrayBuffer()
          res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=1800')
          res.setHeader('Access-Control-Allow-Origin', '*')
          res.setHeader('Content-Type', 'image/png')
          return res.status(200).send(Buffer.from(buffer))
        }
      } catch { /* fall through */ }
    }

    return res.status(502).json({ error: 'Tile fetch failed (NICT + SLIDER)' })
  }

  if (q === 'regional') {
    const jmaBand = req.query.jmaBand || NICT_TO_JMA[band] || 'b13'
    const hhmm = req.query.hhmm
    if (!hhmm || !/^\d{4}$/.test(hhmm)) {
      return res.status(400).json({ error: 'Invalid hhmm parameter' })
    }
    const jmaUrl = `${JMA_BASE}/se2_${jmaBand}_${hhmm}.jpg`
    try {
      const resp = await fetch(jmaUrl, {
        signal: AbortSignal.timeout(15000),
        headers: FETCH_HEADERS,
      })
      if (!resp.ok) {
        return res.status(resp.status).json({ error: `JMA returned ${resp.status}` })
      }
      const buffer = await resp.arrayBuffer()
      res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=1800')
      res.setHeader('Access-Control-Allow-Origin', '*')
      res.setHeader('Content-Type', 'image/jpeg')
      return res.status(200).send(Buffer.from(buffer))
    } catch (err) {
      return res.status(502).json({ error: 'JMA fetch failed', message: err.message })
    }
  }

  return res.status(400).json({ error: 'Missing q parameter (latest|tile|regional)' })
}
