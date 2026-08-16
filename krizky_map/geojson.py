"""GeoJSON generation for map pages.

Reads records with coordinate columns and produces a compact GeoJSON
``FeatureCollection`` with an optional ``bbox`` for fast initial fitBounds.
"""

from __future__ import annotations

import json
from pathlib import Path

# Fields that always end up in properties (they are the primary key + coords).
_ALWAYS_FIELDS = ("slug",)

DEFAULT_LAT_FIELD = "latitude"
DEFAULT_LNG_FIELD = "longitude"

# Reasonable defaults for the popup / marker. User overrides via page.map.fields.
DEFAULT_FIELDS = ["slug", "nazev", "umisteni"]


def build_feature_collection(
    records: list[dict],
    fields: list[str] | None,
    lat_field: str = DEFAULT_LAT_FIELD,
    lng_field: str = DEFAULT_LNG_FIELD,
) -> dict:
    """Return a GeoJSON FeatureCollection with per-record properties.

    Records lacking valid ``lat_field`` / ``lng_field`` are silently skipped —
    common for datasets where some entries have no coordinates yet.

    Args:
        records: List of record dicts (typically from the main table).
        fields: Property fields to include per feature. Falsy = DEFAULT_FIELDS.
        lat_field / lng_field: Column names for coordinates.

    Returns:
        Dict shaped as a GeoJSON FeatureCollection with optional ``bbox``.
    """
    prop_fields = list(fields) if fields else list(DEFAULT_FIELDS)
    for k in _ALWAYS_FIELDS:
        if k not in prop_fields:
            prop_fields.append(k)

    features: list[dict] = []
    lats: list[float] = []
    lngs: list[float] = []

    for record in records:
        lat = record.get(lat_field)
        lng = record.get(lng_field)
        if lat is None or lng is None:
            continue
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            continue

        props = {k: record.get(k) for k in prop_fields if k in record}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng_f, lat_f]},
            "properties": props,
        })
        lats.append(lat_f)
        lngs.append(lng_f)

    result: dict = {"type": "FeatureCollection", "features": features}
    if lats:
        result["bbox"] = [min(lngs), min(lats), max(lngs), max(lats)]
    return result


def bounds_from_feature_collection(fc: dict) -> list[list[float]] | None:
    """Return Leaflet-shape bounds ``[[minLat, minLng], [maxLat, maxLng]]`` or None.

    Falls back to computing from features if no ``bbox`` is stored.
    """
    bbox = fc.get("bbox")
    if bbox and len(bbox) == 4:
        min_lng, min_lat, max_lng, max_lat = bbox
        return [[min_lat, min_lng], [max_lat, max_lng]]
    features = fc.get("features", [])
    if not features:
        return None
    lats: list[float] = []
    lngs: list[float] = []
    for f in features:
        coords = f.get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lngs.append(coords[0])
        lats.append(coords[1])
    if not lats:
        return None
    return [[min(lats), min(lngs)], [max(lats), max(lngs)]]


def write_geojson(fc: dict, output_dir: Path, stem: str) -> Path:
    """Write ``fc`` as compact JSON to ``<output_dir>/maps/<stem>.geojson``."""
    dst = output_dir / "maps" / f"{stem}.geojson"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        json.dumps(fc, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return dst
