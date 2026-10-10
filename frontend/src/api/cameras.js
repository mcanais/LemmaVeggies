import { request, rangeParams, buildUrl } from './client.js'

// [{ id, areas: [areaId] }]
export function getCameras() {
  return request('/cameras')
}

// { id, areas: [{ id, productName, imageCoordinates }] }
export function getCamera(cameraId) {
  return request(`/cameras/${encodeURIComponent(cameraId)}`)
}

// [imageId]
export function getCameraImages(cameraId, range) {
  return request(`/cameras/${encodeURIComponent(cameraId)}/images`, rangeParams(range))
}

// The endpoint returns the image itself, so hand back a URL for <img src>.
// The timestamp avoids the browser serving a stale cached "latest" image.
export function getLatestImageUrl(cameraId) {
  return buildUrl(`/cameras/${encodeURIComponent(cameraId)}/images/latest`, { t: Date.now() })
}
