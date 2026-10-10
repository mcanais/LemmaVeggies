"""Turn the reviewed labels into the official format.

Writes labels/labels.json in the same format as the official annotations.json:
    {camera: {image: {area_id: {planogram_compliant, stock_level, stock_value}}}}
Areas marked unsure are left out.

Usage:
    python3 labeling/export_labels.py
"""

import json

from common import LABELS_DIR, load_human_labels


def main():
    merged, unsure = {}, 0
    for (cam, img, area), h in sorted(load_human_labels().items()):
        if h.get("unsure"):
            unsure += 1
            continue
        merged.setdefault(cam, {}).setdefault(img, {})[area] = {
            "planogram_compliant": h["planogram_compliant"],
            "stock_level": h["stock_level"],
            "stock_value": h["stock_value"],
        }

    out = LABELS_DIR / "labels.json"
    LABELS_DIR.mkdir(exist_ok=True)
    out.write_text(json.dumps(merged, indent=1, ensure_ascii=False))
    n = sum(len(a) for imgs in merged.values() for a in imgs.values())
    print(f"{n} labelled areas written to {out} ({unsure} left out as unsure)")


if __name__ == "__main__":
    main()
