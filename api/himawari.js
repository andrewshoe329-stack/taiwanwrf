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

const NICT_BASE = 'https://himawari8-dl.nict.go.jp/himawari8/img'
const VALID_BANDS = ['INFRARED_FULL', 'D531106']
const VALID_ZOOMS = [1, 2, 4, 8, 16, 20]

export default async function handler(req, res) {
  const { q, band = 'INFRARED_FULL', z, x, y, time } = req.query

  if (!VALID_BANDS.includes(band)) {
    return res.status(400).json({ error: 'Invalid band' })
  }

  if (q === 'latest') {
    try {
      const resp = await fetch(`${NICT_BASE}/${band}/latest.json`, {
        signal: AbortSignal.timeout(10000),
      })
      if (!resp.ok) return res.status(502).json({ error: `NICT returned ${resp.status}` })
      const data = await resp.json()
      res.setHeader('Cache-Control', 's-maxage=120, stale-while-revalidate=300')
      res.setHeader('Access-Control-Allow-Origin', '*')
      return res.status(200).json({ date: data.date, band })
    } catch (err) {
      return res.status(502).json({ error: 'NICT fetch failed', message: err.message })
    }
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
    const url = `${NICT_BASE}/${band}/${zoom}d/550/${yyyy}/${mm}/${dd}/${hhmmss}_${tx}_${ty}.png`

    try {
      const resp = await fetch(url, {
        signal: AbortSignal.timeout(15000),
      })
      if (!resp.ok) {
        return res.status(resp.status).json({ error: `NICT tile returned ${resp.status}` })
      }

      const buffer = await resp.arrayBuffer()
      // Cache tiles for 10 minutes (images don't change once generated)
      res.setHeader('Cache-Control', 's-maxage=600, stale-while-revalidate=1800')
      res.setHeader('Access-Control-Allow-Origin', '*')
      res.setHeader('Content-Type', 'image/png')
      return res.status(200).send(Buffer.from(buffer))
    } catch (err) {
      return res.status(502).json({ error: 'NICT tile fetch failed', message: err.message })
    }
  }

  return res.status(400).json({ error: 'Missing q parameter (latest|tile)' })
}
