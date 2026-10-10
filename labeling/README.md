# Labelling dashboard

A local dashboard to label planogram areas by hand: stock level (empty / half / full) and
whether the product is the one the planogram expects. Every area starts as **half stock,
correct product**; you confirm or change it.

```
review_server.py ──► labels/human.jsonl     your answers (latest per area wins)
export_labels.py ──► labels/labels.json     same format as the official annotations.json
```

`labeling_guide.md` defines empty / half / full and compliance (press `?` in the dashboard).
Only the Python standard library is needed.

## Label

Generate the crops first (see `backend/README.md`), then start the dashboard:

```bash
cd backend && .venv/bin/python crop_areas.py && cd ..
python3 labeling/review_server.py      # then open http://127.0.0.1:8000
```

You label one image at a time, one area at a time. The image shows the area you are on, and
the panel shows its crop (from `backend/crops/index.csv`) and the product the planogram
expects there.

| Key | Action |
|---|---|
| `↑` `↓` | previous / next area (or click an area on the image) |
| `1` `2` `3` | empty / half / full, then move to the next area |
| `X` / `C` | wrong / correct product |
| `U` | unsure: left out of the export |
| `Enter` | save every area of this image, go to the next image |
| `←` `→` | previous / next image without saving |
| `?` | labelling guide |

Filters:
- **Suggested (3 per camera)**, the default: unsaved images among the ones closest to 10:45
  and 15:00 plus the last image of each camera's day (closest to the validation images).
  Change the times in `SUGGESTED_TIMES` in `common.py`.
- **To review**: every image not saved yet.
- **All images**: to go back and fix one.

## Export

```bash
python3 labeling/export_labels.py
```

Writes `labels/labels.json` in the official format. Commit the `labels/` folder so the team
shares the same labels.
