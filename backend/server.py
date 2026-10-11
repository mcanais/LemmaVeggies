"""HTTP API for the LemmaVeggies frontend.

Serves the model predictions in submission.json (written by
gemini-code-supervisedLearning.py) together with the planogram and the camera
images. The JSON shapes match frontend/mock/mockApi.js.
"""
import argparse
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent


class BadRequest(Exception):
    pass


class Store:
    """Planogram, image list and predictions, reloaded when submission.json changes."""

    def __init__(self, planogram_path, images_dir, submission_path):
        self.planogram_path = Path(planogram_path)
        self.images_dir = Path(images_dir)
        self.submission_path = Path(submission_path)
        self._lock = threading.Lock()
        self._mtime = None
        self.cameras = {}
        self.images_by_camera = {}
        self.areas = {}

    def refresh(self):
        try:
            mtime = os.stat(self.submission_path).st_mtime
        except FileNotFoundError:
            mtime = None
        with self._lock:
            if self.cameras and mtime == self._mtime:
                return
            self._load()
            self._mtime = mtime

    def _load(self):
        with open(self.planogram_path, encoding="utf-8") as f:
            cameras = json.load(f)["Frutas e Legumes"]["cameras"]
        submission = {}
        if self.submission_path.exists():
            with open(self.submission_path, encoding="utf-8") as f:
                submission = json.load(f)

        images_by_camera = {}
        areas = {}
        for camera_id, camera in cameras.items():
            camera_dir = self.images_dir / camera_id
            images_by_camera[camera_id] = sorted(
                int(p.stem) for p in camera_dir.glob("*.jpg") if p.stem.isdigit()
            ) if camera_dir.is_dir() else []

            predictions = submission.get(camera_id, {})
            for p in camera["products"]:
                area_id = p["area_id"]
                history = sorted(
                    (
                        {
                            "timestamp": int(image[:-4]),
                            "compliant": by_area[area_id]["planogram_compliant"],
                            "stockLevel": by_area[area_id]["stock_level"],
                        }
                        for image, by_area in predictions.items()
                        if area_id in by_area
                    ),
                    key=lambda h: h["timestamp"],
                )
                areas[area_id] = {
                    "id": area_id,
                    "cameraId": camera_id,
                    "productId": p["product_id"],
                    "productName": p["product_name"],
                    "imageCoordinates": p["image_coordinates"],
                    "history": history,
                }

        self.cameras = cameras
        self.images_by_camera = images_by_camera
        self.areas = areas


def parse_range(query):
    bounds = []
    for key in ("from", "to"):
        value = query.get(key, [""])[0]
        if value == "":
            bounds.append(None)
            continue
        try:
            bounds.append(float(value))
        except ValueError:
            raise BadRequest(f"Invalid '{key}' parameter")
    return bounds


def in_range(timestamp, bounds):
    start, end = bounds
    return (start is None or timestamp >= start) and (end is None or timestamp <= end)


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, body, status=200):
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def send_image(self, camera_id, timestamp):
            path = store.images_dir / camera_id / f"{timestamp}.jpg"
            if not path.is_file():
                return self.send_json({"error": "Image not found"}, 404)
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def list_areas(self, query):
            result = []
            for area in store.areas.values():
                latest = area["history"][-1] if area["history"] else {"compliant": True, "stockLevel": "empty"}
                result.append({
                    "id": area["id"],
                    "cameraId": area["cameraId"],
                    "productName": area["productName"],
                    "compliant": latest["compliant"],
                    "stockLevel": latest["stockLevel"],
                })
            self.send_json(result)

        def get_area(self, query, area_id):
            area = store.areas.get(area_id)
            if not area:
                return self.send_json({"error": "Area not found"}, 404)
            bounds = parse_range(query)
            self.send_json({
                "id": area["id"],
                "cameraId": area["cameraId"],
                "productName": area["productName"],
                "history": [h for h in area["history"] if in_range(h["timestamp"], bounds)],
            })

        def list_cameras(self, query):
            self.send_json([
                {"id": camera_id, "areas": [p["area_id"] for p in camera["products"]]}
                for camera_id, camera in store.cameras.items()
            ])

        def get_camera(self, query, camera_id):
            camera = store.cameras.get(camera_id)
            if not camera:
                return self.send_json({"error": "Camera not found"}, 404)
            self.send_json({
                "id": camera_id,
                "areas": [
                    {"id": p["area_id"], "productName": p["product_name"], "imageCoordinates": p["image_coordinates"]}
                    for p in camera["products"]
                ],
            })

        def latest_image(self, query, camera_id):
            timestamps = store.images_by_camera.get(camera_id)
            if not timestamps:
                return self.send_json({"error": "No images"}, 404)
            self.send_image(camera_id, timestamps[-1])

        def list_images(self, query, camera_id):
            timestamps = store.images_by_camera.get(camera_id)
            if timestamps is None:
                return self.send_json({"error": "Camera not found"}, 404)
            bounds = parse_range(query)
            self.send_json([f"{camera_id}_{t}" for t in timestamps if in_range(t, bounds)])

        def get_image(self, query, camera_id, timestamp):
            self.send_image(camera_id, timestamp)

        ROUTES = [
            (re.compile(r"^/api/areas/?$"), list_areas),
            (re.compile(r"^/api/areas/([^/]+)/?$"), get_area),
            (re.compile(r"^/api/cameras/?$"), list_cameras),
            (re.compile(r"^/api/cameras/([^/]+)/?$"), get_camera),
            (re.compile(r"^/api/cameras/([^/]+)/images/latest/?$"), latest_image),
            (re.compile(r"^/api/cameras/([^/]+)/images/?$"), list_images),
            (re.compile(r"^/api/images/(\d+)_(\d+)/?$"), get_image),
        ]

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            for pattern, handler in self.ROUTES:
                match = pattern.match(url.path)
                if match:
                    try:
                        store.refresh()
                        return handler(self, query, *(unquote(g) for g in match.groups()))
                    except BadRequest as e:
                        return self.send_json({"error": str(e)}, 400)
            self.send_json({"error": "Not found"}, 404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="LemmaVeggies API server")
    parser.add_argument("--planogram", default=HERE.parent / "dataset" / "planogram.json")
    parser.add_argument("--images", default=HERE.parent / "dataset" / "train_test")
    parser.add_argument("--submission", default=HERE / "submission.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    store = Store(args.planogram, args.images, args.submission)
    store.refresh()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"Serving {len(store.areas)} areas from {len(store.cameras)} cameras on http://{args.host}:{args.port}/api")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
