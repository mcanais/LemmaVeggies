# LemmaVeggies backend

Per planogram area (basket) in each camera image, decide whether it holds the product the planogram expects.

1. **Crop** each area out of the camera images (`crop_areas.py`).
2. **Compliance model**: is the right product in the area? (`embed_crops.py`, `train_compliance.py`, `predict_compliance.py`).
3. **Variety model**: which variety (Fuji vs Gala, banana kinds...)? (`train_variety.py`).

Stock level is a separate model (not here yet).

## What it does

Each camera image (`dataset/train_test/<camera_id>/<timestamp>.jpg`, 1280×720) shows several baskets. `dataset/planogram.json` gives the four corners of each area per camera (152 areas over 14 cameras). For every image and every area of its camera, `crop_areas.py`:

1. Takes the axis-aligned bounding box of the area's four-sided polygon, clipped to the image. Areas with negative coordinates (cameras 6383, 6386) are partly off-frame and simply stop at the image edge.
2. Blacks out the pixels inside the box but outside the polygon, so neighbouring baskets don't leak in. `--no-mask` turns this off.
3. Saves the crop as PNG with its **original pixels and perspective**: no warping, no resizing and no JPEG re-compression. Re-compression would shift the model's embeddings compared with cropping in memory at prediction time. Resizing to the model's input size belongs in the model's preprocessing.

There is an alternative `--mode warp` that perspective-rectifies each area into an upright rectangle. It is not the default, because the distortion could affect the model.

On the current dataset this gives 181 images → 1,962 crops.

## Layout

```
backend/
├── crop_areas.py          # CLI: crop all images
├── embed_crops.py         # CLI: CLIP embeddings of all crops (cached, incremental)
├── train_compliance.py    # CLI: train + evaluate the compliance model
├── train_variety.py       # CLI: train + evaluate the variety model
├── predict_compliance.py  # CLI: camera images -> compliance JSON (+ variety)
├── human.jsonl            # the team's labels
├── lemma/
│   ├── planogram.py       # load_areas(): planogram.json -> {camera_id: [Area]}
│   ├── crop.py            # bbox_area(), warp_area(), draw_areas(), inner_tiles()
│   ├── categories.py      # product name -> generic category, variety family, CLIP prompts
│   ├── embed.py           # CLIP model (frozen, CPU) + embedding cache
│   ├── labels.py          # read labels (.json annotations format or .jsonl)
│   ├── compliance.py      # features, supervised + unsupervised models, scoring
│   └── variety.py         # per-family variety classifiers
├── requirements.txt
├── shell.nix              # NixOS dev shell (native libs for pip wheels)
├── crops/                 # generated (git-ignored)
├── models/                # trained model (git-ignored)
└── predictions/           # prediction JSON (git-ignored)
```

`Area` holds `camera_id`, `area_id`, `product_id`, `product_name` and `quad`, a (4, 2) float32 array ordered top-left, top-right, bottom-right, bottom-left.

## Setup

On NixOS, pip wheels (numpy, opencv) need `libstdc++` and friends on `LD_LIBRARY_PATH`, and `shell.nix` provides them. The first `nix-shell` also creates `.venv` and installs `requirements.txt`.

```sh
cd backend
nix-shell                     # enter the dev shell
source .venv/bin/activate
```

Or run a single command without entering the shell:

```sh
nix-shell --run '.venv/bin/python crop_areas.py --overlays'
```

On other Linux/macOS systems, skip `shell.nix`:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Usage

```sh
python crop_areas.py [--images DIR] [--planogram FILE] [--out DIR]
                     [--mode bbox|warp] [--no-mask] [--size N] [--overlays]
```

| Option | Default | Meaning |
|---|---|---|
| `--images` | `../dataset/train_test` | One subfolder per camera id with `*.jpg` images |
| `--planogram` | `../dataset/planogram.json` | Planogram file |
| `--out` | `crops/` | Output folder |
| `--mode` | `bbox` | `bbox`: original pixels, no distortion. `warp`: perspective-rectified |
| `--no-mask` | off | `bbox` mode: keep the pixels outside the area polygon |
| `--size N` | — | `warp` mode only: resize crops to N×N |
| `--overlays` | off | Save one image per camera with the area polygons and ids drawn |

