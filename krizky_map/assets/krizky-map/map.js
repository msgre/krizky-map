/* krizky-map — Leaflet init for [data-map-mode] elements.
 *
 * Modes:
 *   detail — single pin, popup with name (+ category), no cluster.
 *   list   — fetch geojson, cluster, popup with name + category + detail link.
 *   full   — fetch geojson, cluster, side panel, optional locate button.
 *
 * Bez cross-plugin závislosti — filter integration je opt-in (listen na
 * `krizky-filters:update`); pokud filter není přítomen, mapa zobrazí vše.
 */
(function () {
  'use strict';

  document.querySelectorAll('[data-map-mode]').forEach(init);

  function init(el) {
    if (typeof L === 'undefined') {
      console.error('krizky-map: Leaflet not loaded. Check that <script src="…leaflet.js"> resolves and site.map.leaflet.js in config is correct.');
      return;
    }
    var mode = el.dataset.mapMode;
    var cfg = safeJson(el.dataset.mapConfig) || {};
    if (!cfg.tile || !cfg.tile.url) {
      console.error('krizky-map: no tile URL in map_config. Check site.map.tile.provider or set custom tile.url in config.');
    }
    if (mode === 'detail') initDetail(el, cfg);
    else if (mode === 'list' || mode === 'full') initListOrFull(el, cfg, mode);
  }

  function safeJson(s) { try { return s ? JSON.parse(s) : null; } catch (e) { return null; } }
  function safeBounds(s) {
    var b = safeJson(s);
    return (b && b.length === 2 && b[0].length === 2 && b[1].length === 2) ? b : null;
  }
  function deriveSrc() {
    // /kategorie-socha.html → /maps/kategorie-socha.geojson
    var stem = window.location.pathname.split('/').pop().replace(/\.html?$/i, '');
    return stem ? '/maps/' + stem + '.geojson' : '';
  }

  // ------------------------------------------------------------------
  // Detail: single pin, no cluster
  // ------------------------------------------------------------------
  function initDetail(el, cfg) {
    var lat = parseFloat(el.dataset.mapLat);
    var lng = parseFloat(el.dataset.mapLng);
    if (!isFinite(lat) || !isFinite(lng)) return;

    var zoom = parseInt(el.dataset.mapZoom, 10) || 15;
    var name = el.dataset.mapName || '';
    // `category` = slug (for icon lookup); `subtitle` = text under title in popup.
    var category = el.dataset.mapCategory || '';
    var subtitle = el.dataset.mapSubtitle || '';

    var map = L.map(el, { scrollWheelZoom: false }).setView([lat, lng], zoom);
    addTile(map, cfg);
    addMask(map, cfg);
    addOverlays(map, cfg);

    var marker = L.marker([lat, lng], { icon: buildIcon(cfg.markers, category) }).addTo(map);
    marker.bindPopup(popupHtml({ nazev: name, subtitle: subtitle }, cfg, { link: false }));
  }

  // ------------------------------------------------------------------
  // List / Full: geojson fetch, cluster, popup or panel
  // ------------------------------------------------------------------
  function initListOrFull(el, cfg, mode) {
    // Derive geojson URL from current pathname when template didn't set it —
    // works reliably for dynamic paths (e.g. /{{ category.slug }}.html) where
    // the SSR helper can't render the final stem.
    var src = el.dataset.mapSrc || deriveSrc();
    if (!src) { console.warn('krizky-map: could not resolve geojson URL'); return; }

    var wantCluster = el.dataset.mapCluster !== '0' && typeof L.markerClusterGroup === 'function';
    var initialBounds = safeBounds(el.dataset.mapBounds);

    var map = L.map(el);
    if (initialBounds) map.fitBounds(initialBounds, { padding: [30, 30], maxZoom: 12 });
    else map.setView(cfg.default_center || [49.4, 17.95], cfg.default_zoom || 9);

    addTile(map, cfg);
    addMask(map, cfg);
    addOverlays(map, cfg);

    var layerGroup = wantCluster ? L.markerClusterGroup(clusterOpts(cfg)) : L.layerGroup();
    map.addLayer(layerGroup);

    // Full-mode side panel (optional).
    var panelHooks = mode === 'full' ? findPanelHooks(el) : null;
    if (panelHooks && panelHooks.locateBtn) hookLocateBtn(map, panelHooks.locateBtn);

    // Active marker highlight — one marker at a time is "active" (popup open
    // in list mode, or last clicked in full mode). CSS class `k-marker-active`
    // lets projects style the highlight (default: subtle scale + higher z-index).
    var activeMarker = null;
    function setActive(m) {
      if (activeMarker === m) return;
      clearActive();
      activeMarker = m;
      var elm = m.getElement && m.getElement();
      if (elm) elm.classList.add('k-marker-active');
    }
    function clearActive() {
      if (!activeMarker) return;
      var elm = activeMarker.getElement && activeMarker.getElement();
      if (elm) elm.classList.remove('k-marker-active');
      activeMarker = null;
    }

    // Filter integration: listener must be registered BEFORE fetch so that
    // an early event from krizky-filters (initial URL state) is captured even
    // when its JSON loads faster than ours. We queue the last event until
    // markers exist, then apply it.
    var slugToMarker = {};
    var allSlugs = [];
    var markersReady = false;
    var pendingEvent = null;

    function applyEvent(e) {
      var recs = (e.detail && e.detail.filteredRecords) || [];
      var visible = {};
      recs.forEach(function (r) { if (r && r.slug) visible[r.slug] = 1; });
      applyFilter(layerGroup, slugToMarker, allSlugs, visible);
      if (panelHooks && panelHooks.count) panelHooks.count.textContent = String(recs.length);
      // Optional: re-fit the map on filter update (skip when 0 visible markers).
      if (cfg.fit_on_filter) fitVisible(map, slugToMarker, visible);
    }

    document.addEventListener('krizky-filters:update', function (e) {
      if (markersReady) applyEvent(e);
      else pendingEvent = e;  // Only the latest one matters — filter re-computes on every change.
    });

    fetch(src)
      .then(function (r) { return r.json(); })
      .then(function (fc) {
        (fc.features || []).forEach(function (f) {
          var props = f.properties || {};
          var coords = f.geometry && f.geometry.coordinates;
          if (!coords || coords.length < 2) return;
          var lat = coords[1], lng = coords[0];
          var slug = props.slug;
          var m = L.marker([lat, lng], { icon: buildIcon(cfg.markers, props[cfg.markers.category_field]) });
          if (panelHooks) {
            // Full mode: side panel replaces popup.
            m.on('click', function () {
              setActive(m);
              fillPanel(panelHooks, props, cfg);
            });
          } else {
            // List mode: bind popup once at construction time so Leaflet handles
            // toggle (open/close on click) itself — binding inside a click handler
            // would fight the built-in toggle and only work on first click.
            m.bindPopup(popupHtml(props, cfg, { link: true }));
            m.on('popupopen', function () { setActive(m); });
            m.on('popupclose', function () { if (activeMarker === m) clearActive(); });
          }
          layerGroup.addLayer(m);
          if (slug) { slugToMarker[slug] = m; allSlugs.push(slug); }
        });
        // SSR count in the template uses `records|length`, which is the
        // paginated subset. Geojson always holds every record for the page,
        // so it's the authoritative count. Filter events overwrite this later.
        if (panelHooks && panelHooks.count) {
          panelHooks.count.textContent = String((fc.features || []).length);
        }
        markersReady = true;
        if (pendingEvent) { applyEvent(pendingEvent); pendingEvent = null; }
      })
      .catch(function (e) { console.error('krizky-map: failed to load ' + src, e); });
  }

  // ------------------------------------------------------------------
  // Marker + cluster styling
  // ------------------------------------------------------------------
  function buildIcon(markers, category) {
    markers = markers || {};
    var shape = markers.shape === 'circle' ? 'circle' : 'drop';
    var size = markers.size || 32;
    var color = markers.color || '#850000';
    var iconId = null;
    if (markers.icon_prefix && category) iconId = markers.icon_prefix + category;
    else if (markers.fallback_icon) iconId = markers.fallback_icon;

    var inner = iconId
      ? '<svg class="k-marker-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#' + escAttr(iconId) + '"/></svg>'
      : '';
    var html = '<span class="k-marker-body"></span>' + inner;
    var anchor = shape === 'drop' ? [size / 2, size] : [size / 2, size / 2];
    var style = '--marker-color:' + escAttr(color) + ';width:' + size + 'px;height:' + size + 'px';
    if (markers.active_color) style += ';--marker-active-color:' + escAttr(markers.active_color);
    return L.divIcon({
      className: 'k-marker k-marker-' + shape,
      html: '<div class="k-marker-wrap" style="' + style + '">' + html + '</div>',
      iconSize: [size, size],
      iconAnchor: anchor,
      popupAnchor: [0, -size],
    });
  }

  function clusterOpts(cfg) {
    var c = cfg.cluster || {};
    return {
      showCoverageOnHover: false,
      maxClusterRadius: c.max_radius || 50,
      disableClusteringAtZoom: c.disable_at_zoom || 14,
      spiderfyOnMaxZoom: true,
      iconCreateFunction: function (cluster) {
        var n = cluster.getChildCount();
        var size = n >= 50 ? 48 : (n >= 10 ? 40 : 32);
        var cls = n >= 50 ? 'l' : (n >= 10 ? 'm' : 's');
        return L.divIcon({
          html: '<span>' + n + '</span>',
          className: 'k-cluster k-cluster-' + cls,
          iconSize: [size, size],
        });
      },
    };
  }

  // ------------------------------------------------------------------
  // Popup
  // ------------------------------------------------------------------
  function popupHtml(props, cfg, opts) {
    var link = opts && opts.link;
    var name = escHtml(props.name || props.nazev || '');
    // Subtitle: explicit props.subtitle (detail mode) → props[popup.subtitle_field] (list/full).
    var subField = cfg.popup && cfg.popup.subtitle_field;
    var subtitle = props.subtitle || (subField ? props[subField] : null);
    var out = '<div class="k-popup">';
    out += '<div class="k-popup-name">' + name + '</div>';
    if (subtitle) out += '<div class="k-popup-subtitle">' + escHtml(subtitle) + '</div>';
    if (link && props.slug) {
      out += '<a class="k-popup-link" href="/' + escAttr(props.slug) + '.html">Otevřít detail</a>';
    }
    out += '</div>';
    return out;
  }

  // ------------------------------------------------------------------
  // Side panel (full mode)
  // ------------------------------------------------------------------
  function findPanelHooks(mapEl) {
    var wrap = mapEl.closest('.krizky-map-full-wrap');
    if (!wrap) return null;
    return {
      panel: wrap.querySelector('[data-map-panel]'),
      detail: wrap.querySelector('[data-map-detail]'),
      hint: wrap.querySelector('[data-map-hint]'),
      count: wrap.querySelector('[data-map-count]'),
      locateBtn: wrap.querySelector('[data-map-locate]'),
    };
  }

  function fillPanel(hooks, props, cfg) {
    if (!hooks.detail) return;
    var name = escHtml(props.name || props.nazev || '');
    var loc = escHtml(props.location || props.umisteni || '');
    var labelField = cfg.markers.category_label_field || cfg.markers.category_field;
    var cat = props.category || (labelField ? props[labelField] : null);
    var thumb = buildThumb(props, cfg);
    var html = '';
    if (thumb) {
      var focalStyle = thumb.focal ? ' style="object-position:' + escAttr(thumb.focal) + '"' : '';
      html += '<div class="k-panel-thumb"><img src="' + escAttr(thumb.src) + '" alt=""' + focalStyle + '></div>';
    }
    if (loc) html += '<div class="k-panel-loc mono">' + loc + '</div>';
    html += '<h3 class="k-panel-name">' + name + '</h3>';
    if (cat) html += '<p class="k-panel-cat muted">' + escHtml(cat) + '</p>';
    if (props.slug) html += '<a class="k-panel-link" href="/' + escAttr(props.slug) + '.html">Otevřít detail</a>';
    hooks.detail.innerHTML = html;
    hooks.detail.hidden = false;
    if (hooks.hint) hooks.hint.hidden = true;
    if (window.matchMedia('(pointer:coarse)').matches && hooks.panel) {
      hooks.panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  // Compose a thumbnail URL from krizky-photos base_url + row number.
  // Uses the same conventions as _karta_filter.html in krizky-filters:
  // `{baseUrl}/{paddedRow}_{size}.{format}`. Adds focal_point when available.
  function buildThumb(props, cfg) {
    var panel = cfg.panel || {};
    var field = panel.thumbnail_field;
    var baseUrl = cfg.photos_base_url;
    if (!field || !baseUrl) return null;
    var rowId = props[field];
    if (rowId == null || rowId === '') return null;
    var pad = panel.thumbnail_pad || 3;
    var size = panel.thumbnail_size || 'thumb';
    var fmt = panel.thumbnail_format || 'jpg';
    var padded = String(rowId).padStart(pad, '0');
    var src = baseUrl + '/' + padded + '_' + size + '.' + fmt;
    var focal = null;
    if (window.krizkyPhotos && window.krizkyPhotos.focalPoints) {
      focal = window.krizkyPhotos.focalPoints[padded] || null;
    }
    return { src: src, focal: focal };
  }

  function hookLocateBtn(map, btn) {
    var userMarker = null, userCircle = null;
    btn.addEventListener('click', function () {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(function (pos) {
        var lat = pos.coords.latitude, lng = pos.coords.longitude;
        if (userMarker) map.removeLayer(userMarker);
        if (userCircle) map.removeLayer(userCircle);
        userCircle = L.circle([lat, lng], {
          radius: pos.coords.accuracy,
          color: '#4CAF50', fillColor: '#4CAF50', fillOpacity: 0.1, weight: 1,
        }).addTo(map);
        userMarker = L.circleMarker([lat, lng], {
          radius: 8, color: '#4CAF50', fillColor: '#4CAF50', fillOpacity: 0.9, weight: 2,
        }).addTo(map).bindPopup('Vaše poloha').openPopup();
        map.setView([lat, lng], 13);
      }, function () { /* denied / unavailable */ });
    });
  }

  // ------------------------------------------------------------------
  // Filter apply
  // ------------------------------------------------------------------
  function applyFilter(layer, slugToMarker, allSlugs, visible) {
    allSlugs.forEach(function (s) {
      var m = slugToMarker[s];
      if (!m) return;
      var shouldShow = visible[s];
      var has = layer.hasLayer(m);
      if (shouldShow && !has) layer.addLayer(m);
      else if (!shouldShow && has) layer.removeLayer(m);
    });
  }

  function fitVisible(map, slugToMarker, visible) {
    var latlngs = [];
    Object.keys(visible).forEach(function (s) {
      var m = slugToMarker[s];
      if (m && m.getLatLng) latlngs.push(m.getLatLng());
    });
    if (!latlngs.length) return;   // (a) — 0 markers = leave view alone.
    map.fitBounds(L.latLngBounds(latlngs), { padding: [30, 30], maxZoom: 15 });
  }

  // ------------------------------------------------------------------
  // Tile / mask / overlays
  // ------------------------------------------------------------------
  function addTile(map, cfg) {
    var t = cfg.tile || {};
    if (!t.url) return;
    L.tileLayer(t.url, {
      attribution: t.attribution || '',
      subdomains: t.subdomains && t.subdomains.length ? t.subdomains : 'abc',
      maxZoom: t.max_zoom || 19,
    }).addTo(map);
  }

  function addMask(map, cfg) {
    var m = cfg.mask;
    if (!m || !m.url) return;
    fetch(m.url).then(function (r) { return r.json(); }).then(function (data) {
      var geom = data.geometry || data;
      if (!geom || geom.type !== 'Polygon') return;
      var coords = geom.coordinates[0];
      var worldBounds = [[90, -180], [90, 180], [-90, 180], [-90, -180], [90, -180]];
      var hole = coords.map(function (c) { return [c[1], c[0]]; }).reverse();
      L.polygon([worldBounds, hole], {
        color: 'transparent',
        fillColor: m.fill_color || '#000000',
        fillOpacity: m.fill_opacity || 0.3,
        interactive: false,
        className: m.blur ? 'k-mask-blur k-mask-blur-' + m.blur : '',
      }).addTo(map);
    }).catch(function () { /* ignore */ });
  }

  function addOverlays(map, cfg) {
    (cfg.overlays || []).forEach(function (ov) {
      if (!ov.url) return;
      var style = ov.style || {};
      fetch(ov.url).then(function (r) { return r.json(); }).then(function (data) {
        L.geoJSON(data, {
          pointToLayer: function (f, ll) {
            if (style.type === 'circle') return L.circleMarker(ll, style);
            return L.marker(ll);
          },
          style: function () { return style; },
        }).addTo(map);
      }).catch(function () { /* ignore */ });
    });
  }

  // ------------------------------------------------------------------
  // Utils
  // ------------------------------------------------------------------
  function escHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
})();
