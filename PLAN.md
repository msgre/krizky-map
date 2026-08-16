# krizky-map — implementační plán

## Cíl

Plugin do krizky pro tři use cases mapy nad Leaflet:

1. **Detail místa** — jeden pin s popupem (název + kategorie).
2. **Kategorie / štítek / období** — obdélníková mapa nad výpisem, cluster, popup s odkazem, integrace s `krizky-filters`.
3. **Samostatná stránka mapa** — velká mapa se side panelem (thumbnail + odkaz), locate button.

## Rozhodnutí (viz konverzace 2026-08-14/15)

- **Ikony markerů**: kapka („drop") s SVG symbolem uvnitř podle kategorie. Použití existujícího spritu projektu přes `<use href="#{icon_prefix}{value}"/>`. Bez configurace `category_field` → univerzální kapka.
- **Data**: vlastní geojson per stránka (`/maps/<stem>.geojson`), loose coupling s filter pluginem. Filter dispatch event → mapa filtruje features podle `slug`.
- **Bez JS**: `<noscript>` fallback. Detail sekce se nevygeneruje bez GPS.
- **Bounding box**: SSR-precomputed, předaný v `data-map-bounds`. Žádné „skoky" po fetchi. Filter update = jen piny, view se nemění.
- **Leaflet knihovny**: nedodává plugin — uživatel si stáhne do `assets/leaflet/`, plugin config referuje URL.
- **Overlays**: volitelný config `overlays: [{source, style}]` (pro sekundární data typu OSM kostely, cyklostezky).
- **Mask**: volitelný polygon výplně mimo Valašsko (`mask: {polygon, fill_color, fill_opacity, blur}`).
- **Locate button**: jen ve `map_full`.
- **Deep link `?id=slug&zoom=N`**: vynecháno (v starém webu nebyl reálně funkční).
- **Openstreetmaps kostely overlay**: vynecháno jako hardcoded, dostupné přes generickou `overlays` config.

## Struktura

```
_plugins/krizky-map/
├── PLAN.md, README.md, pyproject.toml
├── krizky_map/
│   ├── __init__.py
│   ├── plugin.py          — hooky
│   ├── geojson.py         — build FeatureCollection + bounds + write
│   ├── templates/_map.html — map_detail, map_list, map_full
│   └── assets/krizky-map/
│       ├── map.js         — Leaflet init, cluster, filter integration
│       └── map.css        — styly (kapka, cluster, popup, panel, layout)
└── tests/
    ├── test_geojson.py    — 14 testů (FeatureCollection, bounds, write)
    ├── test_plugin.py     — 15 testů (tile resolve, hooks, assets copy, mask, overlays)
    └── test_macros.py     — 15 testů (sanity render všech 3 maker)
```

## Hooky

| Hook | Kdy | Co vypíše |
|---|---|---|
| `prepare_jinja2_environment` | 1× per build | plugin templates do loaderu; Jinja globals `map_config`, `map_bounds` |
| `inject_head` | per page (pouze `map:` je set) | tile preconnect + `<link>` Leaflet.css + markercluster.css + map.css |
| `inject_body_end` | per page (pouze `map:` je set) | `<script>` Leaflet + markercluster + map.js |
| `after_page_written` | per page | pro non-detail stránky s `map:` → `/maps/<stem>.geojson`; assety + mask + overlays kopírované jednou per output |

## Konfigurace

**Globální** (`site.map:`) — projekt-wide invariants: tile provider, marker vzhled, cluster defaults, mask, overlays, leaflet URLs.

**Per-page** (`pages.<X>.map:`) — jen dva klíče:
- `map: true` — opt-in, plugin generuje geojson pro tuto stránku.
- `map: {fields: [...]}` — override properties v geojson (default: `slug, nazev, umisteni`).

**Chování mode** (cluster on/off, popup, panel) je určeno voláním makra (`map_detail`/`map_list`/`map_full`) — žádné configurable overrides.

## Integrace s krizky-filters

Filter plugin dispatchne `krizky-filters:update` s `detail.filteredRecords` (list objektů). Mapa vezme `record.slug`, filtruje své features.

Loose coupling — plugin filters není závislost, mapa funguje samostatně (pak zobrazí všechny features).

## Bounding box

- Server-side `build_feature_collection()` vrací `bbox: [minLng, minLat, maxLng, maxLat]` (GeoJSON standard).
- `bounds_from_feature_collection()` konvertuje na Leaflet formát `[[minLat, minLng], [maxLat, maxLng]]`.
- Šablona: `map_bounds(records)` global vypočte bounds → data-attribute → JS ho hned použije při init.
- 1 record → JS zapíná fallback `setView(lat, lng, 14)`. 0 records → `default_center + default_zoom`.

## Ikony marker

- `L.divIcon` s SVG `<use href="#..."/>` uvnitř — dědí barvu z projektu.
- Kapka (`drop`): border-radius 50% 50% 50% 0, rotate(-45deg). Ikona uvnitř bez rotace (absolute positioned).
- Kruh (`circle`): jednodušší vzhled bez „ocasu".

## Cluster

`L.markerClusterGroup` s config `max_radius` a `disable_at_zoom`. Ikona: 3 velikosti (`s`/`m`/`l`) podle count (`<10`/`<50`/`>=50`). Barva sladěna s `markers.color`.

## Testování

- Nespoléhá na Leaflet (JS runtime není v pytest env).
- Testy pokrývají: build_feature_collection s různými scénáři (chybějící coords, non-numeric, string parse, fields, bbox), bounds computation, write_geojson.
- Plugin: `_resolve_tile` presety a override, `inject_head/body_end` opt-in per page, `after_page_written` skipne detail, respektuje `fields`, přidává `category_field` do properties, kopíruje assety/mask/overlays jednou.
- Macros: `_map_root` data-attributes, `map_detail` bez coords → prázdný, custom height/zoom, `map_list` bounds + src, `map_full` panel + locate.