Run it on the validation images by pointing `--images` at their folder (same `<camera_id>/<timestamp>.jpg` layout).

## Output

```
crops/
├── <camera_id>/<area_id>/<timestamp>.png   # one crop per area per image
├── index.csv                               # one row per crop
└── _overlays/<camera_id>.jpg               # with --overlays (mid-day frame)
```

Crops are grouped by area, so all frames of the same basket across the day sit together.

`index.csv` columns: `camera_id, image, area_id, product_id, product_name, crop_path` (`crop_path` is relative to the output folder).

## How training works (in short)

Labels are only used at **training time**. Training writes small model files to `models/`. Prediction only reads those files, so new images need no labels. Nothing updates on its own: when the team labels more, re-run training.

```sh
cd backend && nix-shell          # then: source .venv/bin/activate
python crop_areas.py             # 1. crops (only needed for new images)
python embed_crops.py            # 2. CLIP embeddings, cached (only new crops are computed)
python train_compliance.py --labels human.jsonl   # 3. -> models/compliance.joblib  (~1 min)
python train_variety.py   --labels human.jsonl    # 4. -> models/variety.joblib     (~1 min, needs 3.)
python predict_compliance.py --images <dir>       # 5. -> predictions/compliance.json
```

## Compliance model

### Idea

No vision network is trained. A free pretrained image–text model, **CLIP ViT-B/32** (open_clip, LAION weights), turns each crop into 512 numbers (an *embedding*) that describe what it shows. Small, fast models on top of these numbers decide "does this crop show the product the planogram expects?".

Each product name is first mapped to a generic category (`lemma/categories.py`, e.g. `MAÇÃ GALA CNT CAL 70/80 KG IMP` → `red apples`, `BATATA BRANCA CNT EMB. 3KG` → `potatoes (packaged)`). Run `python -m lemma.categories` to see the full mapping. A new product name with no rule fails loudly; add a rule to `RULES`.

Each crop is compared with its **expected** category:

| Feature | Meaning |
|---|---|
| `text_sim` | CLIP similarity to text prompts for the expected category ("a photo of bananas in a supermarket display") |
| `margin_other` | `text_sim` minus the best-matching *other* category |
| `margin_empty` | `text_sim` minus the best "empty basket / covered shelf" prompt |
| `best_vs_empty` | best match over *all* categories minus the best empty/covered prompt (< 0: no product at all) |
| `proto_sim` | similarity to the expected category's visual prototype: the mean of labelled-compliant crops of that category (≥3), otherwise the median of all crops whose area expects it |
| area consistency | similarity to that area's usual look over the day |

`train_compliance.py` compares two kinds of model and **keeps the one that scores best**:

- **Unsupervised**: flags the crops that look least like their expected product (`margin_other` + `proto_sim`). The labels only tune *how many* to flag (2–15%). A crop that looks like no product at all (empty or covered) is kept compliant: it isn't the wrong product, and emptiness is the stock model's job. Without labels it flags 5%.
- **Supervised**: logistic regression on all features, trained on the labels, optionally with the area nudge.

**Area consistency is deliberately the weakest signal.** Stores reorganise and mix products in a basket, so "looks unlike usual" is weak evidence. It can only nudge the supervised model's probability by at most ±`--area-max-shift` (default 0.05).

**Decision threshold.** A correct answer scores +1 and a wrong one −2, so the supervised model flags an area only when P(non-compliant) > 2/3 (`--threshold`).

**Evaluation** is leave-one-camera-out. Everything tuned or trained sees the other cameras' labels only, then predicts the held-out camera. Scores are in challenge points, compared with "always compliant".

### Current results (`human.jsonl`: 355 usable labels, 3 cameras, 44 non-compliant)

| Model | Points | Caught | False alarms |
|---|---|---|---|
| always compliant | 223 | 0/44 | 0 |
| **unsupervised, tuned** (kept) | **289** | 24/44 | 2 |
| supervised | 214 | 0/44 | 3 |

