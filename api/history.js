/**
 * Vercel serverless function: /api/history
 *
 * Returns historical daily summaries from Firebase Firestore.
 * Each document in the `daily_archive` collection contains
 * min/max/avg for temp, wind, gust, wave, precip, and pressure.
 *
 * Query params:
 *   ?days=30  — number of days to return (default 30, max 90)
 *
 * Cached at edge for 1 hour (archive data doesn't change retroactively).
 */

export default async function handler(req, res) {
  // Only allow GET
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const days = Math.min(Math.max(parseInt(req.query.days, 10) || 30, 1), 90)

  try {
    // Dynamic import firebase-admin (only available when FIREBASE_PROJECT is set)
    if (!process.env.FIREBASE_PROJECT) {
      return res.status(503).json({ error: 'Firebase not configured' })
    }

    const admin = await import('firebase-admin')

    // Initialize if not already
    if (!admin.default.apps.length) {
      const cred = process.env.GOOGLE_APPLICATION_CREDENTIALS
        ? admin.default.credential.applicationDefault()
        : process.env.FIREBASE_SA_KEY
          ? admin.default.credential.cert(JSON.parse(process.env.FIREBASE_SA_KEY))
          : undefined

      if (!cred) {
        return res.status(503).json({ error: 'Firebase credentials not configured' })
      }

      admin.default.initializeApp({
        credential: cred,
        projectId: process.env.FIREBASE_PROJECT,
      })
    }

    const db = admin.default.firestore()
    const cutoffDate = new Date()
    cutoffDate.setDate(cutoffDate.getDate() - days)
    const cutoff = cutoffDate.toISOString().slice(0, 10)

    const snapshot = await db
      .collection('daily_archive')
      .where('date', '>=', cutoff)
      .orderBy('date', 'asc')
      .get()

    const entries = []
    snapshot.forEach(doc => {
      entries.push(doc.data())
    })

    // Cache at edge for 1 hour, stale-while-revalidate for 6 hours
    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=21600')
    res.setHeader('Access-Control-Allow-Origin', '*')
    return res.status(200).json({ days: entries.length, entries })

  } catch (err) {
    console.error('history error:', err)
    return res.status(502).json({ error: 'Failed to fetch history', message: err.message })
  }
}
