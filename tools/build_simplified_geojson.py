#!/usr/bin/env python3
"""Build simplified prefecture GeoJSON for faster initial map load."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

Point = Tuple[float, float]


def perpendicular_distance(point: Point, start: Point, end: Point) -> float:
    (px, py), (sx, sy), (ex, ey) = point, start, end
    if sx == ex and sy == ey:
        return math.hypot(px - sx, py - sy)
    numerator = abs((ey - sy) * px - (ex - sx) * py + ex * sy - ey * sx)
    denominator = math.hypot(ex - sx, ey - sy)
    return numerator / denominator


def douglas_peucker(points: Sequence[Point], tolerance: float) -> List[Point]:
    if len(points) <= 2:
        return list(points)

    start = points[0]
    end = points[-1]

    max_distance = -1.0
    index = -1
    for i in range(1, len(points) - 1):
        distance = perpendicular_distance(points[i], start, end)
        if distance > max_distance:
            index = i
            max_distance = distance

    if max_distance > tolerance and index != -1:
        left = douglas_peucker(points[: index + 1], tolerance)
        right = douglas_peucker(points[index:], tolerance)
        return left[:-1] + right

    return [start, end]


def round_point(point: Point, digits: int) -> Point:
    return (round(point[0], digits), round(point[1], digits))


def simplify_ring(ring: List[List[float]], tolerance: float, digits: int) -> List[List[float]]:
    if len(ring) < 4:
        return ring

    closed = ring[0] == ring[-1]
    base = ring[:-1] if closed else ring[:]
    points = [(float(p[0]), float(p[1])) for p in base]

    simplified = douglas_peucker(points, tolerance)
    if len(simplified) < 3:
        simplified = points

    simplified = [round_point(p, digits) for p in simplified]

    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])

    if len(simplified) < 4:
        original = [round_point((float(p[0]), float(p[1])), digits) for p in points]
        if original[0] != original[-1]:
            original.append(original[0])
        simplified = original

    return [[p[0], p[1]] for p in simplified]


def simplify_polygon(coordinates: List[Any], tolerance: float, digits: int) -> List[Any]:
    return [simplify_ring(ring, tolerance, digits) for ring in coordinates]


def simplify_geometry(geometry: Dict[str, Any], tolerance: float, digits: int) -> Dict[str, Any]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Polygon" and isinstance(coords, list):
        return {"type": "Polygon", "coordinates": simplify_polygon(coords, tolerance, digits)}

    if gtype == "MultiPolygon" and isinstance(coords, list):
        return {
            "type": "MultiPolygon",
            "coordinates": [simplify_polygon(poly, tolerance, digits) for poly in coords],
        }

    return geometry


def slim_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(props, dict):
        return {}
    return {
        "id": props.get("id"),
        "nam": props.get("nam"),
        "nam_ja": props.get("nam_ja") or props.get("name_ja") or props.get("N03_004"),
    }


def simplify_feature_collection(fc: Dict[str, Any], tolerance: float, digits: int) -> Dict[str, Any]:
    features = fc.get("features") if isinstance(fc.get("features"), list) else []
    simplified = []

    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        props = feature.get("properties") if isinstance(feature, dict) else {}
        if not isinstance(geometry, dict):
            continue

        simplified.append(
            {
                "type": "Feature",
                "properties": slim_properties(props),
                "geometry": simplify_geometry(geometry, tolerance, digits),
            }
        )

    return {"type": "FeatureCollection", "features": simplified}


def dump_compact(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Simplify prefecture GeoJSON")
    parser.add_argument("--in", dest="input_path", default="frontend/dist/japan-prefectures.geojson")
    parser.add_argument("--out", dest="output_path", default="frontend/dist/data/japan-prefectures-simplified.geojson")
    parser.add_argument("--target-kb", type=int, default=900)
    parser.add_argument("--start-tolerance", type=float, default=0.01)
    parser.add_argument("--max-tolerance", type=float, default=0.15)
    parser.add_argument("--tolerance-step", type=float, default=0.01)
    parser.add_argument("--round-digits", type=int, default=4)
    args = parser.parse_args()

    root = Path.cwd()
    input_path = (root / args.input_path).resolve()
    output_path = (root / args.output_path).resolve()

    src = json.loads(input_path.read_text(encoding="utf-8"))

    tolerance = max(0.0, float(args.start_tolerance))
    max_tolerance = max(tolerance, float(args.max_tolerance))
    step = max(0.001, float(args.tolerance_step))
    target_bytes = int(args.target_kb) * 1024
    round_digits = max(0, int(args.round_digits))

    best_payload = simplify_feature_collection(src, tolerance, round_digits)
    best_text = dump_compact(best_payload)

    while len(best_text.encode("utf-8")) > target_bytes and tolerance < max_tolerance:
        tolerance = round(tolerance + step, 6)
        candidate_payload = simplify_feature_collection(src, tolerance, round_digits)
        candidate_text = dump_compact(candidate_payload)
        best_payload = candidate_payload
        best_text = candidate_text

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(best_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "features": len(best_payload.get("features", [])),
                "tolerance": tolerance,
                "size_bytes": len(best_text.encode("utf-8")),
                "target_bytes": target_bytes,
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