- **What it catches:** bananas in the orange crates 6215_7 and 6215_9, which are wrong all day.
- **What it misses, mostly:** 6373_1 (13 labels). A Gala basket holding another red apple is a *variety* mix-up, and the category model can't see it.
- **Why the supervised model doesn't help yet:** with labels from only 3 cameras, each held-out test learns from a different kind of mistake than the one it's tested on. Labels from more cameras, with wrong-product examples, should change that. Re-run training and it will switch automatically if the supervised model starts winning.

**Cost:** ~0.65 s per camera image on a laptop CPU (crop + embed + classify), with no GPU and no API calls. `predict_compliance.py` prints it.

## Variety model

Within a family (apples, bananas, pears, melons, watermelons, tomatoes, peaches, mangoes, papayas), it predicts which variety is in a basket.

- **Input:** only the **centre 70% of the crop, cut into 2×2 tiles** (`inner_tiles`), so it looks at the fruit rather than the crate or the price label.
- **Model:** one logistic regression per family. The tiles vote.
- **Training data is free:** a crop labelled compliant, or unlabelled and not flagged by the compliance model, shows its planogram product.
- **Packaged products are left out**, because they look like packaging.

**Main risk:** every variety sits in one or two fixed baskets, often in its own crate. A model could learn "this crate = Pink Lady". So `train_variety.py` tests **leave-one-area-out**: it predicts each basket with a model that has never seen it. Current results:

- **Good on unseen baskets:** Fuji 100%, Cosmic Crisp 87%, Packams pear, beefsteak/round tomatoes and Melão verde 100%, Banana Cat I 100%.
- **Poor:** Golden (50%, confused with Granny Smith), mini watermelon, Manga CNT, Paraguayo peach, Banana Pão.
- **Not testable:** Gala, Pink Lady, Granny Smith, Reineta and others have one basket only, so they can't be tested on an unseen basket.

**Does it help compliance?** `train_variety.py` adds variety mismatches to the compliance flags at several thresholds and checks the points on the labels. Right now it doesn't help: it doesn't catch 6373_1 and only adds false alarms. So it is **switched off for compliance** and saved with `threshold = inf`.

- **Why 6373_1 is missed:** the only loose Gala basket is labelled wrong all day, so the model has never seen a correct Gala basket to compare against. It spreads its guess over Fuji, Cosmic Crisp and Pink Lady (~0.35 each).
- **What would fix it:** reference images of real Gala apples, either from other store images or from the web.

`predict_compliance.py --with-variety` adds `predicted_variety` and `p_variety` per area, for the app. These fields are not part of the submission. This costs ~1.5 s per image instead of 0.65 s, so tiles are only computed when asked for or when the variety check is on.

## Labelling

Two formats are accepted, and several files can be passed (later ones win):

- **`.jsonl` from the labelling tool**, one area per line: `camera, image, area_id, planogram_compliant, stock_level, stock_value, unsure, time`. If an area was labelled more than once, the latest `time` wins (corrections). `unsure` rows are skipped unless `--keep-unsure` is passed.
- **The challenge's `annotations.json` format**: `{camera: {image: {area_id: {planogram_compliant, ...}}}}`.

Label every area of an image, not only the wrong ones. Most useful next: wrong-product examples on **more cameras** (so far only 6215, 6371, 6373 are labelled).

## Prediction output

`predict_compliance.py` options:
- `--images`: default `../dataset/train_test`, one subfolder per camera.
- `--model`, `--variety-model`, `--out`: default `predictions/compliance.json`.
- `--with-proba`: adds `p_compliant` per area.
- `--with-variety`: adds the predicted variety.

The output has the annotations structure with `planogram_compliant`; merge in the stock model's fields before submitting.

## Adding more images

Put them in a folder with one subfolder per camera id (camera ids must exist in the planogram), then:

```sh
python crop_areas.py --images <new_dir>        # added to crops/ and merged into index.csv
python embed_crops.py                          # embeds only the new crops
python train_compliance.py --labels human.jsonl new_labels.jsonl
python train_variety.py   --labels human.jsonl new_labels.jsonl
```

Embeddings are cached, so only new crops are computed, and retraining takes about a minute. The CLIP model never changes, so nothing heavy is retrained.

## Notes for the stock model

- Early-morning frames can show shelves covered (e.g. camera 6383), so they don't reflect stock.
- Scoring penalises overestimating stock (−3) more than underestimating it (−2), so stock predictions should lean towards the lower level when unsure.
