# LemmaVeggies

**LemmaVeggies spots empty and misplaced produce before your customers do.**

Built for the *Fruits & Vegetables – Shelf Monitoring* challenge (`Enunciado.pdf`). From the ceiling
camera images of a store's produce section, LemmaVeggies estimates, for every planogram area, how
much stock is left (empty, half or full) and whether it holds the right product. A staff app shows
the results on a store map, per camera and over time.

## How it works

1. **Crop**: each camera image is cut into one crop per planogram area (`backend/crop_areas.py`).
2. **Describe**: a pretrained vision model (DINOv2) turns each crop into a compact description.
3. **Classify**: two small models trained on labelled crops read that description: one estimates
   the stock level, the other detects the wrong product. When unsure, the stock answer leans
   towards flagging a restock, since the scoring penalises a missed empty crate most.
4. **Show**: `backend/server.py` serves the predictions to the web app in `frontend/`.

## Repository

| Folder | Contents |
|---|---|
| `dataset/` | Camera images (`train_test/<camera>/<timestamp>.jpg`) and `planogram.json` |
| `backend/` | Cropping, training, classification and the API server |
| `backend/testing_models/` | Other approaches we tried (fine-tuned ConvNeXt, CLIP, SAM, …) |
| `frontend/` | Staff web app (Vue + Vite) |
| `labeling/` | Local dashboard used to hand-label crops |
| `labels/` | Labels: `human.jsonl` (hand-labelled) and `claude.jsonl` (used for training) |

## Running it

Backend (Python 3.12+), from `backend/`:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python crop_areas.py       # dataset images -> crops/
.venv/bin/python train_dino.py       # labels + crops -> models/dino_*.joblib
.venv/bin/python classify_dino.py    # crops -> annotations.json (official output format)
.venv/bin/python server.py           # API on http://127.0.0.1:8000
```

Frontend, from `frontend/`:

```sh
npm install
npm run dev        # uses the API server; `npm run dev:mock` runs on mock data
```

To classify new images (e.g. the validation set): `classify_dino.py` reads every crop in
`backend/crops/`, so move the existing crops aside first, then run
`crop_areas.py --images <validation folder>` and `classify_dino.py`.

The output, `backend/annotations.json`, follows the challenge format:
`{camera: {image: {area_id: {planogram_compliant, stock_level, stock_value}}}}`.

More detail: `backend/README.md` (cropping and API) and `labeling/README.md` (labelling tool).
