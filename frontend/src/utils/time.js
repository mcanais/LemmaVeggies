// Image ids look like "<cameraId>_<unix seconds>". Returns null if the id doesn't carry a timestamp.
export function imageTimestamp(imageId) {
  const ts = Number(String(imageId).split('_').at(-1))
  return Number.isFinite(ts) && ts > 1e9 ? ts : null
}

export function formatTime(seconds) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
