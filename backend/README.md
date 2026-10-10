# LemmaVeggies backend

Step 1 of the pipeline: cut each planogram area (basket) out of the camera images, so a model can later classify per area which product is there and how much stock it has.

## What it does

Each camera image (`dataset/train_test/<camera_id>/<timestamp>.jpg`, 1280×720) shows several baskets. `dataset/planogram.json` gives the four corners of each area per camera (152 areas over 14 cameras). For every image and every area of its camera, `crop_areas.py`:

1. Takes the axis-aligned bounding box of the area's four-sided polygon, clipped to the image. Areas with negative coordinates (cameras 6383, 6386) are partly off-frame and simply stop at the image edge.
2. Blacks out the pixels inside the box but outside the polygon, so neighbouring baskets don't leak in. `--no-mask` turns this off.
3. Saves the crop with its **original pixels and perspective**: no warping and no resizing. Resizing to the model's input size belongs in the model's preprocessing.

There is an alternative `--mode warp` that perspective-rectifies each area into an upright rectangle. It is not the default, because the distortion could affect the model.

On the current dataset this gives 181 images → 1,962 crops.

## Layout

```
backend/
├── crop_areas.py        # CLI: crop all images
├── lemma/
│   ├── planogram.py     # load_areas(): planogram.json -> {camera_id: [Area]}
│   └── crop.py          # bbox_area(), warp_area(), draw_areas()
├── requirements.txt     # numpy, opencv-python-headless
├── shell.nix            # NixOS dev shell (native libs for pip wheels)
└── crops/               # generated output (git-ignored)
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
├── <camera_id>/<area_id>/<timestamp>.jpg   # one crop per area per image
├── index.csv                               # one row per crop
└── _overlays/<camera_id>.jpg               # with --overlays (mid-day frame)
```

Crops are grouped by area, so all frames of the same basket across the day sit together.

`index.csv` columns: `camera_id, image, area_id, product_id, product_name, crop_path` (`crop_path` is relative to the output folder). The next step can go through this file to classify each crop and write the submission, which has the same structure as `annotations.json`: `{camera_id: {image: {area_id: {planogram_compliant, stock_level, stock_value}}}}`.

## Notes for the model step

- Early-morning frames can show shelves covered (e.g. camera 6383), so they don't reflect stock.
- Products move during the day. For example, area 6215_3 (planned: oranges) holds bananas later on. That is the non-compliance case to detect.
- Scoring penalises overestimating stock (−3) more than underestimating it (−2), so stock predictions should lean towards the lower level when unsure.
