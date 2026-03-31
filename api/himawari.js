/**
 * Vercel serverless function: /api/himawari
 *
 * Proxies NICT Himawari-9 satellite imagery to avoid CORS issues.
 * Free, non-commercial use. Updates every 10 minutes.
 *
 * Endpoints:
 *   GET /api/himawari?q=latest&band=INFRARED_FULL
 *     → Returns { date: "...", band: "..." }
 *
 *   GET /api/himawari?q=tile&band=INFRARED_FULL&z=8&x=2&y=2&time=20260331120000
 *     → Proxies tile PNG from NICT
 *
 * Source: https://himawari8.nict.go.jp/
 */

const NICT_BASE = 'https://himawari8-dl.nict.go.jp/himawari9/img'
const NICT_BASE_LEGACY = 'https://himawari8-dl.nict.go.jp/himawari8/img'
const JMA_BASE = 'https://www.data.jma.go.jp/mscweb/data/himawari/img/se2'
const VALID_BANDS = ['INFRARED_FULL', 'D531106']
const VALID_ZOOMS = [1, 2, 4, 8, 16, 20]

// Map NICT bands to JMA MSC band codes
const NICT_TO_JMA_BAND = {
  'INFRARED_FULL': 'b13',  // 10.4μm IR
  'D531106': 'trm',        // true color (visible)
}

const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Referer': 'https://himawari8.nict.go.jp/',
  'Accept': 'application/json, image/png, image/jpeg, */*',
}

export default async function handler(req, res) {
  const { q, band = 'INFRARED_FULL', z, x, y, time } = req.query

  if (!VALID_BANDS.includes(band)) {
    return res.status(400).json({ error: 'Invalid band' })
  }

  if (q === 'latest') {
    // Try NICT first (himawari9 path, then legacy himawari8)
    for (const base of [NICT_BASE, NICT_BASE_LEGACY]) {
      try {
        const resp = await fetch(`${base}/${band}/latest.json`, {
          signal: AbortSignal.timeout(6000),
          headers: FETCH_HEADERS,
        })
        if (!resp.ok) continue
        const data = await resp.json()
        res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
        res.setHeader('Access-Control-Allow-Origin', '*')
        return res.status(200).json({ date: data.date, band, source: 'nict' })
      } catch { /* try next */ }
    }

    // Fallback: JMA MSC regional images (updated every 10 min, ~40 min delay)
    // Compute latest available time: round down to nearest 10 min, subtract 40 min lag
    const now = new Date()
    const lagMs = 50 * 60 * 1000 // ~50 min processing delay
    const avail = new Date(now.getTime() - lagMs)
    const mm = Math.floor(avail.getUTCMinutes() / 10) * 10
    avail.setUTCMinutes(mm, 0, 0)
    const jmaBand = NICT_TO_JMA_BAND[band] || 'b13'
    const hhmm = String(avail.getUTCHours()).padStart(2, '0') + String(mm).padStart(2, '0')

    // Verify the JMA image actually exists
    try {
      const jmaUrl = `${JMA_BASE}/se2_${jmaBand}_${hhmm}.jpg`
      const resp = await fetch(jmaUrl, {
        method: 'HEAD',
        signal: AbortSignal.timeout(5000),
        headers: FETCH_HEADERS,
      })
      if (resp.ok) {
        res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
        res.setHeader('Access-Control-Allow-Origin', '*')
        return res.status(200).json({ date: avail.toISOString(), band, source: 'jma', jmaBand, hhmm })
      }
    } catch { /* fall through */ }

    return res.status(502).json({ error: 'Both NICT and JMA sources unavailable' })
  }

  if (q === 'tile') {
    const zoom = parseInt(z, 10)
    const tx = parseInt(x, 10)
    const ty = parseInt(y, 10)

    if (!VALID_ZOOMS.includes(zoom) || isNaN(tx) || isNaN(ty) || !time) {
      return res.status(400).json({ error: 'Invalid tile params' })
    }

    // Validate tile coords within grid
    if (tx < 0 || tx >= zoom || ty < 0 || ty >= zoom) {
      return res.status(400).json({ error: 'Tile coords out of range' })
    }

    // Validate time format: YYYYMMDDHHMMSS (14 digits)
    if (!/^\d{14}$/.test(time)) {
      return res.status(400).json({ error: 'Invalid time format' })
    }

    // Build NICT URL: {base}/{band}/{z}d/550/{YYYY}/{MM}/{DD}/{HHMMSS}_{x}_{y}.png
    const yyyy = time.slice(0, 4)
    const mm = time.slice(4, 6)
    const dd = time.slice(6, 8)
    const hhmmss = time.slice(8, 14)
    const tilePath = `/${band}/${zoom}d/550/${yyyy}/${mm}/${dd}/${hhmmss}_${tx}_${ty}.png`

    // Try himawari9 path first, then legacy himawari8
    for (const base of [NICT_BASE, NICT_BASE_LEGACY]) {
      try {
        const resp = await fetch(`${base}${tilePath}`, {
          signal: AbortSignal.timeout(12000),
          headers: FETCH_HEADERS,
        })
        if (!resp.ok) continue

        const buffer = await resp.arrayBuffer()
        // Cache tiles for 10 minutes (images don't change once generated)
        res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=1800')
        res.setHeader('Access-Control-Allow-Origin', '*')
        res.setHeader('Content-Type', 'image/png')
        return res.status(200).send(Buffer.from(buffer))
      } catch { /* try next */ }
    }
    return res.status(502).json({ error: 'NICT tile fetch failed (both paths)' })
  }

  if (q === 'regional') {
    // Proxy a full JMA MSC SE2 regional image (fallback when NICT tiles fail)
    const jmaBand = req.query.jmaBand || NICT_TO_JMA_BAND[band] || 'b13'
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
