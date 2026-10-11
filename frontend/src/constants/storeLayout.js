// Made-up top-down layout of the store, in floor-plan units (the map's viewBox).
// Prototype only. Every area tile has the same size; a camera's gondola is
// TILE.cols tiles wide and as long as its number of areas needs.

export const TILE = { size: 44, gap: 4, cols: 3 }
export const BLOCK = { pad: 8, header: 20 }

const MARGIN = 40 // floor edge → first gondola
const BLOCK_GAP = 24 // between gondolas in the same column
const ENTRANCE_DEPTH = 80 // room in front of the front wall for the entrance marker

// Columns of gondolas from left to right. `gapAfter` is the space to the right
// of the column: an aisle, or a small gap for back-to-back islands.
// The entrance is in the middle of the front (bottom) wall.
const COLUMNS = [
  { cameras: ['6215', '6371', '6373', '6376'], gapAfter: 80 },
  { cameras: ['6383', '6385', '6386'], gapAfter: 16 },
  { cameras: ['6443', '6462', '6468'], gapAfter: 80 },
  { cameras: ['6491', '6591', '6594', '6781'], gapAfter: MARGIN },
]

export function blockSize(areaCount) {
  const rows = Math.max(1, Math.ceil(areaCount / TILE.cols))
  return {
    rows,
    width: BLOCK.pad * 2 + TILE.cols * TILE.size + (TILE.cols - 1) * TILE.gap,
    height: BLOCK.header + rows * TILE.size + (rows - 1) * TILE.gap + BLOCK.pad,
  }
}

// { [cameraId]: areaCount } → { width, height, blocks: [{ cameraId, box }], entrance: { x, y } }
export function computeLayout(countsByCamera) {
  const placed = new Set(COLUMNS.flatMap((c) => c.cameras))
  // Cameras the layout doesn't know about yet get an extra column on the right.
  const extra = Object.keys(countsByCamera).filter((id) => !placed.has(id))
  const columns = extra.length ? [...COLUMNS, { cameras: extra, gapAfter: MARGIN }] : COLUMNS

  const colItems = columns.map((c) => c.cameras.filter((id) => id in countsByCamera))
  const colHeights = colItems.map(
    (items) => items.reduce((sum, id) => sum + blockSize(countsByCamera[id]).height, 0) + BLOCK_GAP * Math.max(0, items.length - 1),
  )
  const colWidth = blockSize(0).width

  const blocks = []
  let x = MARGIN
  colItems.forEach((items, i) => {
    let y = MARGIN // columns start at the back wall
    for (const id of items) {
      const { width: w, height: h } = blockSize(countsByCamera[id])
      blocks.push({ cameraId: id, box: { x, y, width: w, height: h } })
      y += h + BLOCK_GAP
    }
    x += colWidth + columns[i].gapAfter
  })

  const width = x
  const height = MARGIN + Math.max(0, ...colHeights) + ENTRANCE_DEPTH
  return { width, height, blocks, entrance: { x: width / 2, y: height } }
}
