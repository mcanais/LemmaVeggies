"""Read compliance labels: the challenge's annotations.json format or the labelling tool's .jsonl."""
import json
from pathlib import Path

LabelKey = tuple[str, str, str]  # (camera_id, image, area_id)


def _load_json(path: Path) -> dict[LabelKey, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        (str(camera_id), image, area_id): ann
        for camera_id, images in data.items()
        for image, areas in images.items()
        for area_id, ann in areas.items()
    }


def _load_jsonl(path: Path, keep_unsure: bool) -> dict[LabelKey, dict]:
    """One label per line. An area labelled more than once keeps its latest `time` (a correction)."""
    latest: dict[LabelKey, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            key = (str(r["camera"]), r["image"], r["area_id"])
            if key not in latest or r.get("time", 0) >= latest[key].get("time", 0):
                latest[key] = r
    return {k: r for k, r in latest.items() if keep_unsure or not r.get("unsure", False)}


def load_annotations(paths: list[Path], keep_unsure: bool = False) -> dict[LabelKey, dict]:
    """{(camera_id, image, area_id): annotation dict}. Later files win."""
    out = {}
    for path in paths:
        path = Path(path)
        out.update(_load_jsonl(path, keep_unsure) if path.suffix == ".jsonl" else _load_json(path))
    return out


def load_labels(paths: list[Path], keep_unsure: bool = False) -> dict[LabelKey, bool]:
    """{(camera_id, image, area_id): planogram_compliant}; stock fields are ignored."""
    return {
        k: bool(a["planogram_compliant"])
        for k, a in load_annotations(paths, keep_unsure).items()
        if "planogram_compliant" in a
    }
