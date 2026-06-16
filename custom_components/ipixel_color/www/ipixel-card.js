/* iPIXEL Enhanced — page & pixel studio card
 * Tabs: Designer · Draw · Playlist · Slots · Device.
 * Plain custom element, no build step, no external deps.
 */

const PREVIEW_SCALE = 8;
const GRID = 32;                 // editor grid size (display resolution)
const ANCHORS = [
  "top_left", "top_center", "top_right",
  "center_left", "center", "center_right",
  "bottom_left", "bottom_center", "bottom_right",
];
const FONTS = ["Tiny5", "WP7xn", "PixelifySans", "7x5", "5x5", "PressStart2P", "3x5-de", "OpenSans-Light"];
const FONT_SIZES = { Tiny5: 8, WP7xn: 7, PixelifySans: 10, "7x5": 7, "5x5": 10, PressStart2P: 6, "3x5-de": 8, "OpenSans-Light": 9 };

const PALETTE = ["ffffff", "ff0000", "ff8800", "ffcc00", "00cc33", "00ccaa",
  "2266ff", "00ccdd", "aa44ff", "ff66cc", "888888", "000000"];

const WIDGET_FIELDS = {
  text:     [["text", "text", "Text / template"], ["font", "font", ""], ["size", "number", "Size"]],
  emoji:    [["emoji", "text", "Emoji"], ["size", "number", "Size"]],
  clock:    [["format", "text", "strftime"], ["font", "font", ""], ["size", "number", "Size"]],
  line:     [["x", "number", "x1"], ["y", "number", "y1"], ["x2", "number", "x2"], ["y2", "number", "y2"], ["width", "number", "Thickness"]],
  rect:     [["width", "number", "W"], ["height", "number", "H"], ["fill", "bool", "Filled"], ["radius", "number", "Radius"]],
  progress: [["value", "text", "Value 0-100 / tmpl"], ["width", "number", "W"], ["height", "number", "H"]],
  image:    [["src", "text", "URL or /local/.."], ["width", "number", "W"], ["height", "number", "H"], ["fit", "fit", ""]],
};
const WIDGET_TYPES = Object.keys(WIDGET_FIELDS);
const POSITIONLESS = new Set(["line"]);

const EXAMPLES = {
  "Battery bar": { background: "000000", widgets: [
    { type: "text", anchor: "top_center", color: "ffffff", font: "Tiny5", size: 8, text: "Battery", dy: 1 },
    { type: "text", anchor: "center", font: "Tiny5", size: 8, text: "{{ states('sensor.battery') }}%",
      color: "{{ '00cc33' if states('sensor.battery')|int(0) > 30 else 'ff3333' }}" },
    { type: "progress", anchor: "bottom_center", width: 30, height: 5, dy: -1, value: "{{ states('sensor.battery') }}",
      color: "{{ '00cc33' if states('sensor.battery')|int(0) > 30 else 'ff3333' }}" },
  ] },
  "Temperature + emoji": { background: "000000", widgets: [
    { type: "emoji", anchor: "top_left", size: 14, dx: 1, dy: 1, emoji: "🌡️" },
    { type: "text", anchor: "top_right", color: "ffaa00", font: "Tiny5", size: 8, dx: -1, dy: 2, text: "{{ states('sensor.outdoor_temperature') }}°" },
    { type: "line", x: 0, y: 17, x2: 31, y2: 17, color: "2d2d2d" },
    { type: "clock", anchor: "bottom_center", color: "bebebe", font: "Tiny5", size: 8, dy: -1, format: "%H:%M" },
  ] },
  "Two sensors": { background: "000000", widgets: [
    { type: "text", anchor: "top_left", color: "00ccdd", font: "Tiny5", size: 8, dx: 1, dy: 1, text: "{{ states('sensor.living_room_temperature') }}C" },
    { type: "text", anchor: "bottom_left", color: "88ff00", font: "Tiny5", size: 8, dx: 1, dy: -1, text: "{{ states('sensor.humidity') }}%" },
  ] },
};

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "style") n.setAttribute("style", v);
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return n;
}

const TABS = [
  ["designer", "🎨 Designer"],
  ["draw", "✏️ Draw"],
  ["playlist", "🔁 Playlist"],
  ["slots", "💾 Slots"],
  ["device", "⚙️ Device"],
];

class IPixelCard extends HTMLElement {
  constructor() {
    super();
    this._page = { background: "000000", widgets: [] };
    this._mode = "visual";
    this._tab = "designer";
    this._devices = [];
    this._library = {};
    this._playlist = { enabled: false, items: [], target: null };
    this._device = null;
    this._previewTimer = null;
    this._built = false;
    this._grid = new Array(GRID * GRID).fill(null);
    this._brush = "ff0000";
    this._liveDraw = false;
    this._painting = false;
  }

