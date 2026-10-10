import { request, rangeParams } from './client.js'

// [{ id, cameraId, productName, compliant, stockLevel }]
export function getAreas() {
  return request('/areas')
}

// { id, cameraId, productName, history: [{ timestamp, compliant, stockLevel }] }
export function getArea(areaId, range) {
  return request(`/areas/${encodeURIComponent(areaId)}`, rangeParams(range))
}
