"""krizky-map plugin — hook implementations."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path, PurePosixPath

from jinja2 import ChoiceLoader, FileSystemLoader

from krizky.hooks import hookimpl
from krizky_map.geojson import (
    DEFAULT_LAT_FIELD,
    DEFAULT_LNG_FIELD,
    build_feature_collection,
    bounds_from_feature_collection,
    write_geojson,
)

_log = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).parent
_PLUGIN_TEMPLATES = _PLUGIN_DIR / "templates"
_PLUGIN_ASSETS = _PLUGIN_DIR / "assets"

# Tile provider presets. Users can override via `tile.url` + `tile.attribution`.
_TILE_PRESETS: dict[str, dict] = {
    "osm": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenStreetMap contributors",
        "subdomains": ["a", "b", "c"],
        "preconnect": ["https://a.tile.openstreetmap.org", "https://b.tile.openstreetmap.org", "https://c.tile.openstreetmap.org"],
    },
    "osm-hot": {
        "url": "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenStreetMap contributors, Humanitarian OSM Team",
        "subdomains": ["a", "b", "c"],
        "preconnect": ["https://a.tile.openstreetmap.fr", "https://b.tile.openstreetmap.fr"],
    },
    "cartodb-positron": {
        "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap contributors &copy; CARTO",
        "subdomains": ["a", "b", "c", "d"],
        "preconnect": ["https://a.basemaps.cartocdn.com", "https://b.basemaps.cartocdn.com"],
    },
    "cartodb-voyager": {
        "url": "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        "attribution": "&copy; OpenStreetMap contributors &copy; CARTO",
        "subdomains": ["a", "b", "c", "d"],
        "preconnect": ["https://a.basemaps.cartocdn.com", "https://b.basemaps.cartocdn.com"],
    },
}


def _resolve_tile(map_cfg: dict) -> dict:
    """Merge user tile config with a provider preset."""
    tile_cfg = dict(map_cfg.get("tile", {}) or {})
    provider = tile_cfg.pop("provider", "osm")
    preset = _TILE_PRESETS.get(provider, {})
    merged = {**preset, **{k: v for k, v in tile_cfg.items() if v is not None}}
    merged.setdefault("max_zoom", 19)
    return merged


def _page_map_cfg(page_cfg: dict) -> dict | None:
    """Return per-page map config dict or None when disabled."""
    m = page_cfg.get("map")
    if m is None or m is False:
        return None
    return {} if m is True else dict(m)


def _panel_config(panel_cfg: dict) -> dict:
    """Normalize the map_full side-panel config with defaults.

    Only ``thumbnail_field`` is user-required for photos; the rest have sane
    defaults matching krizky-photos conventions (zero-pad 3, size "thumb",
    format "jpg" — matches ``_normalize_base_name`` in the photos plugin).
    """
    return {
        "thumbnail_field": panel_cfg.get("thumbnail_field"),
        "thumbnail_size": panel_cfg.get("thumbnail_size", "thumb"),
        "thumbnail_format": panel_cfg.get("thumbnail_format", "jpg"),
        "thumbnail_pad": panel_cfg.get("thumbnail_pad", 3),
    }


def _label_field(markers_cfg: dict) -> str | None:
    """Resolve the display label field for a category.

    Priority: explicit ``category_label_field`` → auto-derived from
    ``category_field`` by trimming a trailing ``_slug`` (common convention:
    ``kategorie_slug`` → ``kategorie``). Returns None when neither is set.
    """
    if markers_cfg.get("category_label_field") is not None:
        return markers_cfg["category_label_field"]
    cf = markers_cfg.get("category_field")
    if cf and cf.endswith("_slug"):
        return cf[:-5]
    return cf


def _stem_from_html_path(html_path: str) -> str:
    return PurePosixPath(html_path.lstrip("/")).stem


class MapPlugin:
    """Leaflet-based map plugin for krizky.

    Hooks:
    - prepare_jinja2_environment: adds plugin templates + `map_config` global
    - inject_head: preconnect + Leaflet CSS + map.css for pages with `map:` cfg
    - inject_body_end: Leaflet JS + markercluster JS + map.js for pages with `map:` cfg
    - after_page_written: generates <output>/maps/<stem>.geojson for non-detail pages
    """

    def __init__(self) -> None:
        self._assets_copied: set[str] = set()
        self._config_dir: Path | None = None
        self._photos_base_url: str = ""

    # ------------------------------------------------------------------
    # prepare_jinja2_environment
    # ------------------------------------------------------------------

    @hookimpl
    def prepare_jinja2_environment(self, env, config, config_dir):
        """Insert plugin templates and expose map_config to templates."""
        self._config_dir = Path(config_dir) if config_dir else None
        if isinstance(env.loader, ChoiceLoader):
            loaders = env.loader.loaders
            already = any(
                isinstance(ldr, FileSystemLoader) and str(_PLUGIN_TEMPLATES) in ldr.searchpath
                for ldr in loaders
            )
            if not already:
                env.loader.loaders = (
                    [loaders[0], FileSystemLoader(str(_PLUGIN_TEMPLATES))] + loaders[1:]
                )
        map_cfg = config.get("site", {}).get("map", {}) or {}
        # krizky-photos base URL — needed for panel thumbnail composition.
        photos_cfg = config.get("sources", {}).get("photos", {}) or {}
        self._photos_base_url = (photos_cfg.get("base_url") or "").rstrip("/")
        # Register public URLs for mask + overlays now (before render). The actual
        # file copy happens in after_page_written when output_dir is known.
        self._register_data_urls(map_cfg)
        env.globals["map_config"] = self._runtime_map_config(map_cfg)
        markers_cfg = map_cfg.get("markers", {}) or {}
        _lat_field = markers_cfg.get("lat_field") or DEFAULT_LAT_FIELD
        _lng_field = markers_cfg.get("lng_field") or DEFAULT_LNG_FIELD

        def _map_bounds(records):
            """Compute [[minLat,minLng],[maxLat,maxLng]] from records with coords."""
            fc = build_feature_collection(records or [], None, _lat_field, _lng_field)
            return bounds_from_feature_collection(fc)

        env.globals["map_bounds"] = _map_bounds

    def _runtime_map_config(self, map_cfg: dict) -> dict:
        """Config shape exposed to templates as ``map_config``.

        Only values the JS actually needs — the plugin doesn't expose secrets
        or Python-only helpers here.
        """
        tile = _resolve_tile(map_cfg)
        markers = map_cfg.get("markers", {}) or {}
        cluster = map_cfg.get("cluster", {}) or {}
        mask = map_cfg.get("mask", {}) or {}
        return {
            "tile": {
                "url": tile.get("url", ""),
                "attribution": tile.get("attribution", ""),
                "subdomains": tile.get("subdomains", []),
                "max_zoom": tile.get("max_zoom", 19),
            },
            "markers": {
                "shape": markers.get("shape", "drop"),
                "color": markers.get("color", "#850000"),
                # Highlight color for the active marker (popup open / clicked in panel).
                # None = active marker keeps `color` (only scaled up).
                "active_color": markers.get("active_color"),
                "size": markers.get("size", 32),
                "category_field": markers.get("category_field"),
                "category_label_field": _label_field(markers),
                "icon_prefix": markers.get("icon_prefix", ""),
                "fallback_icon": markers.get("fallback_icon", ""),
            },
            "cluster": {
                "max_radius": cluster.get("max_radius", 50),
                "disable_at_zoom": cluster.get("disable_at_zoom", 14),
            },
            "mask": {
                # Path is resolved at build-time (see after_page_written); JS gets URL.
                "url": mask.get("_public_url"),
                "fill_color": mask.get("fill_color", "#000000"),
                "fill_opacity": mask.get("fill_opacity", 0.3),
                "blur": mask.get("blur", 0),
            } if mask else None,
            "overlays": [
                {
                    "url": ov.get("_public_url"),
                    "style": ov.get("style", {}),
                }
                for ov in (map_cfg.get("overlays") or [])
                if ov.get("_public_url")
            ],
            "default_center": map_cfg.get("default_center", [49.4, 17.95]),
            "default_zoom": map_cfg.get("default_zoom", 9),
            # When true, re-fit the map to the visible markers after each
            # `krizky-filters:update` (including the initial URL-driven filter).
            # Default false = view stays put on filter changes.
            "fit_on_filter": bool(map_cfg.get("fit_on_filter", False)),
            "popup": {
                # Column shown under the title in popup bubbles (list / detail modes).
                # Typically the place location — more useful than category when the
                # icon already indicates the type. None = only the title is shown.
                "subtitle_field": (map_cfg.get("popup", {}) or {}).get("subtitle_field"),
            },
            "panel": _panel_config(map_cfg.get("panel", {}) or {}),
            # Photo base URL — reused from krizky-photos config so map_full panel
            # can build thumbnail URLs the same way krizky-filters does.
            "photos_base_url": self._photos_base_url,
        }

    # ------------------------------------------------------------------
    # inject_head — CSS + preconnect for pages with map: cfg
    # ------------------------------------------------------------------

    @hookimpl
    def inject_head(self, page_cfg, config):
        if _page_map_cfg(page_cfg) is None:
            return None
        site_map = config.get("site", {}).get("map", {}) or {}
        tile = _resolve_tile(site_map)
        parts: list[str] = []

        for host in tile.get("preconnect", []) or []:
            parts.append(f'<link rel="preconnect" href="{host}">')

        leaflet_css = (site_map.get("leaflet", {}) or {}).get("css")
        cluster_css = (site_map.get("markercluster", {}) or {}).get("css")
        if leaflet_css:
            parts.append(f'<link rel="stylesheet" href="{leaflet_css}">')
        if cluster_css:
            parts.append(f'<link rel="stylesheet" href="{cluster_css}">')
        parts.append('<link rel="stylesheet" href="/krizky-map/map.css">')
        return "\n".join(parts) + "\n"

    # ------------------------------------------------------------------
    # inject_body_end — Leaflet JS + plugin JS
    # ------------------------------------------------------------------

    @hookimpl
    def inject_body_end(self, page_cfg, config):
        if _page_map_cfg(page_cfg) is None:
            return None
        site_map = config.get("site", {}).get("map", {}) or {}
        leaflet_js = (site_map.get("leaflet", {}) or {}).get("js")
        cluster_js = (site_map.get("markercluster", {}) or {}).get("js")
        parts: list[str] = []
        if not leaflet_js:
            _log.warning("site.map.leaflet.js is not configured; map will not work")
            return None
        parts.append(f'<script src="{leaflet_js}" defer></script>')
        if cluster_js:
            parts.append(f'<script src="{cluster_js}" defer></script>')
        parts.append('<script src="/krizky-map/map.js" defer></script>')
        return "\n".join(parts) + "\n"

    # ------------------------------------------------------------------
    # after_page_written — build geojson + copy assets + copy mask/overlays
    # ------------------------------------------------------------------

    @hookimpl
    def after_page_written(self, page_cfg, html_path, output_dir, records, config):
        page_map = _page_map_cfg(page_cfg)
        if page_map is None:
            return
        self._copy_assets(output_dir, config)

        # Detail pages don't need a geojson — data are inlined in data-* attrs.
        if page_cfg.get("detail"):
            return

        site_map = config.get("site", {}).get("map", {}) or {}
        markers_cfg = site_map.get("markers", {}) or {}
        popup_cfg = site_map.get("popup", {}) or {}
        panel_cfg = site_map.get("panel", {}) or {}
        lat_field = page_map.get("lat_field") or markers_cfg.get("lat_field") or DEFAULT_LAT_FIELD
        lng_field = page_map.get("lng_field") or markers_cfg.get("lng_field") or DEFAULT_LNG_FIELD
        # Auto-include fields that the plugin references implicitly:
        # - category_field / label_field: for marker icon + display name
        # - popup.subtitle_field: for popup subtitle in list/full mode
        # - panel.thumbnail_field: for map_full panel photo composition
        cat_field = markers_cfg.get("category_field")
        label_field = _label_field(markers_cfg)
        subtitle_field = popup_cfg.get("subtitle_field")
        thumb_field = panel_cfg.get("thumbnail_field")
        fields = list(page_map.get("fields") or ())
        for extra in (cat_field, label_field, subtitle_field, thumb_field):
            if extra and extra not in fields:
                fields.append(extra)
        fields = fields or None    # None = fall back to DEFAULT_FIELDS in geojson.py

        fc = build_feature_collection(records, fields, lat_field, lng_field)
        stem = _stem_from_html_path(html_path)
        write_geojson(fc, output_dir, stem)

    # ------------------------------------------------------------------
    # Assets: map.js/css + mask + overlays copied once per output dir.
    # ------------------------------------------------------------------

    def _register_data_urls(self, map_cfg: dict) -> None:
        """Populate ``_public_url`` on mask + overlays so map_config exposes them.

        Runs during prepare_jinja2_environment so map_config global has the
        URLs before any template is rendered. Actual file copy is deferred to
        after_page_written (needs output_dir).
        """
        mask = map_cfg.get("mask") or {}
        if mask.get("polygon") and self._resolve_source_path(mask["polygon"]):
            mask["_public_url"] = "/krizky-map/mask.geojson"
        for i, ov in enumerate(map_cfg.get("overlays") or []):
            if ov.get("source") and self._resolve_source_path(ov["source"]):
                ov["_public_url"] = f"/krizky-map/overlay-{i}.geojson"

    def _copy_assets(self, output_dir: Path, config: dict) -> None:
        key = str(output_dir)
        if key in self._assets_copied:
            return
        dst = output_dir / "krizky-map"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("map.js", "map.css"):
            src = _PLUGIN_ASSETS / "krizky-map" / name
            if src.exists():
                shutil.copy2(src, dst / name)

        # Copy mask polygon and overlay geojsons (URLs already registered in
        # prepare_jinja2_environment via _register_data_urls).
        site_map = config.get("site", {}).get("map", {}) or {}

        mask = site_map.get("mask") or {}
        if mask.get("polygon"):
            src_path = self._resolve_source_path(mask["polygon"])
            if src_path and src_path.exists():
                shutil.copy2(src_path, dst / "mask.geojson")

        for i, ov in enumerate(site_map.get("overlays") or []):
            src_path = self._resolve_source_path(ov.get("source"))
            if src_path and src_path.exists():
                shutil.copy2(src_path, dst / f"overlay-{i}.geojson")

        self._assets_copied.add(key)

    def _resolve_source_path(self, source: str | None) -> Path | None:
        """Resolve a config-relative path using config_dir stored from prepare_jinja2."""
        if not source:
            return None
        p = Path(source)
        if p.is_absolute() or self._config_dir is None:
            return p
        return (self._config_dir / p).resolve()


plugin = MapPlugin()