  setConfig(config) {
    this._config = config || {};
    if (config && config.page) this._page = JSON.parse(JSON.stringify(config.page));
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
      this._loadLibrary();
    }
  }

  getCardSize() { return 14; }

  // ---------- server calls ----------
  async _loadLibrary() {
    try {
      const res = await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/list" });
      this._library = res.pages || {};
      this._playlist = res.playlist || this._playlist;
      this._devices = res.devices || [];
      if (!this._device && this._devices.length) this._device = this._devices[0].id;
      this._refreshDeviceList();
      this._renderTab();
    } catch (e) {
      this._status("Could not reach the integration: " + e, true);
    }
  }

  _schedulePreview() {
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._renderPreview(), 250);
  }

  async _renderPreview() {
    if (!this._hass || !this._img) return;
    try {
      const res = await this._hass.callApi("POST", "ipixel_color/preview", {
        page: this._page, width: GRID, height: GRID, scale: PREVIEW_SCALE,
      });
      if (this._img) this._img.src = res.image;
    } catch (e) {
      this._status("Preview error: " + (e.body && e.body.message ? e.body.message : e), true);
    }
  }

  // ---------- build shell ----------
  _build() {
    const card = el("ha-card", {});
    const root = el("div", { class: "ipx-root" });

    const head = el("div", { class: "ipx-head" }, [
      el("div", { class: "ipx-title" }, "iPIXEL Studio"),
      this._deviceSel = el("select", { class: "ipx-input", onchange: (e) => { this._device = e.target.value; } }),
    ]);
    root.appendChild(head);

    this._tabBar = el("div", { class: "ipx-tabs" });
    TABS.forEach(([id, label]) => {
      this._tabBar.appendChild(el("button", {
        class: "ipx-tab", "data-tab": id, onclick: () => this._setTab(id),
      }, label));
    });
    root.appendChild(this._tabBar);

    this._statusBar = el("div", { class: "ipx-status" });
    root.appendChild(this._statusBar);

    this._content = el("div", { class: "ipx-content" });
    root.appendChild(this._content);

    card.appendChild(root);
    card.appendChild(this._styles());
    card.appendChild(this._buildEntityDatalist());
    this.appendChild(card);

    this._refreshTabBar();
    this._renderTab();
  }

  _buildEntityDatalist() {
    const dl = el("datalist", { id: "ipx-entities" });
    const states = (this._hass && this._hass.states) || {};
    for (const id of Object.keys(states).sort()) {
      const fn = states[id].attributes && states[id].attributes.friendly_name;
      dl.appendChild(el("option", { value: id }, fn || id));
    }
    return dl;
  }

  _setTab(id) { this._tab = id; this._refreshTabBar(); this._renderTab(); }

  _refreshTabBar() {
    [...this._tabBar.children].forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-tab") === this._tab);
    });
  }

  _renderTab() {
    if (!this._content) return;
    this._content.innerHTML = "";
    this._img = null;
    ({
      designer: () => this._tabDesigner(),
      draw: () => this._tabDraw(),
      playlist: () => this._tabPlaylist(),
      slots: () => this._tabSlots(),
      device: () => this._tabDevice(),
    }[this._tab] || (() => {}))();
  }

  _status(msg, isError) {
    this._statusBar.textContent = msg || "";
    this._statusBar.style.color = isError ? "var(--error-color)" : "var(--secondary-text-color)";
  }

  _refreshDeviceList() {
    if (!this._deviceSel) return;
    this._deviceSel.innerHTML = "";
    if (!this._devices.length) { this._deviceSel.appendChild(el("option", { value: "" }, "no device")); return; }
    for (const d of this._devices) this._deviceSel.appendChild(el("option", { value: d.id }, d.name));
    if (this._device) this._deviceSel.value = this._device;
  }

  _labeled(text, node) { return el("label", { class: "ipx-lbl" }, [text, node]); }

  // ============================================================ DESIGNER
  _tabDesigner() {
    const wrap = el("div", { class: "ipx-cols" });

    // left: preview + actions
    const left = el("div", { class: "ipx-pane" });
    this._img = el("img", { class: "ipx-preview",
      style: `width:${GRID * PREVIEW_SCALE}px;height:${GRID * PREVIEW_SCALE}px;` });
    left.appendChild(this._img);
    left.appendChild(el("button", { class: "ipx-btn ipx-primary ipx-wide", onclick: () => this._sendNow() }, "📤 Send now"));

    this._nameInput = el("input", { class: "ipx-input", type: "text", placeholder: "page name" });
    left.appendChild(this._labeled("Save to library", el("div", { class: "ipx-flex" }, [
      this._nameInput, el("button", { class: "ipx-btn", onclick: () => this._savePage() }, "Save"),
    ])));
    this._librarySel = el("select", { class: "ipx-input", onchange: (e) => this._loadPage(e.target.value) });
    left.appendChild(this._labeled("Load page", el("div", { class: "ipx-flex" }, [
      this._librarySel, el("button", { class: "ipx-btn", onclick: () => this._deletePage() }, "Delete"),
    ])));
    const exampleSel = el("select", { class: "ipx-input", onchange: (e) => this._loadExample(e.target.value) });
    exampleSel.appendChild(el("option", { value: "" }, "— starter examples —"));
    Object.keys(EXAMPLES).forEach((n) => exampleSel.appendChild(el("option", { value: n }, n)));
    left.appendChild(this._labeled("Examples (edit entity names!)", exampleSel));
    wrap.appendChild(left);

    // right: editor
    const right = el("div", { class: "ipx-pane ipx-grow" });
    right.appendChild(el("div", { class: "ipx-segment" }, [
      el("button", { class: "ipx-btn" + (this._mode === "visual" ? " ipx-primary" : ""), onclick: () => this._setMode("visual") }, "Visual"),
      el("button", { class: "ipx-btn" + (this._mode === "code" ? " ipx-primary" : ""), onclick: () => this._setMode("code") }, "Code (JSON)"),
    ]));
    this._editor = el("div", {});
    right.appendChild(this._editor);
    wrap.appendChild(right);

    this._content.appendChild(wrap);
    this._refreshLibraryList();
    this._renderEditor();
    this._renderPreview();
  }

  _refreshLibraryList() {
    if (!this._librarySel) return;
    const names = Object.keys(this._library).sort();
    this._librarySel.innerHTML = "";
    this._librarySel.appendChild(el("option", { value: "" }, names.length ? "— pick a page —" : "library empty"));
    for (const n of names) this._librarySel.appendChild(el("option", { value: n }, n));
  }

  _setMode(mode) { if (mode === "code") this._codeText = JSON.stringify(this._page, null, 2); this._mode = mode; this._tabDesigner(); }

  _renderEditor() {
    this._editor.innerHTML = "";
    if (this._mode === "code") return this._renderCodeEditor();
    return this._renderVisualEditor();
  }

  _renderCodeEditor() {
    const ta = el("textarea", { class: "ipx-input ipx-code" });
    ta.value = this._codeText != null ? this._codeText : JSON.stringify(this._page, null, 2);
    ta.addEventListener("input", () => { this._codeText = ta.value; });
    const apply = el("button", { class: "ipx-btn ipx-primary", onclick: () => {
      try { this._page = JSON.parse(ta.value); this._status("Applied."); this._schedulePreview(); }
      catch (e) { this._status("Invalid JSON: " + e.message, true); }
    } }, "Apply");
    this._editor.appendChild(el("div", { class: "ipx-pane" }, [ta, apply]));
  }

  _renderVisualEditor() {
    const wrap = el("div", {});
    const bg = el("input", { class: "ipx-input", type: "text", value: this._page.background || "000000" });
    bg.addEventListener("input", () => { this._page.background = bg.value; this._schedulePreview(); });
    wrap.appendChild(el("div", { class: "ipx-row" }, [this._labeled("Background", bg)]));
    (this._page.widgets || []).forEach((w, i) => wrap.appendChild(this._widgetRow(w, i)));
    const addSel = el("select", { class: "ipx-input" });
    WIDGET_TYPES.forEach((t) => addSel.appendChild(el("option", { value: t }, t)));
    wrap.appendChild(el("div", { class: "ipx-flex", style: "margin-top:6px;" }, [
      addSel,
      el("button", { class: "ipx-btn ipx-primary", onclick: () => {
        this._page.widgets = this._page.widgets || [];
        this._page.widgets.push(this._defaultWidget(addSel.value));
        this._renderEditor(); this._schedulePreview();
      } }, "+ Add widget"),
    ]));
    this._editor.appendChild(wrap);
  }

  _defaultWidget(type) {
    const w = { type, anchor: "center", color: "ffffff" };
    if (type === "text") { w.text = "Hello"; w.font = "Tiny5"; w.size = 8; }
    if (type === "emoji") { w.emoji = "⭐"; w.size = 12; }
    if (type === "clock") { w.format = "%H:%M"; w.font = "Tiny5"; w.size = 8; }
    if (type === "line") { delete w.anchor; w.x = 0; w.y = 16; w.x2 = 31; w.y2 = 16; w.color = "888888"; }
    if (type === "rect") { w.width = 8; w.height = 8; w.fill = true; }
    if (type === "progress") { w.value = "50"; w.width = 30; w.height = 4; w.color = "00cc33"; }
    if (type === "image") { w.src = "/local/"; w.width = 32; w.height = 32; w.fit = "contain"; }
    return w;
  }

  _widgetRow(w, i) {
    const row = el("div", { class: "ipx-row" });
    row.appendChild(el("span", { class: "ipx-pill" }, w.type));
    const typeSel = el("select", { class: "ipx-input" });
    WIDGET_TYPES.forEach((t) => typeSel.appendChild(el("option", { value: t, ...(t === w.type ? { selected: "" } : {}) }, t)));
    typeSel.addEventListener("change", () => { this._page.widgets[i] = this._defaultWidget(typeSel.value); this._renderEditor(); this._schedulePreview(); });
    row.appendChild(this._labeled("type", typeSel));

    if (!POSITIONLESS.has(w.type)) {
      const anchorSel = el("select", { class: "ipx-input" });
      anchorSel.appendChild(el("option", { value: "" }, "x/y"));
      ANCHORS.forEach((a) => anchorSel.appendChild(el("option", { value: a, ...(w.anchor === a ? { selected: "" } : {}) }, a)));
      anchorSel.addEventListener("change", () => {
        if (anchorSel.value) { w.anchor = anchorSel.value; delete w.x; delete w.y; }
        else { delete w.anchor; w.x = 0; w.y = 0; }
        this._renderEditor(); this._schedulePreview();
      });
      row.appendChild(this._labeled("position", anchorSel));
      if (!w.anchor) { row.appendChild(this._field(w, "x", "number", "x")); row.appendChild(this._field(w, "y", "number", "y")); }
      else { row.appendChild(this._field(w, "dx", "number", "dx")); row.appendChild(this._field(w, "dy", "number", "dy")); }
    }
    if (w.type !== "image") row.appendChild(this._field(w, "color", "text", "color"));
    for (const [key, kind, label] of (WIDGET_FIELDS[w.type] || [])) row.appendChild(this._field(w, key, kind, label));
    const bindKey = w.type === "text" ? "text" : (w.type === "progress" ? "value" : null);
    if (bindKey) row.appendChild(this._entityBind(w, bindKey));

    row.appendChild(el("div", { class: "ipx-ctrl" }, [
      el("button", { class: "ipx-btn", onclick: () => this._move(i, -1) }, "↑"),
      el("button", { class: "ipx-btn", onclick: () => this._move(i, 1) }, "↓"),
      el("button", { class: "ipx-btn", onclick: () => { this._page.widgets.splice(i, 1); this._renderEditor(); this._schedulePreview(); } }, "✕"),
    ]));
    return row;
  }

  _entityBind(w, key) {
    const inp = el("input", { class: "ipx-input", list: "ipx-entities", placeholder: "pick entity…", style: "width:140px;" });
    inp.addEventListener("change", () => {
      const id = inp.value.trim();
      if (id && this._hass && this._hass.states && this._hass.states[id]) {
        w[key] = `{{ states('${id}') }}`; inp.value = "";
        this._renderEditor(); this._schedulePreview(); this._status(`Bound ${key} to ${id}`);
      }
    });
    return this._labeled("＋ HA entity", inp);
  }

  _field(w, key, kind, label) {
    let input;
    if (kind === "bool") {
      input = el("input", { type: "checkbox" }); input.checked = !!w[key];
      input.addEventListener("change", () => { w[key] = input.checked; this._schedulePreview(); });
    } else if (kind === "font") {
      input = el("select", { class: "ipx-input" });
      FONTS.forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; if (FONT_SIZES[input.value]) w.size = FONT_SIZES[input.value]; this._renderEditor(); this._schedulePreview(); });
    } else if (kind === "fit") {
      input = el("select", { class: "ipx-input" });
      ["contain", "cover", "stretch"].forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; this._schedulePreview(); });
    } else {
      input = el("input", { class: "ipx-input", type: kind === "number" ? "number" : "text", style: "width:90px;" });
      if (w[key] !== undefined) input.value = w[key];
      input.addEventListener("input", () => { w[key] = kind === "number" ? (input.value === "" ? undefined : Number(input.value)) : input.value; this._schedulePreview(); });
    }
    return this._labeled(label || key, input);
  }

  _move(i, dir) {
    const j = i + dir, a = this._page.widgets;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; this._renderEditor(); this._schedulePreview();
  }

  async _savePage() {
    const name = (this._nameInput.value || "").trim();
    if (!name) return this._status("Enter a page name first.", true);
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/save", name, page: this._page });
      this._library[name] = JSON.parse(JSON.stringify(this._page));
      this._refreshLibraryList(); this._status(`Saved “${name}”.`);
    } catch (e) { this._status("Save failed: " + e, true); }
  }
  _loadPage(name) {
    if (!name || !this._library[name]) return;
    this._page = JSON.parse(JSON.stringify(this._library[name]));
    if (this._nameInput) this._nameInput.value = name;
    this._codeText = null; this._renderEditor(); this._schedulePreview(); this._status(`Loaded “${name}”.`);
  }
  async _deletePage() {
    const name = this._librarySel.value; if (!name) return;
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/delete", name });
      delete this._library[name]; this._refreshLibraryList(); this._status(`Deleted “${name}”.`);
    } catch (e) { this._status("Delete failed: " + e, true); }
  }
  _loadExample(name) {
    if (!name || !EXAMPLES[name]) return;
    this._page = JSON.parse(JSON.stringify(EXAMPLES[name]));
    this._codeText = null; this._mode = "visual"; this._tabDesigner();
    this._status(`Loaded example “${name}” — change the entity names to yours.`);
  }
  async _sendNow() {
    if (!this._device) return this._status("No device selected.", true);
    try {
      await this._hass.callService("ipixel_color", "show_page", { page: this._page }, { device_id: this._device });
      this._status("Sent to display.");
    } catch (e) { this._status("Send failed: " + e, true); }
  }

  // ============================================================ DRAW
  _tabDraw() {
    const wrap = el("div", { class: "ipx-cols" });

    // palette + tools
    const tools = el("div", { class: "ipx-pane" });
    const pal = el("div", { class: "ipx-palette" });
    PALETTE.forEach((c) => {
      const sw = el("button", { class: "ipx-swatch", style: `background:#${c};`, title: c, onclick: () => { this._brush = c; this._markBrush(pal, c); } });
      sw.dataset.c = c;
      pal.appendChild(sw);
    });
    tools.appendChild(this._labeled("Palette", pal));
    const custom = el("input", { type: "color", value: "#ff0000", onchange: (e) => { this._brush = e.target.value.replace("#", ""); this._markBrush(pal, null); } });
    tools.appendChild(this._labeled("Custom color", custom));
    const eraser = el("button", { class: "ipx-btn", onclick: () => { this._brush = null; this._markBrush(pal, null); this._status("Eraser selected"); } }, "🧽 Eraser");
    tools.appendChild(eraser);

    const live = el("input", { type: "checkbox" });
    live.checked = this._liveDraw;
    live.addEventListener("change", async () => {
      this._liveDraw = live.checked;
      if (this._liveDraw && this._device) {
        await this._hass.callService("ipixel_color", "set_fun_mode", { enable: true }, { device_id: this._device });
        this._status("Live draw ON — DIY mode enabled on the panel.");
      }
    });
    tools.appendChild(el("label", { class: "ipx-lbl ipx-inline" }, [live, "Live draw (paint directly on panel)"]));

    tools.appendChild(el("div", { class: "ipx-flex", style: "margin-top:8px;" }, [
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._sendDrawing() }, "📤 Send drawing"),
      el("button", { class: "ipx-btn", onclick: () => this._clearGrid() }, "Clear"),
    ]));
    tools.appendChild(el("div", { class: "ipx-hint" },
      "Click or drag to paint. “Send drawing” pushes the whole picture at once. " +
      "“Live draw” lights each pixel on the panel as you click (enables DIY mode)."));
    wrap.appendChild(tools);

    // grid
    const gridWrap = el("div", { class: "ipx-pane ipx-grow" });
    this._gridEl = el("div", { class: "ipx-grid",
      style: `grid-template-columns:repeat(${GRID},1fr);width:${GRID * 12}px;height:${GRID * 12}px;` });
    for (let i = 0; i < GRID * GRID; i++) {
      const c = this._grid[i];
      const cell = el("div", { class: "ipx-cell", "data-i": i, style: c ? `background:#${c};` : "" });
      this._gridEl.appendChild(cell);
    }
    this._gridEl.addEventListener("pointerdown", (e) => { this._painting = true; this._paintCell(e.target); e.preventDefault(); });
    this._gridEl.addEventListener("pointerover", (e) => { if (this._painting) this._paintCell(e.target); });
    window.addEventListener("pointerup", () => { this._painting = false; });
    gridWrap.appendChild(this._gridEl);
    wrap.appendChild(gridWrap);

    this._content.appendChild(wrap);
    this._markBrush(pal, this._brush);
  }

  _markBrush(pal, c) {
    [...pal.children].forEach((s) => s.classList.toggle("sel", c && s.dataset.c === c));
  }

  _paintCell(cell) {
    if (!cell || !cell.classList || !cell.classList.contains("ipx-cell")) return;
    const i = +cell.getAttribute("data-i");
    this._grid[i] = this._brush;            // null = erase
    cell.setAttribute("style", this._brush ? `background:#${this._brush};` : "");
    if (this._liveDraw && this._device && this._brush) {
      const x = i % GRID, y = Math.floor(i / GRID);
      this._hass.callService("ipixel_color", "set_pixel", { x, y, color: this._brush }, { device_id: this._device })
        .catch((e) => this._status("set_pixel failed: " + e, true));
    }
  }

  async _sendDrawing() {
    if (!this._device) return this._status("No device selected.", true);
    try {
      await this._hass.connection.sendMessagePromise({
        type: "ipixel_color/draw_grid", target: this._device,
        width: GRID, height: GRID, background: "000000",
        pixels: this._grid.map((c) => c || ""),
      });
      this._status("Drawing sent.");
    } catch (e) { this._status("Send failed: " + e, true); }
  }

  _clearGrid() {
    this._grid = new Array(GRID * GRID).fill(null);
    if (this._gridEl) [...this._gridEl.children].forEach((c) => c.setAttribute("style", ""));
    this._status("Cleared (press Send to blank the panel).");
  }

  // ============================================================ PLAYLIST
  _tabPlaylist() {
    const box = el("div", { class: "ipx-pane" });
    box.appendChild(el("b", {}, "Auto-rotate & auto-refresh pages"));
    box.appendChild(el("div", { class: "ipx-hint" },
      "Each page re-renders on its interval, so dynamic data stays live. " +
      "For a single live page, add just that one. For a pure clock, use the device's native clock mode."));

    this._plEnabled = el("input", { type: "checkbox" });
    box.appendChild(el("label", { class: "ipx-lbl ipx-inline" }, [this._plEnabled, "Enabled"]));
    this._plTarget = el("select", { class: "ipx-input" });
    box.appendChild(this._labeled("Target device", this._plTarget));
    this._plList = el("div", {});
    box.appendChild(this._plList);

    const addSel = el("select", { class: "ipx-input" });
    Object.keys(this._library).sort().forEach((n) => addSel.appendChild(el("option", { value: n }, n)));
    box.appendChild(el("div", { class: "ipx-flex", style: "margin-top:6px;" }, [
      addSel,
      el("button", { class: "ipx-btn", onclick: () => {
        if (!addSel.value) return;
        this._playlist.items = this._playlist.items || [];
        this._playlist.items.push({ name: addSel.value, duration: 10 });
        this._refreshPlaylist();
      } }, "+ Add to playlist"),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._savePlaylist() }, "Save playlist"),
    ]));
    this._content.appendChild(box);
    this._refreshPlaylist();
  }

  _refreshPlaylist() {
    if (!this._plList) return;
    this._plEnabled.checked = !!this._playlist.enabled;
    this._plTarget.innerHTML = "";
    this._plTarget.appendChild(el("option", { value: "" }, "first device"));
    for (const d of this._devices) this._plTarget.appendChild(el("option", { value: d.id, ...(this._playlist.target === d.id ? { selected: "" } : {}) }, d.name));
    this._plList.innerHTML = "";
    (this._playlist.items || []).forEach((it, i) => {
      const dur = el("input", { class: "ipx-input", type: "number", value: it.duration, style: "width:70px;" });
      dur.addEventListener("input", () => { it.duration = Number(dur.value); });
      this._plList.appendChild(el("div", { class: "ipx-row" }, [
        el("span", {}, `${i + 1}. ${it.name}`), this._labeled("seconds", dur),
        el("button", { class: "ipx-btn", style: "margin-left:auto;", onclick: () => { this._playlist.items.splice(i, 1); this._refreshPlaylist(); } }, "✕"),
      ]));
    });
  }

  async _savePlaylist() {
    this._playlist.enabled = this._plEnabled.checked;
    this._playlist.target = this._plTarget.value || null;
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/playlist/set", playlist: this._playlist });
      this._status("Playlist saved.");
    } catch (e) { this._status("Playlist save failed: " + e, true); }
  }

  // ============================================================ SLOTS
  _tabSlots() {
    const box = el("div", { class: "ipx-pane" });
    box.appendChild(el("b", {}, "Device slots — native animation"));
    box.appendChild(el("div", { class: "ipx-hint" },
      "Save pages into the panel's own memory, then let it cycle them by itself — " +
      "no Home Assistant, no Bluetooth needed afterwards."));

    const names = Object.keys(this._library).sort();
    if (!names.length) box.appendChild(el("div", { class: "ipx-hint" }, "Save some pages in the Designer first."));
    names.forEach((n) => {
      const slot = el("input", { class: "ipx-input", type: "number", min: 1, max: 255, value: 1, style: "width:70px;" });
      box.appendChild(el("div", { class: "ipx-row" }, [
        el("span", { style: "min-width:120px;" }, n),
        this._labeled("slot", slot),
        el("button", { class: "ipx-btn", onclick: () => this._saveToSlot(n, +slot.value) }, "💾 Save to slot"),
      ]));
    });

    const order = el("input", { class: "ipx-input", type: "text", placeholder: "1,2,3", style: "width:120px;" });
    box.appendChild(el("hr", { class: "ipx-hr" }));
    box.appendChild(el("b", {}, "Cycle slots (animation)"));
    box.appendChild(el("div", { class: "ipx-flex" }, [
      this._labeled("order", order),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._startProgram(order.value) }, "▶ Start cycling"),
    ]));

    const one = el("input", { class: "ipx-input", type: "number", min: 0, max: 255, value: 1, style: "width:70px;" });
    box.appendChild(el("div", { class: "ipx-flex", style: "margin-top:6px;" }, [
      this._labeled("slot", one),
      el("button", { class: "ipx-btn", onclick: () => this._svc("show_slot", { slot: +one.value }) }, "Show slot"),
      el("button", { class: "ipx-btn", onclick: () => this._svc("delete_slot", { slot: +one.value }) }, "Delete slot"),
    ]));
    this._content.appendChild(box);
  }

  async _saveToSlot(name, slot) {
    const page = this._library[name];
    if (!page) return;
    try {
      await this._hass.callService("ipixel_color", "show_page", { page, save_slot: slot }, { device_id: this._device });
      this._status(`Saved “${name}” to slot ${slot}.`);
    } catch (e) { this._status("Save to slot failed: " + e, true); }
  }
  _startProgram(text) {
    const slots = (text || "").split(/[,\s]+/).map((x) => parseInt(x, 10)).filter((x) => !isNaN(x));
    if (!slots.length) return this._status("Enter slot numbers like 1,2,3", true);
    this._svc("set_program", { slots });
  }

  // ============================================================ DEVICE
  _tabDevice() {
    const box = el("div", { class: "ipx-pane" });
    box.appendChild(el("b", {}, "Device controls"));
    const ents = this._deviceEntities();
    if (!ents.length) {
      box.appendChild(el("div", { class: "ipx-hint" }, "No controllable entities found for this device."));
    }
    ents.forEach((eid) => {
      const st = this._hass.states[eid];
      if (!st) return;
      const domain = eid.split(".")[0];
      const label = (st.attributes && st.attributes.friendly_name) || eid;
      let control = null;
      if (domain === "switch") {
        const on = st.state === "on";
        control = el("button", { class: "ipx-btn" + (on ? " ipx-primary" : ""),
          onclick: () => this._hass.callService("switch", on ? "turn_off" : "turn_on", {}, { entity_id: eid }).then(() => setTimeout(() => this._tabDevice0(), 400)) },
          on ? "ON" : "OFF");
      } else if (domain === "number") {
        const a = st.attributes || {};
        const rng = el("input", { type: "range", min: a.min ?? 1, max: a.max ?? 100, step: a.step ?? 1, value: st.state });
        const val = el("span", { class: "ipx-val" }, st.state);
        rng.addEventListener("change", () => { val.textContent = rng.value; this._hass.callService("number", "set_value", { value: Number(rng.value) }, { entity_id: eid }); });
        control = el("div", { class: "ipx-flex" }, [rng, val]);
      } else if (domain === "select") {
        const sel = el("select", { class: "ipx-input" });
        (st.attributes.options || []).forEach((o) => sel.appendChild(el("option", { value: o, ...(o === st.state ? { selected: "" } : {}) }, o)));
        sel.addEventListener("change", () => this._hass.callService("select", "select_option", { option: sel.value }, { entity_id: eid }));
        control = sel;
      }
      if (control) box.appendChild(el("div", { class: "ipx-row" }, [el("span", { style: "min-width:150px;" }, label), control]));
    });

    box.appendChild(el("hr", { class: "ipx-hr" }));
    box.appendChild(el("b", {}, "Rhythm / visualizer"));
    const style = el("input", { class: "ipx-input", type: "number", min: 0, max: 1, value: 1, style: "width:60px;" });
    const frame = el("input", { class: "ipx-input", type: "number", min: 0, max: 7, value: 3, style: "width:60px;" });
    box.appendChild(el("div", { class: "ipx-flex" }, [
      this._labeled("style", style), this._labeled("frame", frame),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._svc("set_rhythm_animation", { style: +style.value, frame: +frame.value }) }, "▶ Play animation"),
    ]));
    box.appendChild(el("div", { class: "ipx-hint" }, "Self-contained visualizer (no audio source needed)."));

    this._content.appendChild(box);
  }

  _tabDevice0() { if (this._tab === "device") this._renderTab(); }

  _deviceEntities() {
    const out = [];
    const reg = this._hass.entities || {};
    for (const [eid, ent] of Object.entries(reg)) {
      if (ent.platform === "ipixel_color" && ent.device_id === this._device) {
        const d = eid.split(".")[0];
        if (["switch", "number", "select"].includes(d)) out.push(eid);
      }
    }
    return out.sort();
  }

  // ---------- helpers ----------
  async _svc(service, data) {
    if (!this._device) return this._status("No device selected.", true);
    try { await this._hass.callService("ipixel_color", service, data, { device_id: this._device }); this._status(`${service} sent.`); }
    catch (e) { this._status(`${service} failed: ` + e, true); }
  }

  _styles() {
    return el("style", {}, `
      .ipx-root{padding:12px;display:flex;flex-direction:column;gap:12px;}
      .ipx-head{display:flex;align-items:center;gap:12px;justify-content:space-between;}
      .ipx-title{font-size:20px;font-weight:600;}
      .ipx-tabs{display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--divider-color);padding-bottom:8px;}
      .ipx-tab{padding:8px 14px;border:none;border-radius:8px 8px 0 0;cursor:pointer;font:inherit;
        background:transparent;color:var(--secondary-text-color);}
      .ipx-tab:hover{background:var(--secondary-background-color);}
      .ipx-tab.active{background:var(--primary-color);color:var(--text-primary-color,#fff);font-weight:600;}
      .ipx-content{min-height:200px;}
      .ipx-cols{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;}
      .ipx-pane{display:flex;flex-direction:column;gap:10px;padding:12px;border:1px solid var(--divider-color);
        border-radius:10px;background:var(--card-background-color);}
      .ipx-grow{flex:1;min-width:280px;}
      .ipx-input{padding:5px 7px;border:1px solid var(--divider-color);border-radius:6px;
        background:var(--card-background-color);color:var(--primary-text-color);font:inherit;}
      .ipx-btn{padding:6px 12px;border:1px solid var(--divider-color);border-radius:6px;cursor:pointer;
        background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit;}
      .ipx-btn:hover{filter:brightness(1.1);}
      .ipx-primary{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:transparent;}
      .ipx-wide{width:100%;}
      .ipx-flex{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
      .ipx-segment{display:flex;gap:6px;margin-bottom:8px;}
      .ipx-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:8px;border:1px solid var(--divider-color);
        border-radius:8px;margin-bottom:6px;background:var(--secondary-background-color);}
      .ipx-lbl{font-size:12px;color:var(--secondary-text-color);display:flex;flex-direction:column;gap:3px;}
      .ipx-lbl.ipx-inline{flex-direction:row;align-items:center;gap:6px;}
      .ipx-preview{image-rendering:pixelated;background:#111;border:1px solid var(--divider-color);border-radius:8px;}
      .ipx-status{min-height:18px;font-size:12px;color:var(--secondary-text-color);}
      .ipx-pill{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--primary-color);color:#fff;}
      .ipx-ctrl{margin-left:auto;display:flex;gap:4px;}
      textarea.ipx-code{width:100%;min-height:260px;font-family:monospace;}
      .ipx-hint{font-size:12px;color:var(--secondary-text-color);line-height:1.4;}
      .ipx-palette{display:flex;gap:4px;flex-wrap:wrap;max-width:180px;}
      .ipx-swatch{width:24px;height:24px;border-radius:5px;border:2px solid transparent;cursor:pointer;}
      .ipx-swatch.sel{border-color:var(--primary-text-color,#fff);outline:1px solid var(--primary-color);}
      .ipx-grid{display:grid;gap:0;border:1px solid var(--divider-color);background:#000;touch-action:none;user-select:none;}
      .ipx-cell{border:1px solid rgba(128,128,128,.15);background:transparent;}
      .ipx-val{min-width:32px;text-align:right;}
      .ipx-hr{border:none;border-top:1px solid var(--divider-color);width:100%;margin:8px 0;}
    `);
  }
}

customElements.define("ipixel-card", IPixelCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "ipixel-card", name: "iPIXEL Studio",
  description: "Design pages, draw pixels, manage playlists/slots and control your iPIXEL panel." });
console.info("%c iPIXEL-CARD ", "background:#222;color:#0cf", "loaded (tabbed)");
