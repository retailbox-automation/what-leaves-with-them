/* What Leaves With Them: the one-page demo over the honest-memory HTTP API.
 *
 * Flow: the company graph -> pick a person (what_leaves, depth 1-4) -> Remove (without, single_source, bridges)
 * -> Plan the handoff (handoff_plan, single_source before and after, promises) -> Show Cypher (trace of the last action).
 * Every number and name on screen comes from an API answer; the page never writes to the graph.
 */
'use strict';

(() => {
  // ---- configuration ------------------------------------------------------------------------------------------------
  // One-line switch: 'live' asks the API of this server; 'fixtures' reads answers recorded from it (web/fixtures/).
  const DATA = 'live';

  const query = new URLSearchParams(location.search);
  const SOURCE = ['live', 'fixtures'].includes(query.get('data')) ? query.get('data') : DATA;
  const TENANT = /^[A-Za-z0-9_-]{1,64}$/.test(query.get('tenant') || '') ? query.get('tenant') : 'quillfield';
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ms = (t) => (REDUCED ? 0 : t);
  const DAYS_PER_ANSWER = 3;        // what one answer costs on the countdown (a game rule, not data)
  const ASSUMED_NOTICE_DAYS = 14;   // when the graph records no last day for the person
  const W = 1600, H = 900;          // layout space
  const STEP_MS = 170;              // one hop of the depth animation
  const ZONE_ORDER = ['Payments', 'Platform', 'Support', 'Growth'];
  const HIDDEN_EDGES = new Set(['MEMBER_OF']);  // membership is the zone itself

  const $ = (id) => document.getElementById(id);
  const app = $('app');
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(name).trim();
  const C = {
    blue: token('--blue'), red: token('--red'), green: token('--green'), node: token('--node'),
    nodeInk: token('--node-ink'), ink: token('--ink'), muted: token('--muted'),
    zones: [token('--zone-1'), token('--zone-2'), token('--zone-3'), token('--zone-4')],
  };

  // ---- small helpers ------------------------------------------------------------------------------------------------
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const first = (name) => String(name).split(' ')[0];
  const initials = (name) => String(name).split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
  const plural = (n, one, many) => (n === 1 ? one : many);
  const day = (iso) => (iso ? String(iso).slice(0, 10) : '');
  const daysBetween = (a, b) => Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000);
  const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sleep = (t) => new Promise((r) => setTimeout(r, t));

  function mulberry32(seed) {
    return () => {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function mix(hexA, hexB, t) {
    const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const a = p(hexA), b = p(hexB);
    return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join('');
  }

  // ---- data: live API or recorded answers ---------------------------------------------------------------------------
  const api = {
    source: SOURCE,
    cache: new Map(),
    files: new Map(),
    schemas: null,

    key(name, args) {
      return [name, ...Object.keys(args).sort().map((k) => `${k}=${args[k]}`)].join('|');
    },

    async http(url, opts) {
      const t0 = performance.now();
      const res = await fetch(url, opts);
      let body = {};
      try { body = await res.json(); } catch (_) { body = {}; }
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
      return { body, roundtrip: Math.round(performance.now() - t0) };
    },

    file(name) {
      if (!this.files.has(name)) {
        this.files.set(name, fetch(`fixtures/${name}`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
      }
      return this.files.get(name);
    },

    async recorded(key, person) {
      const book = await this.file(person ? `people/${slug(person)}.json` : 'common.json');
      if (!(key in book)) throw new Error(`no recorded answer for ${key}`);
      return { body: book[key], roundtrip: null };
    },

    // GET or POST against the API; on failure (or in fixtures mode) the recorded answer, if there is one.
    async get(key, person, live) {
      if (this.cache.has(key)) return this.cache.get(key);
      const p = (async () => {
        if (this.source === 'live') {
          try { return await live(); } catch (err) {
            const rec = await this.recorded(key, person).catch(() => null);
            if (!rec) throw err;
            setStatus('The live API did not answer; showing recorded answers.');
            return rec;
          }
        }
        return this.recorded(key, person);
      })();
      this.cache.set(key, p);
      p.catch(() => this.cache.delete(key));
      return p;
    },

    graph() {
      return this.get('graph', null, () => this.http(`v1/${TENANT}/graph`));
    },

    async loadSchemas() {
      try {
        const { body } = await this.get('tools', null, () => this.http(`v1/${TENANT}/tools`));
        this.schemas = Object.fromEntries((body.tools || []).map((t) => [t.name, t]));
      } catch (_) { this.schemas = {}; }
    },

    accepts(tool, arg) {
      const t = this.schemas && this.schemas[tool];
      return Boolean(t && t.parameters && t.parameters.properties && arg in t.parameters.properties);
    },

    tool(name, args) {
      return this.get(this.key(name, args), args.person, () => this.http(`v1/${TENANT}/tools/${name}`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(args),
      }));
    },

    episode(id) {
      return this.get(`episode|${id}`, null, () => this.http(`v1/${TENANT}/episodes/${encodeURIComponent(id)}`));
    },

    confirmReceipts() {
      return this.get('receipts|confirm', null, () => this.http(`v1/${TENANT}/receipts?outcome=confirm&limit=200`));
    },
  };

  function setStatus(text) { $('status').textContent = text || ''; }

  // ---- the model: nodes, edges, zones -------------------------------------------------------------------------------
  const model = { nodes: new Map(), edges: [], teams: [], zoneOf: new Map(), home: new Map(), leaving: new Map(), graph: null };

  function buildModel(g) {
    model.graph = g;
    for (const n of g.nodes) model.nodes.set(n.id, { ...n });
    const teams = g.nodes.filter((n) => n.kind === 'team').map((n) => n.id);
    teams.sort((a, b) => {
      const ia = ZONE_ORDER.indexOf(a), ib = ZONE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
    model.teams = teams;
    teams.forEach((t, i) => model.zoneOf.set(t, i));
    model.edges = [...g.edges.map((e) => ({ ...e, ended: false })), ...g.ended.map((e) => ({ ...e, ended: true }))];
    for (const r of g.leaving || []) model.leaving.set(r.person, r);
  }

  const drawnNode = (n) => n.kind !== 'team';
  const drawnEdge = (e) => !HIDDEN_EDGES.has(e.type) && !(e.type === 'LEADS' && model.nodes.get(e.target)?.kind === 'team')
    && model.nodes.has(e.source) && model.nodes.has(e.target);
  const edgeId = (e) => `${e.type}|${e.source}|${e.target}`;

  // Each team gets a region of the layout space: four quadrants with a cross-shaped gap between them. Rows and
  // columns are sized by how many nodes the teams in them hold.
  const regions = new Map();

  function planRegions() {
    const count = new Map(model.teams.map((t) => [t, 0]));
    for (const n of model.nodes.values()) if (drawnNode(n) && placeOf(n).team) count.set(placeOf(n).team, (count.get(placeOf(n).team) || 0) + 1);
    const c = (i) => count.get(model.teams[i]) || 0;
    const L = 20, R = W - 20, T = 92, B = H - 40, GX = 150, GY = 96;
    const top = Math.max(c(0), c(1)), bottom = Math.max(c(2), c(3));
    const share = Math.max(0.42, Math.min(0.6, top / Math.max(1, top + bottom)));
    const split = T + (B - T - GY) * share;
    const left = Math.max(c(0), c(2)), right = Math.max(c(1), c(3));
    const colShare = Math.max(0.44, Math.min(0.56, left / Math.max(1, left + right)));
    const mid = L + (R - L - GX) * colShare;
    const rects = [
      [L, T, mid, split], [mid + GX, T, R, split],
      [L, split + GY, mid, B], [mid + GX, split + GY, R, B],
    ];
    model.teams.forEach((t, i) => {
      if (i < 4) { const [x0, y0, x1, y1] = rects[i]; regions.set(t, { x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 }); }
    });
    regions.set('', { x0: mid, y0: split, x1: mid + GX, y1: split + GY, cx: mid + GX / 2, cy: split + GY / 2, gapX: [mid, mid + GX], gapY: [split, split + GY] });
  }

  // Where a node is drawn: in its team's zone, or between two zones when it is a decision that governs a system of
  // another team (that is the decision a person leaving takes across a team line).
  const places = new Map();

  function placeOf(n) {
    if (places.has(n.id)) return places.get(n.id);
    let place = { team: n.team, between: null };
    if (n.kind === 'decision' && n.team) {
      const other = model.edges.filter((e) => e.type === 'CONSTRAINS' && e.source === n.id)
        .map((e) => model.nodes.get(e.target)?.team).find((t) => t && t !== n.team);
      if (other) place = { team: null, between: [n.team, other] };
    }
    if (place.team && !model.zoneOf.has(place.team)) place.team = null;
    places.set(n.id, place);
    return place;
  }

  function zoneCenter(team) {
    const r = regions.get(team);
    return r ? [r.cx, r.cy] : [regions.get('').cx, regions.get('').cy];
  }

  function homeOf(n) {
    const place = placeOf(n);
    if (place.team) return zoneCenter(place.team);
    const gap = regions.get('');
    if (place.between) {
      const [a, b] = place.between.map(zoneCenter);
      const x = (a[0] + b[0]) / 2, y = (a[1] + b[1]) / 2;
      return [x, y];
    }
    return [gap.cx, gap.cy];
  }

  function boundsOf(p) {
    const place = placeOf(p.n);
    const r = regions.get(place.team);
    if (r) return [r.x0 + 46, r.y0 + 84, r.x1 - 46, r.y1 - 30];
    const g = regions.get('');
    const [hx, hy] = p.home;
    const inGapX = Math.abs(hx - (g.gapX[0] + g.gapX[1]) / 2) < 2, inGapY = Math.abs(hy - (g.gapY[0] + g.gapY[1]) / 2) < 2;
    if (inGapX && !inGapY) return [g.gapX[0] + 30, 120, g.gapX[1] - 30, H - 60];
    if (inGapY && !inGapX) return [60, g.gapY[0] + 22, W - 60, g.gapY[1] - 22];
    return [g.gapX[0] - 10, g.gapY[0] - 10, g.gapX[1] + 10, g.gapY[1] + 10];
  }

  // A small deterministic force layout: every load gives the same picture, which then stays still.
  function layout() {
    planRegions();
    const rnd = mulberry32(42);
    const pts = [...model.nodes.values()].filter(drawnNode).map((n) => {
      const home = homeOf(n);
      const p = { id: n.id, n, x: home[0] + (rnd() - 0.5) * 200, y: home[1] + (rnd() - 0.5) * 120, vx: 0, vy: 0,
        r: n.kind === 'project' ? 16 : 24, home, team: placeOf(n).team };
      p.bounds = boundsOf(p);
      return p;
    });
    const index = new Map(pts.map((p, i) => [p.id, i]));
    const links = model.edges.filter(drawnEdge).map((e) => [index.get(e.source), index.get(e.target)])
      .filter(([a, b]) => a !== undefined && b !== undefined);
    const N = 600;
    for (let it = 0; it < N; it++) {
      const alpha = 1 - it / N;
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i], b = pts[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { dx = rnd() - 0.5; dy = rnd() - 0.5; d2 = 1; }
          if (d2 > 240 * 240) continue;
          const d = Math.sqrt(d2);
          let f = (a.team === b.team ? 1100 : 400) / d2;
          const min = a.r + b.r + 34;
          if (d < min) f += (min - d) * 0.45 / d;
          a.vx += dx * f * 0.5; a.vy += dy * f * 0.5; b.vx -= dx * f * 0.5; b.vy -= dy * f * 0.5;
        }
      }
      for (const [i, j] of links) {
        const a = pts[i], b = pts[j];
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
        const same = a.team && a.team === b.team;
        const k = (same ? 0.01 : 0.002) * (d - (same ? 96 : 200)) / d;
        a.vx += dx * k; a.vy += dy * k; b.vx -= dx * k; b.vy -= dy * k;
      }
      for (const p of pts) {
        const g = p.team ? 0.03 : 0.03;
        p.vx += (p.home[0] - p.x) * g; p.vy += (p.home[1] - p.y) * g;
        const step = 12 * (0.25 + alpha);
        p.vx = Math.max(-step, Math.min(step, p.vx)); p.vy = Math.max(-step, Math.min(step, p.vy));
        p.x += p.vx; p.y += p.vy; p.vx *= 0.5; p.vy *= 0.5;
        const [x0, y0, x1, y1] = p.bounds;
        p.x = Math.max(x0, Math.min(x1, p.x)); p.y = Math.max(y0, Math.min(y1, p.y));
      }
    }
    for (const p of pts) model.home.set(p.id, { x: Math.round(p.x), y: Math.round(p.y) });
  }

  // ---- cytoscape ----------------------------------------------------------------------------------------------------
  let cy = null;

  function nodeData(n) {
    const zi = model.zoneOf.get(n.team);
    const zone = zi === undefined ? '#6b7591' : C.zones[zi % C.zones.length];
    return { id: n.id, kind: n.kind, initials: n.kind === 'person' ? initials(n.id) : '', zone,
      fill: zi === undefined ? C.node : mix(C.node, zone, 0.1), dim: n.kind === 'decision' && n.status === 'superseded' ? 1 : 0 };
  }

  function styles() {
    const T = 'background-color, border-color, border-width, border-opacity, opacity, underlay-opacity, underlay-padding, line-color, width, color';
    return [
      { selector: 'node', style: {
        'background-color': 'data(fill)', 'border-width': 1.5, 'border-color': 'data(zone)', 'border-opacity': 0.5,
        label: 'data(initials)', color: C.nodeInk, 'font-size': 13, 'font-weight': 600, 'text-valign': 'center',
        'text-halign': 'center', 'font-family': token('--font'), 'underlay-color': C.blue, 'underlay-opacity': 0,
        'underlay-padding': 9, 'transition-property': T, 'transition-duration': ms(280), 'transition-timing-function': 'ease-out',
      } },
      { selector: 'node[kind = "person"]', style: { shape: 'ellipse', width: 44, height: 44, 'underlay-shape': 'ellipse' } },
      { selector: 'node[kind = "system"]', style: { shape: 'round-rectangle', width: 38, height: 38, 'underlay-shape': 'round-rectangle' } },
      { selector: 'node[kind = "decision"]', style: { shape: 'round-diamond', width: 40, height: 40, 'underlay-shape': 'ellipse' } },
      { selector: 'node[kind = "project"]', style: { shape: 'round-hexagon', width: 26, height: 26, 'underlay-shape': 'ellipse' } },
      { selector: 'node[dim = 1]', style: { 'border-style': 'dashed' } },
      { selector: 'node.faded', style: { opacity: 0.45 } },
      { selector: 'node.lit', style: { 'border-color': C.blue, 'border-opacity': 1, 'border-width': 2.5, 'background-color': '#0e2846',
        'underlay-color': C.blue, 'underlay-opacity': 0.16, color: '#d6e9f8', opacity: 1 } },
      { selector: 'node.tail', style: { 'border-color': C.blue, 'border-opacity': 0.75, 'border-width': 2, opacity: 1 } },
      { selector: 'node.pick', style: { 'border-color': '#6cb8ec', 'border-width': 3, 'background-color': '#0f2c4f',
        'underlay-color': C.blue, 'underlay-opacity': 0.3, 'underlay-padding': 14, color: '#ffffff', opacity: 1 } },
      { selector: 'node.ghost', style: { 'background-opacity': 0, 'border-style': 'dashed', 'border-color': '#8a94ae',
        'border-opacity': 0.9, 'border-width': 2, label: '', 'underlay-opacity': 0, opacity: 1 } },
      { selector: 'node.island', style: { 'border-color': C.red, 'border-opacity': 1, 'border-width': 2.5, 'background-color': '#3a1219',
        'underlay-color': C.red, 'underlay-opacity': 0.26, 'underlay-padding': 13, color: '#ffd1d2', opacity: 1 } },
      { selector: 'node.single', style: { 'border-color': C.red, 'border-opacity': 1, 'border-width': 2.5, 'background-color': '#2e1218',
        'underlay-color': C.red, 'underlay-opacity': 0.16, opacity: 1 } },
      { selector: 'node.saved', style: { 'border-color': C.green, 'border-opacity': 1, 'border-width': 2.5, 'background-color': '#0f3326',
        'underlay-color': C.green, 'underlay-opacity': 0.24, 'underlay-padding': 12, color: '#d9f7e8', opacity: 1 } },
      { selector: 'node.succ', style: { 'border-color': C.green, 'border-opacity': 1, 'border-width': 2.5,
        'underlay-color': C.green, 'underlay-opacity': 0.2, color: '#d9f7e8', opacity: 1 } },
      { selector: 'edge', style: {
        width: 1, 'line-color': '#8f9cc0', opacity: 0.22, 'curve-style': 'straight', 'arrow-scale': 0.9,
        'target-arrow-color': C.blue, 'source-arrow-color': C.blue,
        'transition-property': T + ', source-distance-from-node, target-distance-from-node', 'transition-duration': ms(280),
      } },
      { selector: 'edge.faded', style: { opacity: 0.12 } },
      { selector: 'edge.lit', style: { 'line-color': C.blue, width: 2.4, opacity: 1, 'z-index': 10 } },
      { selector: 'edge.lit.fwd', style: { 'target-arrow-shape': 'triangle' } },
      { selector: 'edge.lit.back', style: { 'source-arrow-shape': 'triangle' } },
      { selector: 'edge.tail', style: { 'line-color': C.blue, width: 1.5, opacity: 0.5, 'z-index': 9 } },
      { selector: 'edge.snap', style: { 'line-color': C.red, 'line-style': 'dashed', 'line-dash-pattern': [7, 6], width: 2,
        opacity: 0.9, 'z-index': 10 } },
      { selector: 'edge.snap.weak', style: { width: 1.4, opacity: 0.5 } },
      { selector: 'edge.snap.after', style: { opacity: 0.22 } },
      { selector: 'edge.snap-s', style: { 'source-distance-from-node': 16 } },
      { selector: 'edge.snap-t', style: { 'target-distance-from-node': 16 } },
      { selector: 'edge.handover', style: { 'line-color': C.green, 'line-style': 'dashed', 'line-dash-pattern': [7, 6], width: 2,
        opacity: 0.95, 'z-index': 11 } },
    ];
  }

  function initCy() {
    const elements = [];
    for (const n of model.nodes.values()) {
      if (!drawnNode(n)) continue;
      elements.push({ group: 'nodes', data: nodeData(n), position: { ...model.home.get(n.id) } });
    }
    for (const e of model.edges.filter(drawnEdge)) {
      elements.push({ group: 'edges', data: { id: edgeId(e), source: e.source, target: e.target, type: e.type } });
    }
    cy = cytoscape({
      container: $('cy'), elements, layout: { name: 'preset' }, style: styles(),
      userZoomingEnabled: false, userPanningEnabled: false, boxSelectionEnabled: false,
      autoungrabify: true, autounselectify: true, minZoom: 0.05, maxZoom: 4,
    });
    cy.on('render', scheduleSync);
    cy.on('tap', 'node', (ev) => onTapNode(ev.target));
    cy.on('tap', (ev) => { if (ev.target === cy) onTapBackground(); });
    cy.on('mouseover', 'node, edge', (ev) => showTip(ev.target, ev.originalEvent));
    cy.on('mousemove', 'node, edge', (ev) => moveTip(ev.originalEvent));
    cy.on('mouseout', 'node, edge', hideTip);
  }

  // ---- fitting the drawing into the free part of the screen ---------------------------------------------------------
  function freeRect() {
    const w = innerWidth, h = innerHeight;
    const narrow = w <= 760;
    const top = narrow ? 110 : Math.max(96, h * 0.115);
    let bottom = narrow ? h - 120 : h - Math.max(120, h * 0.16);
    let right = w - 16;
    if (state.phase === 'game') {
      if (narrow) bottom = h * 0.48 - 8; else right = w - $('game').getBoundingClientRect().width - 24;
    }
    if (state.phase === 'done' && !narrow) {
      bottom = h - Math.max(70, h * 0.07);
      if (w >= 1100) right = w - $('handoff').getBoundingClientRect().width - 40;
    }
    return { x: 16, y: top, w: Math.max(100, right - 16), h: Math.max(100, bottom - top) };
  }

  function fit(animate, focus) {
    // the whole drawing, or (in the game) the part around the people and items in play, never zoomed in past 1.6x
    let pts = [...model.home.values()];
    let margin = 70;
    if (focus && focus.length) {
      pts = focus.flatMap((id) => [model.home.get(id), cy.getElementById(id).length ? cy.getElementById(id).position() : null]).filter(Boolean);
      margin = 110;
    }
    const minX = Math.min(...pts.map((p) => p.x)) - margin, maxX = Math.max(...pts.map((p) => p.x)) + margin;
    const minY = Math.min(...pts.map((p) => p.y)) - margin, maxY = Math.max(...pts.map((p) => p.y)) + margin - 10;
    const r = freeRect();
    const full = Math.min(r.w / W, r.h / H);
    const zoom = Math.min(r.w / (maxX - minX), r.h / (maxY - minY), full * 1.6);
    const pan = { x: r.x + r.w / 2 - zoom * (minX + maxX) / 2, y: r.y + r.h / 2 - zoom * (minY + maxY) / 2 };
    if (animate && !REDUCED) cy.animate({ zoom, pan }, { duration: 500, easing: 'ease-in-out-cubic' });
    else cy.viewport({ zoom, pan });
  }

  // ---- overlay: zones, labels, the Remove button, links -------------------------------------------------------------
  let syncQueued = false;
  function scheduleSync() {
    if (syncQueued) return;
    syncQueued = true;
    requestAnimationFrame(() => { syncQueued = false; sync(); });
  }

  function hull(points) {
    const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (p.length < 3) return p;
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [], upper = [];
    for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
    for (const q of p.reverse()) { while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
  }

  function softHull(points, r) {
    const ring = [];
    for (const q of points) for (let k = 0; k < 20; k++) ring.push([q[0] + Math.cos(k * Math.PI / 10) * r * 1.08, q[1] + Math.sin(k * Math.PI / 10) * r]);
    let h = hull(ring);
    for (let it = 0; it < 3; it++) {
      const next = [];
      for (let i = 0; i < h.length; i++) {
        const a = h[i], b = h[(i + 1) % h.length];
        next.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25], [a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
      }
      h = next;
    }
    return 'M' + h.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(' L') + 'Z';
  }

  function roundedHull(points, r) {
    // the hull of the node centres grown by r: straight sides joined by arcs, a soft zone around its members
    if (!points.length) return '';
    if (points.length === 1) {
      const [x, y] = points[0];
      return `M${x - r},${y} a${r},${r} 0 1,0 ${2 * r},0 a${r},${r} 0 1,0 ${-2 * r},0Z`;
    }
    const h = points.length === 2 ? points : hull(points);
    const n = h.length;
    const cx = h.reduce((a, p) => a + p[0], 0) / n, cy = h.reduce((a, p) => a + p[1], 0) / n;
    const normals = h.map((p, i) => {
      const q = h[(i + 1) % n];
      let nx = q[1] - p[1], ny = -(q[0] - p[0]);
      const len = Math.hypot(nx, ny) || 1;
      nx /= len; ny /= len;
      if (nx * ((p[0] + q[0]) / 2 - cx) + ny * ((p[1] + q[1]) / 2 - cy) < 0) { nx = -nx; ny = -ny; }
      return [nx, ny];
    });
    const f = (v) => v.toFixed(1);
    let d = '';
    for (let i = 0; i < n; i++) {
      const p = h[i], q = h[(i + 1) % n], [nx, ny] = normals[i], [mx, my] = normals[(i + 1) % n];
      if (!i) d += `M${f(p[0] + nx * r)},${f(p[1] + ny * r)}`;
      d += ` L${f(q[0] + nx * r)},${f(q[1] + ny * r)}`;
      const sweep = nx * my - ny * mx > 0 ? 1 : 0;
      d += ` A${f(r)},${f(r)} 0 0,${sweep} ${f(q[0] + mx * r)},${f(q[1] + my * r)}`;
    }
    return d + 'Z';
  }

  const zoneEls = new Map();
  const zoneAnchor = new Map();

  function syncZones() {
    const svg = $('zones');
    const z = cy.zoom();
    const pad = 58 * z;
    for (const team of model.teams) {
      const i = model.zoneOf.get(team);
      const color = C.zones[i % C.zones.length];
      const members = cy.nodes().filter((n) => placeOf(model.nodes.get(n.id())).team === team && !n.hasClass('drift'));
      let g = zoneEls.get(team);
      if (!g) {
        g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'zone');
        g.innerHTML = '<path/><text/>';
        g.querySelector('text').textContent = team;
        svg.appendChild(g);
        zoneEls.set(team, g);
      }
      const path = g.querySelector('path'), text = g.querySelector('text');
      if (!members.length) { path.setAttribute('d', ''); text.textContent = ''; continue; }
      const pts = members.map((n) => { const p = n.renderedPosition(); return [p.x, p.y]; });
      const reg = regions.get(team);
      if (reg) {  // the label sits at the top of the region: keep it inside the zone
        const pan = cy.pan();
        pts.push([pan.x + z * (reg.x0 + (reg.x1 - reg.x0) * 0.24), pan.y + z * (reg.y0 + 40)]);
      }
      path.setAttribute('d', softHull(pts, pad));
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
      const lit = g.classList.contains('lit');
      const red = g.classList.contains('red');
      const stroke = red ? C.red : lit ? C.blue : color;
      path.setAttribute('fill', color);
      path.setAttribute('fill-opacity', lit ? '0.13' : '0.075');
      path.setAttribute('stroke', stroke);
      path.setAttribute('stroke-opacity', lit || red ? '0.75' : '0.28');
      const lx = reg ? cy.pan().x + z * (reg.x0 + (reg.x1 - reg.x0) * 0.24) : minX + (maxX - minX) * 0.24;
      const ly = reg ? cy.pan().y + z * (reg.y0 + 40) : minY + 34;
      text.setAttribute('x', lx.toFixed(1));
      text.setAttribute('y', (ly + 6).toFixed(1));
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', color);
      const ring = [];
      for (const q of pts) for (let k = 0; k < 16; k++) ring.push([q[0] + Math.cos(k * Math.PI / 8) * pad, q[1] + Math.sin(k * Math.PI / 8) * pad]);
      zoneAnchor.set(team, { x: (minX + maxX) / 2, y: (minY + maxY) / 2, top: minY, edge: hull(ring) });
    }
  }

  const labelEls = new Map();

  function wantedLabels() {
    // node id -> class ('', 'red', 'green', 'dim'); persons show initials inside, the full name below when relevant
    const out = new Map();
    cy.nodes().forEach((n) => {
      let cls = null;
      if (n.hasClass('island') || n.hasClass('single')) cls = 'red';
      else if (n.hasClass('saved') || n.hasClass('succ')) cls = 'green';
      else if (n.hasClass('lit') || n.hasClass('pick')) cls = '';
      if (n.hasClass('ghost')) cls = null;
      if (cls !== null) out.set(n.id(), cls);
    });
    return out;
  }

  function syncLabels() {
    const box = $('labels');
    const want = wantedLabels();
    for (const [id, el] of labelEls) {
      if (!want.has(id)) { el.remove(); labelEls.delete(id); }
    }
    const z = cy.zoom();
    for (const [id, cls] of want) {
      const n = cy.getElementById(id);
      let el = labelEls.get(id);
      if (!el) {
        el = document.createElement('div');
        el.textContent = id;
        box.appendChild(el);
        labelEls.set(id, el);
      }
      el.className = 'nlabel' + (cls ? ' ' + cls : '');
      const p = n.renderedPosition();
      el.style.left = `${p.x}px`;
      el.style.top = `${p.y + (n.height() / 2) * z + 8 + (n.hasClass('pick') ? 6 : 0)}px`;
    }
  }

  function syncPicked() {
    // below the name as in the frames; beside or above the person when a node sits there
    const box = $('picked');
    if (box.hidden || !state.person) return;
    const n = cy.getElementById(state.person);
    const p = n.renderedPosition(), r = (n.height() / 2) * cy.zoom();
    const bw = box.offsetWidth || 90, bh = box.offsetHeight || 28;
    const spots = [[p.x, p.y + r + 46], [p.x + r + 16 + bw / 2, p.y - bh / 2], [p.x - r - 16 - bw / 2, p.y - bh / 2], [p.x, p.y - r - bh - 12]];
    const others = cy.nodes().not(n).map((m) => m.renderedBoundingBox());
    const clear = ([x, y]) => others.every((b) => x + bw / 2 < b.x1 - 2 || x - bw / 2 > b.x2 + 2 || y + bh < b.y1 - 2 || y > b.y2 + 2);
    const [x, y] = spots.find(clear) || spots[0];
    box.style.left = `${x}px`;
    box.style.top = `${y}px`;
  }

  function sync() {
    if (!cy) return;
    syncZones();
    syncLabels();
    syncPicked();
    syncLinks();
  }

  // links drawn in the overlay: the bridge a person was the only one to hold, and the card-to-node line of the game
  const links = { bridges: [], card: null };

  function syncLinks() {
    const svg = $('overlay');
    let html = '';
    for (const [a, b] of links.bridges) {
      const za = zoneAnchor.get(a), zb = zoneAnchor.get(b);
      if (!za || !zb) continue;
      const near = (z, t) => z.edge.reduce((m, q) => (Math.hypot(q[0] - t.x, q[1] - t.y) < Math.hypot(m[0] - t.x, m[1] - t.y) ? q : m), z.edge[0]);
      const p = near(za, zb), q = near(zb, za);
      const mx = (p[0] + q[0]) / 2, my = (p[1] + q[1]) / 2;
      const ux = (q[0] - p[0]) / (Math.hypot(q[0] - p[0], q[1] - p[1]) || 1), uy = (q[1] - p[1]) / (Math.hypot(q[0] - p[0], q[1] - p[1]) || 1);
      const g = 14;
      html += `<path d="M${p[0]},${p[1]} L${mx - ux * g},${my - uy * g} M${mx + ux * g},${my + uy * g} L${q[0]},${q[1]}" fill="none" stroke="${C.red}" stroke-width="2.2" stroke-dasharray="7 6" stroke-opacity="0.85"/>`
        + `<circle cx="${p[0]}" cy="${p[1]}" r="4.5" fill="${C.red}"/><circle cx="${q[0]}" cy="${q[1]}" r="4.5" fill="${C.red}"/>`
        + `<path d="M${mx - uy * 9 - ux * 4},${my + ux * 9 - uy * 4} L${mx + uy * 9 - ux * 4},${my - ux * 9 - uy * 4} M${mx - uy * 9 + ux * 4},${my + ux * 9 + uy * 4} L${mx + uy * 9 + ux * 4},${my - ux * 9 + uy * 4}" stroke="${C.red}" stroke-width="2.2" stroke-linecap="round"/>`;
    }
    if (links.card) {
      const card = links.card.el.getBoundingClientRect();
      const host = app.getBoundingClientRect();
      const n = cy.getElementById(links.card.node);
      if (card.width && n.length) {
        const p = n.renderedPosition();
        const x1 = card.left - host.left, y1 = card.top - host.top + card.height / 2;
        const r = (n.width() / 2) * cy.zoom() + 6;
        const x2 = p.x + r, y2 = p.y;
        const dx = Math.max(60, (x1 - x2) * 0.5);
        html += `<path class="draw" d="M${x2},${y2} C${x2 + dx},${y2} ${x1 - dx},${y1} ${x1},${y1}" fill="none" stroke="${C.green}" stroke-width="2.5"/>`
          + `<circle cx="${x2}" cy="${y2}" r="5" fill="${C.green}"/><circle cx="${x1}" cy="${y1}" r="5" fill="${C.green}"/>`;
      }
    }
    svg.innerHTML = html;
  }

  // ---- tooltip ------------------------------------------------------------------------------------------------------
  const hoverInfo = new Map();  // element id -> extra lines for the current state

  function describeNode(id) {
    const n = model.nodes.get(id);
    if (!n) return '';
    const lines = [];
    const team = n.team ? ` <span class="k">· ${esc(n.team)}</span>` : '';
    if (n.kind === 'person') {
      lines.push(`<div><b>${esc(id)}</b>${team}</div>`);
      const leave = model.leaving.get(id);
      if (leave) lines.push(`<div class="k">Resigned ${esc(day(leave.notice_at))}, last day ${esc(leave.last_day)} <span class="ids">${esc(leave.notice_source || '')}</span></div>`);
    } else if (n.kind === 'system') {
      const kind = n.system_kind && n.system_kind !== 'service' ? ` <span class="k">${esc(n.system_kind)}</span>` : '';
      lines.push(`<div><b>${esc(id)}</b>${kind}${team}</div>`);
      if (n.purpose) lines.push(`<div class="k">${esc(n.purpose)}</div>`);
    } else if (n.kind === 'decision') {
      lines.push(`<div><b>${esc(id)}</b> <span class="k">${esc(n.status || '')}</span></div>`);
      if (n.title) lines.push(`<div class="k">${esc(n.title)}</div>`);
    } else if (n.kind === 'project') {
      lines.push(`<div><b>${esc(id)}</b> <span class="k">project</span>${team}</div>`);
      if (n.goal) lines.push(`<div class="k">${esc(n.goal)}</div>`);
    }
    return lines.join('');
  }

  function describeEdge(id) {
    const [type, source, target] = id.split('|');
    const e = model.edges.find((x) => edgeId(x) === id);
    if (!e) return '';
    const ids = e.source_ids.slice(0, 5).join(', ') + (e.source_ids.length > 5 ? ` +${e.source_ids.length - 5}` : '');
    const ended = e.ended ? `<div class="k">ended ${esc(day(e.until))} <span class="ids">${esc((e.ended_by || []).join(', '))}</span></div>` : '';
    return `<div><b>${esc(source)}</b> <span class="k">${esc(type)}</span> <b>${esc(target)}</b></div>`
      + `<div class="k">since ${esc(day(e.since))}${e.count ? ` · ${e.count} records` : ''}</div>`
      + (ids ? `<div class="ids">${esc(ids)}</div>` : '') + ended;
  }

  function showTip(ele, ev) {
    const id = ele.id();
    const base = ele.isNode() ? describeNode(id) : describeEdge(id);
    const extra = hoverInfo.get(id) || '';
    if (!base && !extra) return;
    const tip = $('tip');
    tip.innerHTML = base + extra;
    tip.hidden = false;
    moveTip(ev);
  }

  function moveTip(ev) {
    const tip = $('tip');
    if (tip.hidden || !ev) return;
    const x = ev.clientX, y = ev.clientY;
    const r = tip.getBoundingClientRect();
    tip.style.left = `${Math.min(x + 14, innerWidth - r.width - 8)}px`;
    tip.style.top = `${y + 18 + r.height > innerHeight ? y - r.height - 12 : y + 18}px`;
  }

  function hideTip() { $('tip').hidden = true; }

  function htmlTip(target, html) {
    target.addEventListener('mouseenter', (ev) => { const tip = $('tip'); tip.innerHTML = html(); tip.hidden = false; moveTip(ev); });
    target.addEventListener('mousemove', moveTip);
    target.addEventListener('mouseleave', hideTip);
  }

  // ---- Show Cypher --------------------------------------------------------------------------------------------------
  let lastAction = { title: 'Loading the company graph', calls: [] };

  function record(title, calls) {
    lastAction = { title, calls };
    if (!$('cypher').hidden) renderCypher();
  }

  function renderCypher() {
    $('cypher-title').textContent = lastAction.title;
    const body = $('cypher-body');
    if (!lastAction.calls.length) { body.innerHTML = '<p class="call none">No query yet.</p>'; return; }
    body.innerHTML = lastAction.calls.map((c) => {
      const head = `<h3>${esc(c.name)}<small>${esc(c.meta)}</small></h3>`;
      const qs = c.queries.map((q) => `<pre>${q.ms !== undefined ? `<span class="ms">${esc(q.ms)} ms</span>` : ''}${esc(q.text)}</pre>`).join('');
      return `<div class="call">${head}${qs || '<p class="none">No query ran.</p>'}</div>`;
    }).join('');
  }

  function toolCall(name, args, res) {
    const a = res.body;
    const tr = (a.trace || [])[0] || {};
    const argText = Object.entries(args).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ');
    const meta = [tr.ms !== undefined ? `${tr.ms} ms in FalkorDB` : null, `${(a.rows || []).length} rows`,
      a.outcome, res.roundtrip !== null && res.roundtrip !== undefined ? `${res.roundtrip} ms round trip` : 'recorded'].filter(Boolean).join(' · ');
    return { name: `${name}(${argText})`, meta, queries: (a.trace || []).flatMap((t) => (t.queries || []).map((q) => ({ text: q }))) };
  }

  // ---- state --------------------------------------------------------------------------------------------------------
  const state = { phase: 'loading', person: null, depth: 1, shown: 0, seq: 0, lit: null, removed: null, game: null };

  function setPhase(p) { state.phase = p; app.dataset.phase = p; }

  function clearClasses() {
    cy.elements().removeClass('faded lit tail pick fwd back ghost island single saved succ snap snap-s snap-t weak after');
    cy.edges('.handover').remove();
    $('zones').querySelectorAll('.zone').forEach((g) => g.classList.remove('lit', 'red'));
    hoverInfo.clear();
    links.bridges = [];
    links.card = null;
  }

  function show(id, on) { $(id).hidden = !on; }

  function toLanding(animate = true) {
    state.seq++;
    state.person = null; state.lit = null; state.removed = null; state.game = null;
    clearClasses();
    cy.nodes().forEach((n) => {
      const h = model.home.get(n.id());
      n.removeClass('drift');
      if (animate && !REDUCED) n.animate({ position: h }, { duration: 600, easing: 'ease-in-out-cubic' });
      else n.position(h);
    });
    setPhase('landing');
    $('headline').textContent = 'Pick someone. See what leaves with them.';
    for (const id of ['headline']) show(id, true);
    for (const id of ['counters', 'picked', 'depth', 'actions', 'game', 'handoff', 'promise', 'restart']) show(id, false);
    fit(animate);
    scheduleSync();
  }

  // ---- 1-2. pick a person, walk the depth -------------------------------------------------------------------------
  async function pick(person) {
    if (state.phase !== 'landing' && state.phase !== 'picked') { toLanding(false); }
    state.person = person; state.depth = 1; state.shown = 0; state.lit = null;
    setPhase('picked');
    clearClasses();
    cy.elements().addClass('faded');
    cy.getElementById(person).removeClass('faded').addClass('pick');
    show('picked', true); show('depth', true);
    $('cap-1').textContent = `what ${first(person)} owns`;
    $('cap-4').textContent = `what depends on ${first(person)}`;
    setSlider(1);
    $('slider').classList.remove('hint');
    scheduleSync();
    await setDepth(1);
    if (state.person === person && state.depth === 1) $('slider').classList.add('hint');
  }

  function segmentsOf(answer, person) {
    // one entry per hop of every path: [from, edge type, to] with its step along the path and whether it is the tail
    const rows = (answer.rows || []).filter((r) => r.kind !== 'summary');
    const out = [];
    (answer.paths || []).forEach((path, i) => {
      const row = rows[i] || {};
      if (path[0] !== person) return;
      for (let k = 1; 2 * k < path.length; k++) {
        out.push({ a: path[2 * k - 2], rel: path[2 * k - 1], b: path[2 * k], step: k, tail: row.hops ? k > row.hops : false, row });
      }
    });
    return out;
  }

  function resolveSegment(s) {
    // the drawn edge for one hop, and the direction it is walked in; a team is a zone, not an edge
    const back = s.rel.startsWith('<-');
    const type = back ? s.rel.slice(2) : s.rel;
    const [from, to] = back ? [s.b, s.a] : [s.a, s.b];
    if (model.nodes.get(to)?.kind === 'team' && (type === 'MEMBER_OF' || type === 'LEADS' || type === 'WAS')) return { zone: to };
    let e = cy.getElementById(`${type}|${from}|${to}`);
    if (!e.length && type === 'WAS') {
      e = cy.edges().filter((x) => x.source().id() === from && x.target().id() === to);
    }
    if (!e.length) return null;
    return { edge: e[0], dir: back ? 'back' : 'fwd' };
  }

  function rowNote(row) {
    if (!row) return '';
    const ids = (row.source_ids || []).slice(0, 5);
    const what = row.why || (row.relation ? `${row.relation.toLowerCase()} ${row.item}${row.state === 'ended' ? ` (ended ${day(row.until)})` : ''}` : '');
    return `<div class="k">${esc(what)}${row.hops ? ` · ${row.hops} ${plural(row.hops, 'hop', 'hops')}` : ''}</div>`
      + (ids.length ? `<div class="ids">${esc(ids.join(', '))}</div>` : '');
  }

  async function setDepth(d) {
    const person = state.person;
    const my = ++state.seq;
    state.depth = d;
    setSlider(d);
    let res;
    try { res = await api.tool('what_leaves', { person, depth: d }); } catch (err) { setStatus(err.message); return; }
    if (my !== state.seq || state.person !== person) return;
    record(`what_leaves(${person}, depth ${d})`, [toolCall('what_leaves', { person, depth: d }, res)]);
    applyDepth(res.body, person, d);
  }

  function applyDepth(answer, person, d) {
    const prev = state.shown;
    const want = new Map();     // element id -> {ele, cls, dir, delay}
    const zones = new Set();
    const notes = new Map();
    for (const s of segmentsOf(answer, person)) {
      const r = resolveSegment(s);
      if (!r) continue;
      const delay = Math.max(0, s.step - prev - 1) * STEP_MS;
      const note = rowNote(s.row);
      if (r.zone) { zones.add(r.zone); continue; }
      const cls = s.tail ? 'tail' : 'lit';
      const prevE = want.get(r.edge.id());
      if (!prevE || (prevE.cls === 'tail' && cls === 'lit')) want.set(r.edge.id(), { ele: r.edge, cls, dir: r.dir, delay });
      const end = r.dir === 'fwd' ? r.edge.target() : r.edge.source();
      const pn = want.get(end.id());
      if (end.id() !== person && (!pn || (pn.cls === 'tail' && cls === 'lit'))) want.set(end.id(), { ele: end, cls, delay: delay + 60 });
      for (const id of [r.edge.id(), end.id()]) {
        if (!notes.has(id)) notes.set(id, new Set());
        notes.get(id).add(note);
      }
    }
    // drop what is no longer lit
    cy.elements('.lit, .tail').forEach((ele) => {
      const w = want.get(ele.id());
      if (!w || !ele.hasClass(w.cls)) ele.removeClass('lit tail fwd back').addClass('faded');
    });
    hoverInfo.clear();
    for (const [id, set] of notes) hoverInfo.set(id, [...set].slice(0, 3).join(''));
    const summary = (answer.rows || [])[0];
    if (answer.outcome !== 'answered_with_path') hoverInfo.set(person, `<div class="k">${esc(answer.note || answer.sentence || '')}</div>`);
    else if (summary) hoverInfo.set(person, `<div class="k">${esc(answer.sentence || '')}</div>`);
    for (const w of want.values()) {
      const apply = () => {
        if (state.person !== person || state.phase !== 'picked') return;
        w.ele.removeClass('faded lit tail fwd back').addClass(w.cls);
        if (w.dir) w.ele.addClass(w.dir);
        scheduleSync();
      };
      if (w.delay && !REDUCED) setTimeout(apply, w.delay); else apply();
    }
    $('zones').querySelectorAll('.zone').forEach((g) => g.classList.toggle('lit', zones.has(g.querySelector('text').textContent)));
    state.shown = d;
    scheduleSync();
  }

  // the depth slider: four stops, click, drag or arrow keys
  function setSlider(d) {
    const s = $('slider');
    s.setAttribute('aria-valuenow', String(d));
    s.querySelectorAll('.stop').forEach((b) => {
      const v = Number(b.dataset.d);
      b.classList.toggle('on', v <= d);
      b.classList.toggle('cur', v === d);
    });
    s.querySelector('.fill').style.width = `${((d - 1) / 3) * 100}%`;
  }

  function initSlider() {
    const s = $('slider');
    s.querySelectorAll('.stop').forEach((b, i) => { b.style.left = `${(i / 3) * 100}%`; });
    const at = (x) => {
      const r = s.getBoundingClientRect();
      return Math.max(1, Math.min(4, Math.round(((x - r.left) / r.width) * 3) + 1));
    };
    let dragging = false;
    const go = (d) => { s.classList.remove('hint'); if (d !== state.depth && state.phase === 'picked') setDepth(d); };
    s.addEventListener('pointerdown', (ev) => { dragging = true; s.setPointerCapture(ev.pointerId); go(at(ev.clientX)); });
    s.addEventListener('pointermove', (ev) => { if (dragging) go(at(ev.clientX)); });
    s.addEventListener('pointerup', () => { dragging = false; });
    s.addEventListener('pointercancel', () => { dragging = false; });
    s.addEventListener('keydown', (ev) => {
      const k = ev.key;
      if (k === 'ArrowRight' || k === 'ArrowUp') { go(Math.min(4, state.depth + 1)); ev.preventDefault(); }
      if (k === 'ArrowLeft' || k === 'ArrowDown') { go(Math.max(1, state.depth - 1)); ev.preventDefault(); }
      if (k === 'Home') go(1);
      if (k === 'End') go(4);
    });
  }

  // ---- 3. Remove ----------------------------------------------------------------------------------------------------
  function asOfFor(person, tool) {
    const leave = model.leaving.get(person);
    return leave && leave.notice_at && api.accepts(tool, 'as_of') ? day(leave.notice_at) : null;
  }

  function withAsOf(tool, args) {
    const asOf = asOfFor(args.person, tool);
    return asOf ? { ...args, as_of: asOf } : args;
  }

  async function remove() {
    const person = state.person;
    if (!person) return;
    const my = ++state.seq;
    setPhase('removing');
    show('picked', false); show('depth', false);
    const calls = [['without', withAsOf('without', { person })], ['single_source', withAsOf('single_source', { person })], ['bridges', { top: 3 }]];
    let results;
    try { results = await Promise.all(calls.map(([n, a]) => api.tool(n, a))); } catch (err) {
      setStatus(err.message); setPhase('picked'); show('picked', true); show('depth', true); return;
    }
    if (my !== state.seq) return;
    record(`Remove ${person}`, calls.map(([n, a], i) => toolCall(n, a, results[i])));
    const [wo, ss, br] = results.map((r) => r.body);
    const islands = (wo.rows || []).filter((r) => r.kind === 'island');
    const islandItems = islands.flatMap((i) => i.items.map((item) => ({ item, kind: i.kinds?.[item], through: i.connected_through || [] })));
    const singles = (ss.rows || []).filter((r) => r.kind !== 'summary' && r.single_source);
    const singleDecisions = singles.filter((r) => r.item_kind === 'decision');
    const onlyLinks = (br.rows || []).filter((r) => r.kind === 'only_link' && r.person === person).map((r) => r.teams);
    const summary = (wo.rows || []).find((r) => r.kind === 'summary') || {};
    state.removed = { person, wo, ss, br, islandItems, singles, singleDecisions, onlyLinks, summary };

    setPhase('removed');
    clearClasses();
    const me = cy.getElementById(person);
    me.addClass('ghost');
    me.connectedEdges().forEach((e) => e.addClass('snap ' + (e.source().id() === person ? 'snap-s' : 'snap-t')
      + (e.data('type') === 'WORKED_ON' ? ' weak' : '')));
    cy.elements().not(me).not(me.connectedEdges()).addClass('faded');

    // islands drift away from the person, staying inside the drawing, and glow red
    const homes = [...model.home.values()];
    const box = { x0: Math.min(...homes.map((q) => q.x)) - 30, x1: Math.max(...homes.map((q) => q.x)) + 30,
      y0: Math.min(...homes.map((q) => q.y)) + 20, y1: Math.max(...homes.map((q) => q.y)) - 10 };
    const taken = [];
    for (const it of islandItems) {
      const n = cy.getElementById(it.item);
      if (!n.length) continue;
      n.removeClass('faded').addClass('island drift');
      const to = driftSpot(it.item, person, box, taken);
      taken.push(to);
      if (REDUCED) n.position(to); else n.animate({ position: to }, { duration: 900, easing: 'ease-out-cubic' });
      const through = it.through.map((c) => `${c.relation}${c.state === 'ended' ? ' (ended)' : ''}${c.count ? `, ${c.count} records` : ''}`).join('; ');
      hoverInfo.set(it.item, `<div class="red">Without ${esc(first(person))}, nobody in the graph is connected to it.</div>`
        + (through ? `<div class="k">Connected only through ${esc(person)}: ${esc(through)}</div>` : '')
        + `<div class="ids">${esc(it.through.flatMap((c) => c.source_ids || []).slice(0, 6).join(', '))}</div>`);
    }
    for (const r of singles) {
      const n = cy.getElementById(r.item);
      if (!n.length || n.hasClass('island')) continue;
      if (r.item_kind === 'decision') n.removeClass('faded').addClass('single');
      hoverInfo.set(r.item, `<div class="red">Every record behind it was written by ${esc(person)}.</div>`
        + (r.title ? `<div class="k">${esc(r.title)}</div>` : '') + `<div class="ids">${esc((r.episodes || []).slice(0, 6).join(', '))}</div>`);
    }
    links.bridges = onlyLinks;
    $('zones').querySelectorAll('.zone').forEach((g) => g.classList.toggle('red', onlyLinks.some((p) => p.includes(g.querySelector('text').textContent))));

    // counters
    const allSystems = islandItems.every((i) => !i.kind || i.kind === 'system');
    setCounter('islands', islandItems.length, allSystems ? plural(islandItems.length, 'system nobody is connected to', 'systems nobody is connected to')
      : plural(islandItems.length, 'item nobody is connected to', 'items nobody is connected to'));
    setCounter('decisions', singleDecisions.length, `${plural(singleDecisions.length, 'decision', 'decisions')} only ${first(person)} wrote`);
    setCounter('bridges', onlyLinks.length, `${plural(onlyLinks.length, 'bridge', 'bridges')} between teams lost`);
    counterTips(person);
    $('wall').textContent = summary.wall_ms !== undefined ? `measured ${summary.wall_ms} ms` : '';
    show('headline', false); show('counters', true); show('actions', true);
    $('plan').focus({ preventScroll: true });
    scheduleSync();
  }

  function driftSpot(item, person, box, taken) {
    // away from the person, inside the drawing, and clear of every other node: the first free spot on a widening fan
    const h = model.home.get(item), from = model.home.get(person);
    const base = Math.atan2(h.y - from.y, h.x - from.x);
    const others = [...model.home.entries()].filter(([id]) => id !== item).map(([, q]) => q).concat(taken);
    let best = null, bestGap = -1;
    for (const dist of [170, 210, 250, 130]) {
      for (const turn of [0, 0.35, -0.35, 0.7, -0.7, 1.1, -1.1]) {
        const a = base + turn;
        const q = { x: Math.max(box.x0, Math.min(box.x1, h.x + Math.cos(a) * dist)), y: Math.max(box.y0, Math.min(box.y1, h.y + Math.sin(a) * dist * 0.75)) };
        const gap = Math.min(...others.map((o) => Math.hypot(o.x - q.x, o.y - q.y)));
        if (gap >= 80) return q;
        if (gap > bestGap) { best = q; bestGap = gap; }
      }
    }
    return best;
  }

  function setCounter(k, n, label) {
    const el = app.querySelector(`.counter[data-k="${k}"]`);
    el.classList.toggle('zero', n === 0);
    el.classList.remove('good');
    el.querySelector('span').textContent = label;
    const b = el.querySelector('b');
    const from = Number(b.textContent) || 0;
    if (REDUCED || from === n) { b.textContent = String(n); return; }
    const t0 = performance.now();
    const tick = (t) => {
      const f = Math.min(1, (t - t0) / 600);
      b.textContent = String(Math.round(from + (n - from) * (1 - Math.pow(1 - f, 3))));
      if (f < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function counterTips(person) {
    const r = state.removed;
    const isl = r.islandItems.map((i) => i.item).join(', ') || 'none';
    const dec = r.singleDecisions.map((d) => d.item).join(', ') || 'none';
    const br = r.onlyLinks.map((p) => p.join(' and ')).join('; ') || 'none';
    tips.islands = () => `<div>Islands without ${esc(person)}: <b>${esc(isl)}</b></div><div class="k">algo.WCC on a temporary copy of the graph without them`
      + `${r.summary.nodes ? `: ${r.summary.nodes} nodes, ${r.summary.links} links, ${r.summary.components} components` : ''}.</div>`;
    tips.decisions = () => `<div>Live decisions where every source record was written by ${esc(person)}: <b>${esc(dec)}</b></div>`;
    tips.bridges = () => `<div>Teams only ${esc(person)} links: <b>${esc(br)}</b></div><div class="k">algo.betweenness over people, teams and systems.</div>`;
    tips.wall = () => `<div class="k">Wall time of without(): projection, algo.WCC and cleanup on FalkorDB.</div>`;
  }

  const tips = {};

  // ---- 5. the handoff game ------------------------------------------------------------------------------------------
  // Cards: one per item that rested only on the person's records before any handoff (single_source as of their
  // notice day), plus the plan's other open questions. The question text is the plan's own while it is still open;
  // for an item the handoff already answered, the plan no longer asks it, so the same question is put from the same
  // facts (what the decision governs and who owns that). Answering reveals what the graph holds: the CONFIRM receipts
  // about the item since the notice, the records they cite, and single_source as of the day of those records.

  function governsText(item) {
    const owner = new Map(model.edges.filter((e) => e.type === 'OWNS').map((e) => [e.target, e.source]));
    const sys = model.edges.filter((e) => e.type === 'CONSTRAINS' && e.source === item).map((e) => e.target);
    return sys.map((s) => (owner.get(s) ? `${s} (owner ${owner.get(s)})` : s)).join(', ') || 'the systems it governs';
  }

  function cardsFor(person, before, planA) {
    const questions = (planA.rows || []).filter((r) => r.kind === 'question');
    const open = new Map(questions.filter((q) => q.status === 'open').map((q) => [q.item, q]));
    const single = (before.rows || []).filter((r) => r.kind !== 'summary' && r.single_source);
    const cards = single.map((r) => ({
      item: r.item, item_kind: r.item_kind, title: r.title,
      question: open.get(r.item)?.question || (r.item_kind === 'decision'
        ? `Why was ${r.item} decided, and what breaks in ${governsText(r.item)} if it is undone?`
        : `How is ${r.item} run day to day, and where are the steps written down?`),
      from: open.has(r.item) ? 'handoff_plan' : 'single_source', why: open.get(r.item)?.why || `Every record behind ${r.item} was written by ${person}.`,
      sources: r.episodes || [],
    }));
    for (const q of questions) {
      if (q.item_kind === 'gap' || cards.some((c) => c.item === q.item)) continue;  // the phone question is the pill
      cards.push({ item: q.item, item_kind: q.item_kind, question: q.question, from: 'handoff_plan', why: q.why, sources: q.sources_so_far || [] });
    }
    const order = { system: 0, decision: 1 };
    return cards.sort((a, b) => (order[a.item_kind] ?? 2) - (order[b.item_kind] ?? 2) || a.item.localeCompare(b.item));
  }

  async function plan() {
    const person = state.person;
    const my = ++state.seq;
    const leave = model.leaving.get(person);
    const before = state.removed.ss;
    const calls = [['handoff_plan', { person }], ['promises', { person }]];
    let results;
    try { results = await Promise.all(calls.map(([n, a]) => api.tool(n, a))); } catch (err) { setStatus(err.message); return; }
    if (my !== state.seq) return;
    record(`Plan the handoff for ${person}`, calls.map(([n, a], i) => toolCall(n, a, results[i])));
    const planA = results[0].body, promisesA = results[1].body;
    const cards = cardsFor(person, before, planA);
    const total = leave && leave.last_day && leave.notice_at ? daysBetween(day(leave.notice_at), leave.last_day) : ASSUMED_NOTICE_DAYS;
    state.game = { person, cards, plan: planA, promises: promisesA, before, days: total, total, saved: 0,
      answered: new Set(), assumed: !(leave && leave.last_day), resolved: new Map(), notice: leave?.notice_at || null };
    setPhase('game');
    show('counters', false); show('actions', false);
    $('headline').textContent = `Ask before ${first(person)} leaves.`;
    show('headline', true);
    show('game', true);
    $('cards').innerHTML = '';
    $('saved-of').textContent = String(cards.length);
    renderGame();
    for (const c of cards) {
      const n = cy.getElementById(c.item);
      if (n.length && !n.hasClass('island') && !n.hasClass('single')) n.removeClass('faded').addClass('single');
    }
    state.focus = [person, ...cards.map((c) => c.item)].filter((id) => cy.getElementById(id).length);
    fit(true, state.focus);
    scheduleSync();
    if (!cards.length) { await sleep(ms(900)); if (state.game && state.game.person === person) finish(); }
  }

  function renderGame() {
    const g = state.game;
    $('days').textContent = String(g.days);
    $('days').parentElement.lastChild.textContent = ` ${plural(g.days, 'day', 'days')} left`;
    $('days').parentElement.classList.toggle('low', g.days < DAYS_PER_ANSWER);
    $('saved-n').textContent = String(g.saved);
    $('bar-fill').style.width = g.cards.length ? `${(g.saved / g.cards.length) * 100}%` : '0';
    const box = $('cards');
    if (!box.children.length) {
      if (!g.cards.length) {
        box.innerHTML = `<div class="card empty">Nothing rests only on ${esc(first(g.person))}'s records: no question to ask.</div>`;
      }
      g.cards.forEach((c, i) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'card';
        b.dataset.i = String(i);
        b.innerHTML = `<span class="q">${esc(c.question)}</span>`;
        b.addEventListener('click', () => answer(i, b));
        htmlTip(b, () => `<div><b>${esc(c.item)}</b> <span class="k">${esc(c.item_kind)}${c.title ? ' · ' + esc(c.title) : ''}</span></div>`
          + `<div class="k">${esc(c.why || '')}</div><div class="ids">${esc((c.sources || []).slice(0, 6).join(', '))}</div>`
          + (g.assumed ? `<div class="k">No last day is recorded for ${esc(g.person)}: two weeks assumed.</div>` : '')
          + `<div class="k">Each answer costs ${DAYS_PER_ANSWER} days.</div>`);
        box.appendChild(b);
      });
    }
    box.querySelectorAll('.card[data-i]').forEach((b) => {
      const i = Number(b.dataset.i);
      if (!g.answered.has(i) && g.days < DAYS_PER_ANSWER) { b.classList.add('lost'); b.disabled = true; }
    });
  }

  function linesAbout(text, item) {
    const re = new RegExp(`(^|[^\\w-])${item.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^\\w-]|$)`);
    return String(text || '').split('\n').map((s) => s.replace(/^[-*]\s*/, '').trim()).filter((s) => s && re.test(s));
  }

  async function writtenAnswer(item, g) {
    // CONFIRM receipts about the item since the notice, the records they cite, and the item's state as of then
    if (!g.notice) return null;
    const rec = await api.confirmReceipts();
    const receipts = (rec.body.receipts || []).filter((r) => r.outcome === 'CONFIRM' && r.ts > g.notice
      && (r.subject === item || r.object === item));
    if (!receipts.length) return { receipts: [], episodes: [], after: null };
    const ids = [...new Set(receipts.flatMap((r) => r.cites || []))].slice(0, 6);
    const episodes = (await Promise.all(ids.map((id) => api.episode(id)))).map((r) => r.body).filter((e) => e.ts > g.notice);
    if (!episodes.length) return { receipts: [], episodes: [], after: null };
    const asOf = episodes.map((e) => day(e.ts)).sort().pop();
    const args = { person: g.person, as_of: asOf };
    const res = await api.tool('single_source', args);
    record(`Answer about ${item}`, [
      { name: 'GET /receipts?outcome=confirm', meta: `${receipts.length} about ${item} since ${day(g.notice)}`, queries: [] },
      toolCall('single_source', args, res)]);
    const row = (res.body.rows || []).find((r) => r.item === item && r.kind !== 'summary');
    return { receipts, episodes, after: row || null, asOf };
  }

  async function answer(i, card) {
    const g = state.game;
    if (!g || g.answered.has(i) || g.days < DAYS_PER_ANSWER) return;
    const c = g.cards[i];
    g.answered.add(i);
    g.days -= DAYS_PER_ANSWER;
    card.disabled = true;
    renderGame();
    let found = null;
    try { found = await writtenAnswer(c.item, g); } catch (err) { setStatus(err.message); }
    if (state.game !== g) return;
    const node = cy.getElementById(c.item);
    if (found && found.receipts.length) {
      const mine = found.episodes.filter((e) => e.author === g.person);
      const others = found.episodes.filter((e) => e.author !== g.person);
      const said = mine.flatMap((e) => linesAbout(e.text, c.item).map((l) => ({ l, e })))[0];
      const confirmed = others.filter((e) => linesAbout(e.text, c.item).length);
      const done = found.after && !found.after.single_source;
      const ids = found.receipts.map((r) => r.id);
      const chips = `<span class="receipt" title="${esc(found.receipts.map((r) => `${r.id}: ${r.subject} ${r.predicate} ${r.object}, cites ${r.cites.join(', ')}`).join('\n'))}">`
        + `${esc(found.receipts[0].outcome)} ${esc(ids[0])}${ids.length > 1 ? ` +${ids.length - 1}` : ''}</span>`;
      const short = (t) => (t.length > 150 ? t.slice(0, 147).replace(/\s+\S*$/, '') + '…' : t);
      card.classList.add(done ? 'saved' : 'half');
      card.insertAdjacentHTML('beforeend',
        (said ? `<span class="answer"><q>${esc(short(said.l))}</q> <span class="by">${esc(said.e.id)}, ${esc(day(said.e.ts))}</span></span>` : '')
        + (confirmed.length ? `<span class="answer by">Confirmed by ${esc(confirmed.map((e) => `${e.author} (${e.id})`).join(', '))}.</span>`
          : `<span class="answer by">Written down, but only by ${esc(first(g.person))}: it still rests on one person.</span>`)
        + chips);
      if (done) {
        g.saved++;
        g.resolved.set(c.item, { by: [...new Set(confirmed.map((e) => e.author))], episodes: found.episodes.map((e) => e.id), confirmIn: confirmed.map((e) => e.id) });
        if (node.length) node.removeClass('island single faded').addClass('saved');
        hoverInfo.set(c.item, `<div class="green">As of ${esc(found.asOf)}, records by ${esc((found.after.authors || []).join(', '))}</div>`
          + `<div class="ids">${esc((found.after.episodes || []).join(', '))}</div>`);
        links.card = { el: card, node: c.item };
      } else {
        links.card = null;
        hoverInfo.set(c.item, `<div class="red">As of ${esc(found.asOf)}, every record behind it is still by ${esc(g.person)}.</div>`
          + `<div class="ids">${esc((found.after?.episodes || []).join(', '))}</div>`);
      }
    } else {
      card.classList.add('empty');
      card.insertAdjacentHTML('beforeend', `<span class="answer">Not in the graph: no written answer from ${esc(first(g.person))} about ${esc(c.item)}${g.notice ? ` since ${esc(day(g.notice))}` : ''}.</span>`);
      links.card = null;
    }
    renderGame();
    card.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
    $('cards').addEventListener('scroll', scheduleSync, { once: true });
    setTimeout(scheduleSync, ms(400));
    scheduleSync();
    const left = g.cards.some((_, k) => !g.answered.has(k)) && g.days >= DAYS_PER_ANSWER;
    if (!left) { await sleep(ms(1600)); if (state.game === g) finish(); }
  }

  // ---- end state ----------------------------------------------------------------------------------------------------
  function finish() {
    const g = state.game;
    const r = state.removed;
    setPhase('done');
    show('game', false); show('headline', false); show('restart', true);
    links.card = null;
    // counters after the answers: an item counts as handed over only if the graph says it no longer rests on them
    const decisionsLeft = r.singleDecisions.filter((d) => !g.resolved.has(d.item)).length;
    const islandsLeft = r.islandItems.filter((it) => !g.resolved.has(it.item)).length;
    setCounter('islands', islandsLeft, app.querySelector('.counter[data-k="islands"] span').textContent);
    setCounter('decisions', decisionsLeft, app.querySelector('.counter[data-k="decisions"] span').textContent);
    setCounter('bridges', r.onlyLinks.length, app.querySelector('.counter[data-k="bridges"] span').textContent);
    for (const [k, n, was] of [['islands', islandsLeft, r.islandItems.length], ['decisions', decisionsLeft, r.singleDecisions.length]]) {
      app.querySelector(`.counter[data-k="${k}"]`).classList.toggle('good', n === 0 && was > 0);
    }
    show('counters', true);
    cy.edges('.snap').addClass('after');

    for (const it of r.islandItems) {
      if (!g.resolved.has(it.item)) continue;
      const n = cy.getElementById(it.item);
      n.removeClass('island drift').addClass('saved');
      if (REDUCED) n.position(model.home.get(it.item)); else n.animate({ position: model.home.get(it.item) }, { duration: 800, easing: 'ease-in-out-cubic' });
    }
    // who takes what: the person who confirmed in writing, else the plan's first candidate (a proposal)
    const lines = new Map(((g.plan.rows || []).filter((x) => x.kind === 'line')).map((x) => [x.item, x]));
    const items = [...new Set([...g.cards.map((c) => c.item), ...lines.keys()])];
    const rows = [];
    for (const item of items) {
      const res = g.resolved.get(item);
      const to = res && res.by.length ? res.by[0] : (lines.get(item)?.candidates || [])[0];
      const how = res && res.by.length ? `confirmed in ${res.confirmIn.join(', ')}` : to ? 'candidate (proposed)' : '';
      rows.push(`<div class="hrow"><span>${esc(item)}</span><span class="arrow">&rarr;</span>`
        + `<span class="to${to ? '' : ' none'}">${esc(to || 'no one in the graph yet')}${res && res.by.length ? ` <small>${esc(res.confirmIn.join(', '))}</small>` : ''}</span></div>`);
      if (to && cy.getElementById(to).length && cy.getElementById(item).length && !cy.getElementById(`handover|${item}|${to}`).length) {
        cy.add({ group: 'edges', data: { id: `handover|${item}|${to}`, source: item, target: to }, classes: 'handover' });
        cy.getElementById(to).removeClass('faded').addClass('succ');
        hoverInfo.set(to, (hoverInfo.get(to) || '') + `<div class="green">${esc(item)}: ${esc(how)}</div>`);
      }
    }
    $('handoff-rows').innerHTML = rows.join('');
    show('handoff', rows.length > 0);
    $('ask-promise').textContent = `What did ${first(g.person)} promise the partner on the phone?`;
    $('promise-reply').hidden = true;
    show('promise', true);
    fit(true);
    scheduleSync();
  }

  function askPromise() {
    const g = state.game;
    if (!g) return;
    const a = g.promises;
    const found = (a.rows || []).filter((r) => r.kind === 'promise');
    const reply = $('promise-reply');
    reply.textContent = a.outcome === 'not_in_graph' ? 'Not in the graph.'
      : `${found.length} written ${plural(found.length, 'promise', 'promises')}: ${found[0] ? `${found[0].episode}, "${found[0].line}"` : ''}`;
    reply.hidden = false;
    record(`promises(${g.person})`, [toolCall('promises', { person: g.person }, { body: a, roundtrip: null })]);
  }

  // ---- events -------------------------------------------------------------------------------------------------------
  function onTapNode(n) {
    const id = n.id();
    const kind = model.nodes.get(id)?.kind;
    if (kind !== 'person') return;
    if (state.phase === 'landing' || state.phase === 'picked') { if (id !== state.person) pick(id); return; }
    if (state.phase === 'removed' || state.phase === 'done') { toLanding(false); pick(id); }
  }

  function onTapBackground() {
    if (state.phase === 'picked') toLanding(true);
  }

  function wire() {
    $('remove').addEventListener('click', remove);
    $('again').addEventListener('click', () => toLanding(true));
    $('restart').addEventListener('click', () => toLanding(true));
    $('plan').addEventListener('click', plan);
    $('ask-promise').addEventListener('click', askPromise);
    htmlTip($('promise-reply'), () => `<div class="k">${esc(state.game?.promises?.note || state.game?.promises?.sentence || '')}</div>`);
    $('show-cypher').addEventListener('click', () => {
      const c = $('cypher');
      c.hidden = !c.hidden;
      if (!c.hidden) renderCypher();
    });
    $('cypher-close').addEventListener('click', () => { $('cypher').hidden = true; });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        if (!$('cypher').hidden) $('cypher').hidden = true;
        else if (state.phase === 'picked') toLanding(true);
      }
    });
    for (const k of ['islands', 'decisions', 'bridges']) htmlTip(app.querySelector(`.counter[data-k="${k}"]`), () => (tips[k] ? tips[k]() : ''));
    htmlTip($('wall'), () => (tips.wall ? tips.wall() : ''));
    initSlider();
    let t = null;
    addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { fit(false, state.phase === 'game' ? state.focus : null); scheduleSync(); }, 80); });
  }

  // ---- start --------------------------------------------------------------------------------------------------------
  async function start() {
    setStatus('Loading the company graph…');
    let res;
    try {
      [res] = await Promise.all([api.graph(), api.loadSchemas()]);
    } catch (err) {
      setStatus(`Could not load the graph: ${err.message}`);
      return;
    }
    buildModel(res.body);
    layout();
    initCy();
    wire();
    record('The company graph', [{
      name: `GET /v1/${TENANT}/graph`,
      meta: [`${res.body.nodes.length} nodes, ${res.body.edges.length + res.body.ended.length} facts`,
        res.roundtrip !== null && res.roundtrip !== undefined ? `${res.roundtrip} ms round trip` : 'recorded'].join(' · '),
      queries: (res.body.trace || []).map((t) => ({ text: t.query, ms: t.ms })),
    }]);
    setStatus(api.source === 'fixtures' ? 'recorded answers' : '');
    toLanding(false);
    // read-only hooks for scripted walkthroughs (screenshots, the demo video): where a node is, which phase is on
    window.panel = Object.freeze({
      phase: () => state.phase,
      at: (id) => {
        const n = cy.getElementById(id);
        if (!n.length) return null;
        const p = n.renderedPosition(), r = $('cy').getBoundingClientRect();
        return { x: r.left + p.x, y: r.top + p.y };
      },
      people: () => [...model.nodes.values()].filter((n) => n.kind === 'person').map((n) => n.id),
    });
    // a gentle settle: from slightly gathered towards each zone to the final, still layout
    if (!REDUCED) {
      cy.nodes().forEach((n) => {
        const h = model.home.get(n.id());
        const [cx, cyy] = zoneCenter(model.nodes.get(n.id()).team);
        n.position({ x: h.x + (cx - h.x) * 0.16, y: h.y + (cyy - h.y) * 0.16 });
        n.animate({ position: h }, { duration: 950, easing: 'ease-out-cubic' });
      });
    }
    scheduleSync();
  }

  start();
})();
