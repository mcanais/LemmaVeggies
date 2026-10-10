// Made-up top-down layout of the store, in floor-plan units (the map's viewBox).
// Prototype only. Every area tile has the same size; a camera's gondola is
// sized from its number of areas, TILE.rows tiles deep.

export const TILE = { size: 44, gap: 4, rows: 2 }
export const BLOCK = { pad: 8, header: 20 }

const MARGIN = 40 // floor edge → first gondola
const BLOCK_GAP = 24 // between gondolas in the same row
const ENTRANCE_WIDTH = 160
const ENTRANCE_DEPTH = 20

// Rows of gondolas from the back of the store to the front. `gapAfter` is the
// space below the row: an aisle, or a small gap for back-to-back islands.
// 'entrance' reserves the store entrance inside the front wall.
const ROWS = [
  { cameras: ['6215', '6371', '6373', '6376'], gapAfter: 70 },
  { cameras: ['6383', '6385', '6386'], gapAfter: 16 },
  { cameras: ['6443', '6462', '6468'], gapAfter: 70 },
  { cameras: ['6491', '6591', 'entrance', '6594', '6781'], gapAfter: MARGIN },
]

export function blockSize(areaCount) {
  const cols = Math.max(1, Math.ceil(areaCount / TILE.rows))
  return {
    cols,
    width: BLOCK.pad * 2 + cols * TILE.size + (cols - 1) * TILE.gap,
    height: BLOCK.header + TILE.rows * TILE.size + (TILE.rows - 1) * TILE.gap + BLOCK.pad,
  }
}

// { [cameraId]: areaCount } → { width, height, blocks: [{ cameraId, box, cols }], entrance }
export function computeLayout(countsByCamera) {
  const placed = new Set(ROWS.flatMap((r) => r.cameras))
  // Cameras the layout doesn't know about yet get an extra row at the front.
  const extra = Object.keys(countsByCamera).filter((id) => !placed.has(id))
  const rows = extra.length ? [...ROWS, { cameras: extra, gapAfter: MARGIN }] : ROWS

  const itemWidth = (id) => (id === 'entrance' ? ENTRANCE_WIDTH : blockSize(countsByCamera[id] ?? 0).width)
  const rowItems = rows.map((r) => r.cameras.filter((id) => id === 'entrance' || id in countsByCamera))
  const rowWidths = rowItems.map((items) => items.reduce((sum, id) => sum + itemWidth(id), 0) + BLOCK_GAP * Math.max(0, items.length - 1))
  const width = Math.max(...rowWidths) + MARGIN * 2
  const rowHeight = blockSize(0).height

  const blocks = []
  let entrance = null
  let y = MARGIN
  rowItems.forEach((items, i) => {
    let x = (width - rowWidths[i]) / 2 // centre each row
    for (const id of items) {
      if (id === 'entrance') {
        entrance = { x, width: ENTRANCE_WIDTH }
      } else {
        const { cols, width: w, height: h } = blockSize(countsByCamera[id])
        blocks.push({ cameraId: id, cols, box: { x, y, width: w, height: h } })
      }
      x += itemWidth(id) + BLOCK_GAP
    }
    y += rowHeight + rows[i].gapAfter
  })

  const height = y
  return {
    width,
    height,
    blocks,
    entrance: entrance && { ...entrance, y: height - ENTRANCE_DEPTH, height: ENTRANCE_DEPTH },
  }
}
