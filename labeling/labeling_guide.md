# Labelling guide

Rules for labelling. Edit them as the team agrees on edge cases.

## Stock level (per planogram area)

Judge how much of the area's display space (crate, bin, rail, shelf section) is covered
by product. Count only the inside of the area outline.

- **empty**: no product, or only a few stray units. The bottom of the crate/bin is
  visible almost everywhere (roughly under 15% covered).
- **half**: clearly partially stocked. Product covers part of the area but large patches of
  the crate/bin bottom are visible (roughly 15% to 70% covered).
- **full**: the area looks stocked. The crate/bin bottom is hidden or nearly hidden (roughly
  over 70% covered), including heaped piles.

When unsure between two levels, pick the **lower** one: the scoring penalises a level that is
too high more than one that is too low.

For packaged products (name contains a weight, e.g. `500 G`, `EMB. 3KG`), judge coverage by
packages, the same way.

## Planogram compliance

- **compliant = true**: the product shown in the area is the product the planogram expects.
- **compliant = false**: a different product occupies the area (e.g. bananas in a crate the
  planogram assigns to oranges). Also false if the same fruit is shown in a clearly different
  form than expected (e.g. bagged product where loose is expected).
- If the area holds a mix, judge by the product covering most of it.
- **Empty area**: compliant = true (nothing wrong to move). *Team assumption, to confirm with
  the organisers.*
- Varieties (e.g. Gala vs Fuji apples, peach vs nectarine): mark non-compliant only when the
  difference is clearly visible. Otherwise keep compliant, or mark the area unsure.

## Other flags

- **Occluded** (a person, trolley or object hides much of the area): still give your best
  guess, or mark it unsure if you can't tell.
- Areas partly outside the image (negative coordinates): judge only the visible part.
