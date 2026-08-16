# krizky-map

Plugin pro [krizky](https://github.com/msgre/krizky) — mapy nad Leaflet.

Tři použití:
- **`map_detail(record)`** — malá mapa s jedním pinem (detail místa).
- **`map_list(records=filtered)`** — obdélníková mapa nad výpisem míst (kategorie, štítek, období).
- **`map_full(records=filtered)`** — celostránková mapa se side panelem (samostatná stránka).

Kompatibilní s `krizky-filters` — když je filter aktivní, mapa automaticky reaguje na `krizky-filters:update` a překreslí piny.

## Instalace

```bash
pip install krizky-map
```

Plugin je opt-in per stránku přes klíč `map:` v `pages.<X>`.

**Leaflet a markercluster** plugin nedodává (150 kB třetí strany knihovny s vlastní verzí a licencí). Uživatel si je stáhne do `assets/leaflet/` a v configu odkáže. Odkazy: [Leaflet](https://leafletjs.com/download.html), [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster/releases).

## Konfigurace

Do `config.yaml`:

```yaml
site:
  map:
    # OSM tile provider — osm | osm-hot | cartodb-positron | cartodb-voyager | custom
    tile:
      provider: osm
      # nebo custom:
      # url: https://tiles.example.com/{z}/{x}/{y}.png
      # attribution: '&copy; ...'
      # subdomains: [a, b, c]
      max_zoom: 19

    # Vzhled markeru
    markers:
      shape: drop                        # drop (kapka) | circle
      color: '#850000'
      size: 32
      # Když nastaveno, plugin dohledá <use href="#{icon_prefix}{value}"> pro každý pin.
      # Bez category_field všechny piny mají fallback ikonu (nebo žádnou).
      category_field: kategorie_slug
      icon_prefix: i-kategorie-
      fallback_icon: i-mark

    # Cluster (jen v list a full módu)
    cluster:
      max_radius: 50
      disable_at_zoom: 14

    # Volitelná maska (tmavá výplň mimo polygon)
    mask:
      polygon: ./data/valassko.geojson   # relativní ke config.yaml
      fill_color: '#000000'
      fill_opacity: 0.3
      blur: 2

    # Volitelné doplňkové overlay layers
    overlays:
      - source: ./data/osm-kostely.geojson
        style:
          type: circle
          radius: 6
          color: '#5a5a5a'
          fillColor: '#a0a0a0'
          fillOpacity: 0.5

    # Fallback pozice (0 records / neplatný bbox)
    default_center: [49.4, 17.95]
    default_zoom: 9

    # Cesty k lokálním asstům (uživatel stáhne Leaflet do svého assets/)
    leaflet:
      js: /assets/leaflet/leaflet.js
      css: /assets/leaflet/leaflet.css
    markercluster:
      js: /assets/leaflet/leaflet.markercluster.js
      css: /assets/leaflet/MarkerCluster.css
```

Per-page opt-in:

```yaml
pages:
  detail:
    detail: true
    template: detail.html
    map: true                            # opt-in — enable map assets for this page

  vsechna_mista:
    template: vsechna_mista.html
    map:
      # Fields, které skončí v geojson properties (default: [slug, nazev, umisteni]).
      # Popup v map_list používá nazev a category. Panel v map_full navíc thumbnail_url.
      fields: [nazev, umisteni, thumbnail_url]

  mapa:
    template: mapa.html
    map: true
```

## Nutné úpravy šablon

Standardní `head_injections` a `body_end_injections` (už jsou v projektu díky ostatním pluginům):

```html
<head>
  ...
  {{ head_injections | safe }}
</head>
<body>
  ...
  {{ body_end_injections | safe }}
</body>
```

### Detail stránka

```jinja2
{% from "_map.html" import map_detail %}

{% if record.latitude and record.longitude %}
<section class="detail-map">
  <h2>Mapa</h2>
  {{ map_detail(record) }}
</section>
{% endif %}
```

### Kategorie / tematický výpis

```jinja2
{% from "_map.html" import map_list %}
{{ map_list(filtered) }}
```

Když je stránka pod plugin `krizky-filters`, mapa se automaticky napojí na jeho `krizky-filters:update` event a překreslí piny při každé změně filtru. View (pozice + zoom) se nemění.

### Samostatná mapa

```jinja2
{% from "_map.html" import map_full %}
{{ map_full(filtered) }}
```

## Chování mapy

- **Bounding box** se počítá SSR z aktuálních records a předává v `data-map-bounds` — mapa se hned inicializuje na správný view (žádné "skoky" po fetchi geojson).
- **1 record**: `setView(lat, lng, 14)`. **0 records**: `default_center + default_zoom`.
- **Cluster ikony** jsou barevně sladěny s `markers.color`, 3 velikosti podle počtu (`<10`, `<50`, `>=50`).
- **Popup** v `map_detail` = název + kategorie. V `map_list` navíc odkaz „Otevřít detail".
- **Side panel** v `map_full` = thumbnail + název + kategorie + odkaz. Na mobilu se panel scrolluje do view.
- **Locate button** (jen `map_full`) = `navigator.geolocation` s markerem přesnosti.
- **Filter integration**: mapa poslouchá `krizky-filters:update`, filtruje své features podle `slug`. Nezávislé — funguje i bez filter pluginu.

## Bez JavaScriptu

Ve všech třech makrech se místo mapy zobrazí `<noscript>` s hláškou. Detail stránka může volání `map_detail()` obalit `{% if record.latitude and record.longitude %}` — sekce se nevygeneruje pro záznamy bez GPS.

## Licence

MIT
