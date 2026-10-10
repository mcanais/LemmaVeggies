import { buildUrl } from './client.js'

// The endpoint returns the image itself, so hand back a URL for <img src>.
export function getImageUrl(imageId) {
  return buildUrl(`/images/${encodeURIComponent(imageId)}`)
}
