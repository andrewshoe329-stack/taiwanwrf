/**
 * Cloudflare Worker: Himawari satellite proxy
 *
 * Proxies NICT Himawari-9 tile requests to bypass IP-based blocking.
 * Cloudflare Workers use a different IP pool than Vercel (AWS Lambda),
 * so NICT allows these requests through.
 *
 * Endpoints:
 *   GET /latest?band=INFRARED_FULL
 *     → { date: "2026-03-31 06:10:00", band: "INFRARED_FULL" }
 *
 *   GET /tile?band=INFRARED_FULL&z=8&x=2&y=2&time=20260331061000
 *     → PNG image
 *
 * Deploy: cd workers/himawari-proxy && npx wrangler deploy
 */

const NICT_BASE = 'https://himawari8-dl.nict.go.jp/himawari8/img'
const VALID_BANDS = ['INFRARED_FULL', 'D531106']
const VALID_ZOOMS = [1, 2, 4, 8, 16, 20]

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
}

const NICT_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Referer': 'https://himawari8.nict.go.jp/',
  'Accept': '*/*',
}

function jsonResponse(data, status = 200, cacheSeconds = 120) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': `public, s-maxage=${cacheSeconds}, stale-while-revalidate=${cacheSeconds * 2}`,
      ...CORS_HEADERS,
    },
  })
}

export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS })
    }

    const url = new URL(request.url)
    const path = url.pathname.replace(/^\/+/, '')
    const params = url.searchParams
    const band = params.get('band') || 'INFRARED_FULL'

    if (!VALID_BANDS.includes(band)) {
      return jsonResponse({ error: 'Invalid band' }, 400)
    }

    // GET /latest?band=INFRARED_FULL
    if (path === 'latest') {
      try {
        const resp = await fetch(`${NICT_BASE}/${band}/latest.json`, {
          headers: NICT_HEADERS,
          cf: { cacheTtl: 60 },
        })
        if (!resp.ok) {
          return jsonResponse({ error: `NICT returned ${resp.status}` }, 502)
        }
        const data = await resp.json()
        return jsonResponse({ date: data.date, band }, 200, 60)
      } catch (err) {
        return jsonResponse({ error: 'NICT fetch failed', message: err.message }, 502)
      }
    }

    // GET /tile?band=INFRARED_FULL&z=8&x=2&y=2&time=20260331061000
    if (path === 'tile') {
      const z = parseInt(params.get('z'), 10)
      const x = parseInt(params.get('x'), 10)
      const y = parseInt(params.get('y'), 10)
      const time = params.get('time')

      if (!VALID_ZOOMS.includes(z) || isNaN(x) || isNaN(y) || !time) {
        return jsonResponse({ error: 'Invalid tile params' }, 400)
      }
      if (x < 0 || x >= z || y < 0 || y >= z) {
        return jsonResponse({ error: 'Tile coords out of range' }, 400)
      }
      if (!/^\d{14}$/.test(time)) {
        return jsonResponse({ error: 'Invalid time format' }, 400)
      }

      const yyyy = time.slice(0, 4)
      const mm = time.slice(4, 6)
      const dd = time.slice(6, 8)
      const hhmmss = time.slice(8, 14)
      const tileUrl = `${NICT_BASE}/${band}/${z}d/550/${yyyy}/${mm}/${dd}/${hhmmss}_${x}_${y}.png`

      try {
        const resp = await fetch(tileUrl, {
          headers: NICT_HEADERS,
          cf: { cacheTtl: 600 },
        })
        if (!resp.ok) {
          return jsonResponse({ error: `NICT tile returned ${resp.status}` }, resp.status)
        }

        return new Response(resp.body, {
          status: 200,
          headers: {
            'Content-Type': 'image/png',
            'Cache-Control': 'public, s-maxage=600, stale-while-revalidate=1800',
            ...CORS_HEADERS,
          },
        })
      } catch (err) {
        return jsonResponse({ error: 'NICT tile failed', message: err.message }, 502)
      }
    }

    return jsonResponse({ error: 'Unknown path. Use /latest or /tile', paths: ['latest', 'tile'] }, 400)
  },
}
