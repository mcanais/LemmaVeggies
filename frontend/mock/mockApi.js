// Dev-only mock of the LemmaVeggies API, built from the challenge dataset.
// Stock levels and compliance are random (but deterministic per area) since
// there is no model output yet.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const DATASET_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../dataset')
const LEVELS = ['empty', 'half', 'full']

function seededRandom(seed) {
  let h = 2166136261
  for (const c of String(seed)) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507)
    h = Math.imul(h ^ (h >>> 13), 3266489909)
    return ((h ^= h >>> 16) >>> 0) / 4294967296
  }
}

function loadData() {
  const planogram = JSON.parse(fs.readFileSync(path.join(DATASET_DIR, 'planogram.json'), 'utf8'))
  const cameras = planogram['Frutas e Legumes'].cameras
  const imagesDir = path.join(DATASET_DIR, 'train_test')

  const imagesByCamera = {}
  const areas = {}
  for (const [cameraId, camera] of Object.entries(cameras)) {
    const dir = path.join(imagesDir, cameraId)
    const timestamps = fs.existsSync(dir)
      ? fs.readdirSync(dir).filter((f) => f.endsWith('.jpg')).map((f) => Number(f.slice(0, -4))).sort((a, b) => a - b)
      : []
    imagesByCamera[cameraId] = timestamps

    for (const p of camera.products) {
      const rand = seededRandom(p.area_id)
      let level = Math.floor(rand() * 3)
      const history = timestamps.map((timestamp) => {
        // Random walk that mostly drains stock, with occasional restocks.
        const r = rand()
        if (r < 0.25) level = 2
        else if (r < 0.55) level = Math.max(0, level - 1)
        return { timestamp, compliant: rand() > 0.08, stockLevel: LEVELS[level] }
      })
      areas[p.area_id] = {
        id: p.area_id,
        cameraId,
        productId: p.product_id,
        productName: p.product_name,
        imageCoordinates: p.image_coordinates,
        history,
      }
    }
  }
  return { cameras, imagesByCamera, areas, imagesDir }
}

function inRange(timestamp, query) {
  const from = query.get('from')
  const to = query.get('to')
  return (!from || timestamp >= Number(from)) && (!to || timestamp <= Number(to))
}

export default function mockApi() {
  return {
    name: 'lemmaveggies-mock-api',
    apply: 'serve',
    configureServer(server) {
      const { cameras, imagesByCamera, areas, imagesDir } = loadData()

      const json = (res, body, status = 200) => {
        res.statusCode = status
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify(body))
      }
      const sendImage = (res, cameraId, timestamp) => {
        const file = path.join(imagesDir, cameraId, `${timestamp}.jpg`)
        if (!fs.existsSync(file)) return json(res, { error: 'Image not found' }, 404)
        res.setHeader('Content-Type', 'image/jpeg')
        fs.createReadStream(file).pipe(res)
      }

      const routes = [
        [/^\/api\/areas\/?$/, (res) =>
          json(res, Object.values(areas).map(({ id, cameraId, productName, history }) => {
            const latest = history.at(-1) ?? { compliant: true, stockLevel: 'empty' }
            return { id, cameraId, productName, compliant: latest.compliant, stockLevel: latest.stockLevel }
          }))],
        [/^\/api\/areas\/([^/]+)\/?$/, (res, query, [areaId]) => {
          const area = areas[areaId]
          if (!area) return json(res, { error: 'Area not found' }, 404)
          const { id, cameraId, productName, history } = area
          json(res, { id, cameraId, productName, history: history.filter((h) => inRange(h.timestamp, query)) })
        }],
        [/^\/api\/cameras\/?$/, (res) =>
          json(res, Object.entries(cameras).map(([id, c]) => ({ id, areas: c.products.map((p) => p.area_id) })))],
        [/^\/api\/cameras\/([^/]+)\/?$/, (res, query, [cameraId]) => {
          if (!cameras[cameraId]) return json(res, { error: 'Camera not found' }, 404)
          json(res, {
            id: cameraId,
            areas: cameras[cameraId].products.map((p) => ({
              id: p.area_id,
              productName: p.product_name,
              imageCoordinates: p.image_coordinates,
            })),
          })
        }],
        [/^\/api\/cameras\/([^/]+)\/images\/latest\/?$/, (res, query, [cameraId]) => {
          const latest = imagesByCamera[cameraId]?.at(-1)
          if (!latest) return json(res, { error: 'No images' }, 404)
          sendImage(res, cameraId, latest)
        }],
        [/^\/api\/cameras\/([^/]+)\/images\/?$/, (res, query, [cameraId]) => {
          if (!imagesByCamera[cameraId]) return json(res, { error: 'Camera not found' }, 404)
          json(res, imagesByCamera[cameraId].filter((t) => inRange(t, query)).map((t) => `${cameraId}_${t}`))
        }],
        [/^\/api\/images\/(\d+)_(\d+)\/?$/, (res, query, [cameraId, timestamp]) =>
          sendImage(res, cameraId, timestamp)],
      ]

      server.middlewares.use((req, res, next) => {
        if (req.method !== 'GET' || !req.url.startsWith('/api/')) return next()
        const url = new URL(req.url, 'http://localhost')
        for (const [pattern, handler] of routes) {
          const match = url.pathname.match(pattern)
          if (match) return handler(res, url.searchParams, match.slice(1).map(decodeURIComponent))
        }
        json(res, { error: 'Not found' }, 404)
      })
    },
  }
}
