# Compliance benchmark

Which model best decides, per planogram area, "is the planned product here?" (`planogram_compliant`), and how fast is it?

**Result:** DINOv2 with a small product classifier, trained on the team's labels plus the Grocery Store Dataset at apple/pear *variety* level, scores best:
- 936 of 967 labelled areas correct;
- 874 points, against 667 for "always compliant" and 796 for the team's current method;
- **~0.9 s per camera image on CPU**, ~5 s to train.

## What was compared

**Engines.** Both are frozen pretrained models, CPU only, and neither is fine-tuned. Each turns a crop into a list of numbers (an embedding).

| Engine | Model | Notes |
|---|---|---|
| `clip` | CLIP ViT-B/32, LAION-2B (open_clip) | image + text, so it can also match written product names |
| `dinov2` | DINOv2 ViT-S/14 (timm, same weights as the team's `torch.hub` `dinov2_vits14`), 224 px | image only |

**Methods.**

| Method | What it does |
|---|---|
| `always` | always "compliant" (baseline) |
| `area_cosine_0.65` | **the team's current method** (`train.py`/`classify.py`). Compares the crop with the average look of its own area's labelled-compliant crops (cosine similarity), and flags it below 0.65. |
| `area_cosine` | the same, with the cut-off tuned on the training labels |
| `classifier` | a logistic regression that answers "which product is this?". It learns from labelled crops: compliant crops show their planogram product, and empty crops are an extra "empty" class. It flags an area when P(expected product) + P(empty) is below a threshold. If it has never seen the expected product, it says compliant. |
| `text` | (CLIP only) the no-label method from `cadete_testing`. It matches the crop against the written product category, and the labels only tune how many areas to flag. |
| `gsd_only` | the classifier trained only on the [Grocery Store Dataset](https://github.com/marcusklasson/GroceryStoreDataset) (MIT): 3,676 produce photos in 50 classes, mapped to our categories in `embed_gsd.py` |
| `classifier+gsd` | the classifier trained on the team's labels **and** the Grocery Store photos |

**Granularity.**
- `category` judges at generic product level (red apples, bananas…).
- `variety` also distinguishes apple and pear varieties (gala, pink lady, fuji, golden, granny smith, conference…). If the model has fewer than 5 examples of the expected variety, it falls back to category level.

**Translation.** `lemma/categories.py` maps all 94 Portuguese product names to a generic English category, plus a variety for apples and pears. For example, `MELANCIA PRETA POUCAS SEMENTES INT KG` → watermelons; seeds and calibre are ignored. This mapping is done once, not per image.

**Labels.** `labels/human.jsonl` has 1,165 rows. After keeping the latest label per area and dropping the 39 `unsure` rows, **967 areas are usable: 91 images on all 14 cameras, 100 non-compliant.**

**Scoring.**
- **Points:** the challenge's identification score, +1 per correct area and −2 per wrong one.
- **Correct:** number of areas right.
- **Caught:** non-compliant areas flagged.
- **False alarms:** compliant areas flagged.
- **Images all correct:** images where every area is right.
- **Product id:** compliant, non-empty crops whose predicted product equals the planned one.

**Testing.** Every area is predicted by a model that never saw its label.
- `images`: folds grouped by photo. These are new photos from cameras the model has seen, which is what the official validation set is (same 14 cameras, same day). **This is the number that matters for the challenge.**
- `cameras`: leave-one-camera-out. Cameras never seen, like a new store layout.

## Results

### Phase 1: team labels only (`results/phase1.md`)

New photos, seen cameras (5 folds, threshold tuned):

| Engine | Method | Points | Correct | Caught | False alarms | Images all correct |
|---|---|---|---|---|---|---|
| — | always compliant | 667 | 867/967 | 0/100 | 0 | 54/91 |
| clip | area_cosine_0.65 (team) | 769 | 901 | 46 | 12 | 55 |
| clip | area_cosine (tuned) | 778 | 904 | 65 | 28 | 53 |
| clip | text (no labels) | 787 | 907 | 40 | 0 | 66 |
| clip | classifier | 811 | 915 | 52 | 4 | 64 |
| dinov2 | area_cosine_0.65 (team) | 796 | 910 | 79 | 36 | 53 |
| dinov2 | area_cosine (tuned) | 817 | 917 | 79 | 29 | 60 |
| **dinov2** | **classifier** | **835** | **923** | 60 | 4 | 65 |

Unseen cameras:

| Engine | Method | Points | Correct |
|---|---|---|---|
| — | always compliant | 667 | 867 |
| both | area_cosine (team) | 667 | 867 |
| clip | classifier | 679 | 871 |
| dinov2 | classifier | 721 | 885 |
| clip | text (no labels) | **748** | **894** |

### Phase 2: + Grocery Store Dataset, category level (`results/phase2.md`)

New photos, seen cameras:

| Engine | Method | Points | Correct | Caught | False alarms |
|---|---|---|---|---|---|
| clip | gsd_only | 445 | 793 | 27 | 101 |
| clip | classifier+gsd | 805 | 913 | 47 | **1** |
| dinov2 | gsd_only | 541 | 825 | 23 | 65 |
| dinov2 | classifier+gsd | 829 | 921 | 59 | 5 |

Unseen cameras: clip classifier+gsd 472 and dinov2 classifier+gsd 601. Both are worse than without the dataset.

### Phase 2: + Grocery Store Dataset, variety level

The full run was stopped early to save time. Lines that completed (`results/bench_full_runs.log`, 5 folds, threshold tuned, no fallback for rare varieties):

| Engine | Test | Method | Points | Correct | Caught | False alarms |
|---|---|---|---|---|---|---|
| clip | new photos | classifier | 799 | 911 | 50 | 6 |
| clip | new photos | classifier+gsd | 847 | 927 | 61 | 1 |
| dinov2 | new photos | classifier | 823 | 919 | 58 | 6 |
| **dinov2** | **new photos** | **classifier+gsd** | **874** | **936** | **72** | **3** |
| clip | unseen cameras | classifier+gsd | 544 | 826 | 34 | 75 |

**Quick confirmation run** (`results/quick_dinov2_variety.md`). This is the final setup: DINOv2, variety level, 3 folds, fixed threshold 0.1, and the rare-variety fallback. It took 53 s in total.

| Method | Points | Correct | Caught | False alarms | Images all correct | Product id |
|---|---|---|---|---|---|---|
| always compliant | 667 | 867/967 | 0/100 | 0 | 54/91 | |
| **dinov2 classifier+gsd (variety)** | **874** | **936/967** | **71/100** | **2** | **74/91** | 801/817 |

### Time (CPU, laptop, 22 threads)

Per camera image = read the image, crop every area, embed the crops, classify.

| Engine | ms / camera image | ms / area | Training |
|---|---|---|---|
| clip | ~690 | ~64 | 1–4 s |
| dinov2 | ~860–910 | ~80–84 | 1.5–5.5 s |

Embedding the 3,676 Grocery Store photos once took 57 ms per photo (CLIP) and 84 ms per photo (DINOv2), i.e. ~4–5 min, and it is cached in `cache/`.

## What the review of every verdict showed

`review_results.py` checks every labelled area and every flag on unlabelled areas. The reports and image grids are in `results/*_review.md` and `results/*.jpg`.

**Best setup (quick run), per camera:** perfect on 6215, 6371, 6385, 6386, 6462, 6468, 6491, 6591, 6594 and 6781. The errors are in 6373, 6376, 6383 and 6443.

**What the dataset fixed:** the Gala area 6373_1 holds Pink Lady apples all day. Phase 1 missed all 13 photos (it only knew "red apples"). At variety level with the Grocery Store photos, it catches **12 of 13**: it sees "pink lady" where "gala" is planned.

**The 29 remaining misses:**

| Areas | Count | Why |
|---|---|---|
| 6376_3/4/5 (kiwi packs) | 13 | crates partly filled with other netted fruit. The model calls them "empty", which counts as compliant. |
| 6383_1–9 | 9 | a shelf covered by a cloth (early morning), labelled non-compliant. The labelling guide only says *empty* = compliant, so **the team should agree whether "covered" is compliant**. |
| 6373_2 (packed red apples) | 3 | mixed bags of apples |
| 6443_3 | 3 | area mostly outside the image |
| 6373_1 | 1 | one Gala/Pink Lady photo |

**The 2 false alarms:**
- 6373_5: mixed bags.
- 6383_7: the chayote area clearly shows **eggplants** but is labelled compliant, so it's **probably a label error**.

**Flags on unlabelled areas** (final model, 32):
- **Cameras 6468 and 6594:** these flags only appear in the first 3 photos of the day, before restocking. Mangoes really are in the passion-fruit crate, and orange fruit and avocados are in the banana crates. Several of these look correct. Netted onions read as loose onions are likely false alarms.
- **Cosmic Crisp areas 6373_7/6373_9:** before the rare-variety fallback, the final model flagged all their photos (59 flags in total). Their labels are all `unsure`, so the model had almost no Cosmic Crisp examples. **The fallback fixed this** (59 → 32 flags) without changing the score.

## Conclusions

1. **The team's area-cosine method helps but over-flags.** It scores 796 points (DINOv2) with 36 false alarms, and catches nothing on unseen cameras. Tuning its cut-off gives 817.
2. **A product classifier on the same DINOv2 embeddings is better:** 835 points, 4 false alarms. DINOv2 beats CLIP for this.
3. **The Grocery Store Dataset alone is not enough.** Its phone close-ups look too different from ceiling-camera crops (445–571 points). **Combined with the team's labels it helps, mainly at variety level** (874 points), because its Gala/Pink Lady photos teach the apple varieties.
4. **On unseen cameras, nothing trained on labels generalises well.** The no-label CLIP text method is best there (748). For this challenge that matters less, because validation uses the same cameras.
5. **Speed is fine:** under 1 s per camera image on CPU, for 7–16 areas.

**Recommended:** `dinov2` + `classifier+gsd` at `variety` level, threshold 0.1, rare-variety fallback.

**Next steps:**
- Agree on the "covered shelf" rule and fix label 6383_7.
- Label the Cosmic Crisp areas (currently all `unsure`).
- Treat netted/loose versions of the same product as the same thing.
- Possibly add an "other product in the crate" check, so partly filled crates aren't read as empty.

## How to reproduce

```sh
cd backend && nix-shell                      # NixOS; elsewhere: python -m venv .venv && pip install -r requirements.txt
source .venv/bin/activate
python embed_areas.py --engine dinov2        # crops every area of every image in memory -> cache/ (~3 min)
python embed_areas.py --engine clip
git clone --depth 1 https://github.com/marcusklasson/GroceryStoreDataset external/GroceryStoreDataset
python embed_gsd.py --engine dinov2          # ~5 min
python embed_gsd.py --engine clip

python bench_compliance.py                    # phase 1 (~10 min; both engines, both tests)
python bench_compliance.py --gsd              # phase 2 (~25 min)
# fast: the recommended setup only (~1 min)
python bench_compliance.py --engines dinov2 --gsd --granularity variety --schemes images \
    --folds 3 --threshold 0.1 --methods classifier+gsd --tag quick_dinov2_variety
python review_results.py --tag quick_dinov2_variety --column dinov2:classifier+gsd:images
```

Useful options of `bench_compliance.py`:
- `--engines`, `--schemes images cameras`, `--folds`, `--methods`;
- `--threshold` (fixed, skips tuning: much faster);
- `--granularity category|variety`, `--labels`.

Outputs in `results/`:
- `<tag>.md`: tables.
- `<tag>_predictions.csv`: every area of every image, with each method's verdict, score and predicted product, both held-out and final model.
- `bench.log`: progress.

## Files

| File | Purpose |
|---|---|
| `embed_areas.py` | embeds every area of every image per engine, from in-memory crops (no JPEG re-compression) |
| `embed_gsd.py` | maps the Grocery Store classes to ours and embeds the photos |
| `bench_compliance.py` | the benchmark |
| `review_results.py` | per-camera review and image grids of every error/flag |
| `lemma/embed.py` | the two engines + embedding cache |
| `lemma/categories.py` | product name → category / variety (translation table) |
| `lemma/labels.py` | reads `labels/human.jsonl` (latest label wins, `unsure` skipped) |
| `lemma/compliance.py` | challenge points + CLIP text features (from `cadete_testing`) |
