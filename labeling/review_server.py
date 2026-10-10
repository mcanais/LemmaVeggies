"""Local labelling dashboard: confirm or correct the stock level and product of every area, one image at a time.

Usage:
    python labeling/review_server.py        # then open http://127.0.0.1:8000

Answers are appended to labels/human.jsonl (latest entry per area wins).
Only the Python standard library is needed.
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import (
    CROPS_DIR,
    GUIDE,
    HUMAN_LABELS,
    IMAGES_DIR,
    LABELS_DIR,
    STOCK_VALUES,
    list_images,
    load_crop_index,
    load_human_labels,
    load_planogram,
    suggested_images,
)

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    planogram = load_planogram()
    images = list_images()
    image_set = set(images)
    area_ids = {cam: {a["area_id"] for a in areas} for cam, areas in planogram.items()}
    crops = load_crop_index()

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet

    def send(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if ctype == "application/json" else "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if not parts:
            return self.send(200, (STATIC / "review.html").read_bytes(), "text/html; charset=utf-8")
        if parts == ["api", "data"]:
            return self.send(200, self.data())
        if parts[0] == "image" and len(parts) == 3 and tuple(parts[1:]) in self.image_set:
            return self.send(200, (IMAGES_DIR / parts[1] / parts[2]).read_bytes(), "image/jpeg")
        if parts[0] == "crop" and len(parts) == 4:
            path = self.crops.get(tuple(parts[1:]))
            if path and path.exists():
                return self.send(200, path.read_bytes(), "image/jpeg")
        self.send(404, {"error": "not found"})

    def do_POST(self):
        """Save every area of one image: {camera, image, areas: [{area_id, stock_level, ...}]}."""
        if self.path != "/api/labels":
            return self.send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            cam, img = body["camera"], body["image"]
            assert (cam, img) in self.image_set, "unknown image"
            now = int(time.time())
            rows = []
            for a in body["areas"]:
                assert a["area_id"] in self.area_ids[cam], f"unknown area {a['area_id']}"
                assert a["stock_level"] in STOCK_VALUES, "bad stock_level"
                rows.append({
                    "camera": cam,
                    "image": img,
                    "area_id": a["area_id"],
                    "stock_level": a["stock_level"],
                    "stock_value": STOCK_VALUES[a["stock_level"]],
                    "planogram_compliant": bool(a["planogram_compliant"]),
                    "unsure": bool(a.get("unsure", False)),
                    "time": now,
                })
        except (ValueError, KeyError, TypeError, AssertionError) as e:
            return self.send(400, {"error": str(e)})
        LABELS_DIR.mkdir(exist_ok=True)
        with HUMAN_LABELS.open("a") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        self.send(200, {"ok": True, "labels": rows})

    def data(self):
        key = lambda k: "/".join(k)
        return {
            "guide": GUIDE.read_text(),
            "planogram": self.planogram,
            "images": self.images,
            "suggested": sorted(suggested_images(self.images)),
            "human": {key(k): v for k, v in load_human_labels().items()},
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if not Handler.crops:
        raise SystemExit(f"No crops found in {CROPS_DIR}. Run backend/crop_areas.py first.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Review dashboard on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
