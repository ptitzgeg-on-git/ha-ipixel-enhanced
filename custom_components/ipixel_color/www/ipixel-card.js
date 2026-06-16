/* iPIXEL Enhanced — page & pixel studio card
 * Tabs: Designer · Draw · Playlist · Slots · Device.
 * Plain custom element, no build step, no external deps (uses HA's <ha-icon>).
 */

const PREVIEW_SCALE = 8;
const GRID = 32;                 // default editor grid size; overridden per device
const ANCHORS = [
  "top_left", "top_center", "top_right",
  "center_left", "center", "center_right",
  "bottom_left", "bottom_center", "bottom_right",
];
const FONTS = ["Tiny5", "WP7xn", "PixelifySans", "7x5", "5x5", "PressStart2P", "3x5-de", "OpenSans-Light"];
const FONT_SIZES = { Tiny5: 8, WP7xn: 7, PixelifySans: 10, "7x5": 7, "5x5": 10, PressStart2P: 6, "3x5-de": 8, "OpenSans-Light": 9 };

const PALETTE = ["ffffff", "ff0000", "ff8800", "ffcc00", "00cc33", "00ccaa",
  "2266ff", "00ccdd", "aa44ff", "ff66cc", "888888", "000000"];

const WIDGET_ICON = {
  text: "mdi:format-text", emoji: "mdi:emoticon-happy-outline", clock: "mdi:clock-outline",
  line: "mdi:vector-line", rect: "mdi:rectangle-outline", progress: "mdi:gauge", image: "mdi:image-outline",
};
const WIDGET_FIELDS = {
  text:     [["text", "text", "Text / template"], ["font", "font", "Font"], ["size", "number", "Size"]],
  emoji:    [["emoji", "text", "Emoji"], ["size", "number", "Size"]],
  clock:    [["format", "text", "strftime"], ["font", "font", "Font"], ["size", "number", "Size"]],
  line:     [["x", "number", "x1"], ["y", "number", "y1"], ["x2", "number", "x2"], ["y2", "number", "y2"], ["width", "number", "Thickness"]],
  rect:     [["width", "number", "W"], ["height", "number", "H"], ["fill", "bool", "Filled"], ["radius", "number", "Radius"]],
  progress: [["value", "text", "Value 0-100 / tmpl"], ["width", "number", "W"], ["height", "number", "H"]],
  image:    [["src", "text", "URL or /local/.."], ["width", "number", "W"], ["height", "number", "H"], ["fit", "fit", "Fit"]],
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
function icon(name) { return el("ha-icon", { icon: name, class: "ipx-ic" }); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }
const isHex6 = (s) => typeof s === "string" && /^[0-9a-fA-F]{6}$/.test(s);
const isTpl = (s) => typeof s === "string" && s.includes("{{");

const TABS = [
  ["designer", "mdi:palette", "Designer"],
  ["draw", "mdi:brush", "Draw"],
  ["playlist", "mdi:playlist-play", "Playlist"],
  ["slots", "mdi:content-save-outline", "Slots"],
  ["device", "mdi:cog-outline", "Device"],
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
    this._dims = {};                 // deviceId -> {w, h}
    this._gw = GRID;
    this._gh = GRID;
    this._previewTimer = null;
    this._built = false;
    this._grid = new Array(this._gw * this._gh).fill(null);
    this._brush = "ff0000";
    this._liveDraw = false;
    this._painting = false;
    this._liveQueue = [];            // throttled set_pixel queue for Live draw
    this._liveFlushing = false;
  }

  // current device's panel resolution (falls back to 32x32)
  _setDims(deviceId) {
    const d = this._dims[deviceId];
    const w = d && d.w ? d.w : GRID;
    const h = d && d.h ? d.h : GRID;
    const changed = w !== this._gw || h !== this._gh;
    this._gw = w; this._gh = h;
    if (changed) this._grid = new Array(this._gw * this._gh).fill(null);
    return changed;
  }

  setConfig(config) {
    this._config = config || {};
    if (config && config.page) this._page = clone(config.page);
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
      this._dims = {};
      for (const d of this._devices) this._dims[d.id] = { w: d.width || GRID, h: d.height || GRID };
      if (!this._device && this._devices.length) this._device = this._devices[0].id;
      this._setDims(this._device);
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
        page: this._page, width: this._gw, height: this._gh, scale: PREVIEW_SCALE,
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
      el("div", { class: "ipx-brand" }, [icon("mdi:dots-grid"), el("span", { class: "ipx-title" }, "iPIXEL Studio")]),
      this._deviceSel = el("select", { class: "ipx-input", onchange: (e) => {
        this._device = e.target.value;
        if (this._setDims(this._device)) this._renderTab();
        else this._schedulePreview();
      } }),
    ]);
    root.appendChild(head);

    this._tabBar = el("div", { class: "ipx-tabs" });
    TABS.forEach(([id, ic, label]) => {
      this._tabBar.appendChild(el("button", {
        class: "ipx-tab", "data-tab": id, onclick: () => this._setTab(id),
      }, [icon(ic), el("span", {}, label)]));
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
    this._statusBar.className = "ipx-status" + (msg ? (isError ? " err" : " ok") : "");
  }

  _refreshDeviceList() {
    if (!this._deviceSel) return;
    this._deviceSel.innerHTML = "";
    if (!this._devices.length) { this._deviceSel.appendChild(el("option", { value: "" }, "no device")); return; }
    for (const d of this._devices) this._deviceSel.appendChild(el("option", { value: d.id }, d.name));
    if (this._device) this._deviceSel.value = this._device;
  }

  _labeled(text, node) { return el("label", { class: "ipx-lbl" }, [el("span", { class: "ipx-lblt" }, text), node]); }
  _paneHead(text, sub) {
    return el("div", { class: "ipx-paneh" }, [el("span", {}, text), sub ? el("span", { class: "ipx-sub" }, sub) : null]);
  }

  // ============================================================ DESIGNER
  _tabDesigner() {
    const wrap = el("div", { class: "ipx-cols" });

    // left: preview + library actions
    const left = el("div", { class: "ipx-pane ipx-side" });
    left.appendChild(this._paneHead("Live preview", `${this._gw}×${this._gh}`));
    this._img = el("img", { class: "ipx-preview",
      style: `width:${this._gw * PREVIEW_SCALE}px;height:${this._gh * PREVIEW_SCALE}px;` });
    left.appendChild(el("div", { class: "ipx-previewwrap" }, [this._img]));
    left.appendChild(el("button", { class: "ipx-btn ipx-primary ipx-wide", onclick: () => this._sendNow() },
      [icon("mdi:send"), "Send now"]));

    this._nameInput = el("input", { class: "ipx-input", type: "text", placeholder: "page name" });
    left.appendChild(this._labeled("Save to library", el("div", { class: "ipx-flex" }, [
      this._nameInput,
      el("button", { class: "ipx-btn", onclick: () => this._savePage() }, [icon("mdi:content-save"), "Save"]),
    ])));
    this._librarySel = el("select", { class: "ipx-input ipx-grow", onchange: (e) => this._loadPage(e.target.value) });
    left.appendChild(this._labeled("Load page", el("div", { class: "ipx-flex" }, [
      this._librarySel,
      el("button", { class: "ipx-iconbtn ipx-danger", title: "Delete page", onclick: () => this._deletePage() }, icon("mdi:delete")),
    ])));
    const exampleSel = el("select", { class: "ipx-input ipx-wide", onchange: (e) => this._loadExample(e.target.value) });
    exampleSel.appendChild(el("option", { value: "" }, "— starter examples —"));
    Object.keys(EXAMPLES).forEach((n) => exampleSel.appendChild(el("option", { value: n }, n)));
    left.appendChild(this._labeled("Examples (edit entity names!)", exampleSel));
    wrap.appendChild(left);

    // right: editor
    const right = el("div", { class: "ipx-pane ipx-grow" });
    this._segVisual = el("button", { class: "ipx-seg" + (this._mode === "visual" ? " active" : ""), onclick: () => this._setMode("visual") },
      [icon("mdi:view-dashboard-outline"), "Visual"]);
    this._segCode = el("button", { class: "ipx-seg" + (this._mode === "code" ? " active" : ""), onclick: () => this._setMode("code") },
      [icon("mdi:code-braces"), "Code (JSON)"]);
    right.appendChild(el("div", { class: "ipx-segment" }, [this._segVisual, this._segCode]));
    this._editor = el("div", { class: "ipx-editor" });
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

  // Only swaps the editor body + segment highlight — never re-appends the shell.
  _setMode(mode) {
    if (mode === this._mode) return;
    if (mode === "code") this._codeText = JSON.stringify(this._page, null, 2);
    this._mode = mode;
    if (this._segVisual) this._segVisual.classList.toggle("active", mode === "visual");
    if (this._segCode) this._segCode.classList.toggle("active", mode === "code");
    this._renderEditor();
  }

  _renderEditor() {
    if (!this._editor) return;
    this._editor.innerHTML = "";
    if (this._mode === "code") return this._renderCodeEditor();
    return this._renderVisualEditor();
  }

  _renderCodeEditor() {
    const ta = el("textarea", { class: "ipx-input ipx-code", spellcheck: "false" });
    ta.value = this._codeText != null ? this._codeText : JSON.stringify(this._page, null, 2);
    ta.addEventListener("input", () => { this._codeText = ta.value; });
    const apply = el("button", { class: "ipx-btn ipx-primary", onclick: () => {
      try { this._page = JSON.parse(ta.value); this._status("Applied."); this._schedulePreview(); }
      catch (e) { this._status("Invalid JSON: " + e.message, true); }
    } }, [icon("mdi:check"), "Apply"]);
    this._editor.appendChild(el("div", { class: "ipx-codewrap" }, [ta, el("div", { class: "ipx-flex" }, [apply])]));
  }

  _renderVisualEditor() {
    const wrap = el("div", { class: "ipx-vstack" });
    wrap.appendChild(this._colorField(this._page, "background", "Background", true));
    (this._page.widgets || []).forEach((w, i) => wrap.appendChild(this._widgetCard(w, i)));

    const addBar = el("div", { class: "ipx-addbar" });
    WIDGET_TYPES.forEach((t) => addBar.appendChild(el("button", { class: "ipx-btn ipx-add", title: "Add " + t, onclick: () => {
      this._page.widgets = this._page.widgets || [];
      this._page.widgets.push(this._defaultWidget(t));
      this._renderEditor(); this._schedulePreview();
    } }, [icon(WIDGET_ICON[t]), t])));
    wrap.appendChild(this._labeled("Add a widget", addBar));
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

  _widgetCard(w, i) {
    const card = el("div", { class: "ipx-wcard" });

    const typeSel = el("select", { class: "ipx-input" });
    WIDGET_TYPES.forEach((t) => typeSel.appendChild(el("option", { value: t, ...(t === w.type ? { selected: "" } : {}) }, t)));
    typeSel.addEventListener("change", () => { this._page.widgets[i] = this._defaultWidget(typeSel.value); this._renderEditor(); this._schedulePreview(); });

    const ctrls = el("div", { class: "ipx-wctrl" }, [
      el("button", { class: "ipx-iconbtn", title: "Move up", onclick: () => this._move(i, -1) }, icon("mdi:chevron-up")),
      el("button", { class: "ipx-iconbtn", title: "Move down", onclick: () => this._move(i, 1) }, icon("mdi:chevron-down")),
      el("button", { class: "ipx-iconbtn", title: "Duplicate", onclick: () => {
        this._page.widgets.splice(i + 1, 0, clone(this._page.widgets[i]));
        this._renderEditor(); this._schedulePreview();
      } }, icon("mdi:content-copy")),
      el("button", { class: "ipx-iconbtn ipx-danger", title: "Delete", onclick: () => {
        this._page.widgets.splice(i, 1); this._renderEditor(); this._schedulePreview();
      } }, icon("mdi:delete")),
    ]);
    card.appendChild(el("div", { class: "ipx-whead" }, [
      el("span", { class: "ipx-pill" }, String(i + 1)),
      icon(WIDGET_ICON[w.type] || "mdi:shape"),
      typeSel, ctrls,
    ]));

    const fields = el("div", { class: "ipx-fields" });
    if (!POSITIONLESS.has(w.type)) fields.appendChild(this._positionField(w));
    if (w.type !== "image") fields.appendChild(this._colorField(w, "color", "Colour"));
    for (const [key, kind, label] of (WIDGET_FIELDS[w.type] || [])) fields.appendChild(this._field(w, key, kind, label));
    const bindKey = w.type === "text" ? "text" : (w.type === "progress" ? "value" : null);
    if (bindKey) fields.appendChild(this._entityBind(w, bindKey));
    card.appendChild(fields);
    return card;
  }

  _positionField(w) {
    const usingAnchor = !!w.anchor || (w.x === undefined && w.y === undefined);
    const box = el("div", { class: "ipx-posbox" });
    box.appendChild(el("div", { class: "ipx-segment ipx-segsm" }, [
      el("button", { class: "ipx-seg" + (usingAnchor ? " active" : ""), onclick: () => {
        w.anchor = w.anchor || "center"; delete w.x; delete w.y; this._renderEditor(); this._schedulePreview();
      } }, "Anchor"),
      el("button", { class: "ipx-seg" + (!usingAnchor ? " active" : ""), onclick: () => {
        delete w.anchor; w.x = w.x || 0; w.y = w.y || 0; this._renderEditor(); this._schedulePreview();
      } }, "X / Y"),
    ]));
    if (usingAnchor) {
      if (!w.anchor) w.anchor = "center";
      const pad = el("div", { class: "ipx-anchorpad" });
      ANCHORS.forEach((a) => pad.appendChild(el("button", {
        class: "ipx-anchor" + (w.anchor === a ? " sel" : ""), title: a,
        onclick: () => { w.anchor = a; this._renderEditor(); this._schedulePreview(); },
      })));
      box.appendChild(pad);
      box.appendChild(el("div", { class: "ipx-flex" }, [this._field(w, "dx", "number", "± x"), this._field(w, "dy", "number", "± y")]));
    } else {
      box.appendChild(el("div", { class: "ipx-flex" }, [this._field(w, "x", "number", "x"), this._field(w, "y", "number", "y")]));
    }
    return this._labeled("Position", box);
  }

  // Colour picker + hex input (hex also accepts Jinja templates).
  _colorField(obj, key, label, full) {
    const val = obj[key] || "";
    const picker = el("input", { type: "color", class: "ipx-color", value: isHex6(val) ? "#" + val : "#000000" });
    const hex = el("input", { class: "ipx-input ipx-mono", type: "text", value: val, placeholder: "rrggbb / {{ }}", style: "width:130px;" });
    if (isTpl(val)) picker.setAttribute("disabled", "");
    picker.addEventListener("input", () => { obj[key] = picker.value.replace("#", ""); hex.value = obj[key]; this._schedulePreview(); });
    hex.addEventListener("input", () => {
      obj[key] = hex.value;
      if (isHex6(hex.value)) { picker.value = "#" + hex.value; picker.removeAttribute("disabled"); }
      else if (isTpl(hex.value)) picker.setAttribute("disabled", "");
      this._schedulePreview();
    });
    const node = el("div", { class: "ipx-flex" }, [picker, hex]);
    return el("label", { class: "ipx-lbl" + (full ? " ipx-wide" : "") }, [el("span", { class: "ipx-lblt" }, label), node]);
  }

  _entityBind(w, key) {
    const inp = el("input", { class: "ipx-input", list: "ipx-entities", placeholder: "bind HA entity…" });
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
      input = el("input", { type: "checkbox", class: "ipx-check" }); input.checked = !!w[key];
      input.addEventListener("change", () => { w[key] = input.checked; this._schedulePreview(); });
      return el("label", { class: "ipx-lbl ipx-inline" }, [input, el("span", { class: "ipx-lblt" }, label || key)]);
    } else if (kind === "font") {
      input = el("select", { class: "ipx-input" });
      FONTS.forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; if (FONT_SIZES[input.value]) w.size = FONT_SIZES[input.value]; this._renderEditor(); this._schedulePreview(); });
    } else if (kind === "fit") {
      input = el("select", { class: "ipx-input" });
      ["contain", "cover", "stretch"].forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; this._schedulePreview(); });
    } else {
      const num = kind === "number";
      input = el("input", { class: "ipx-input" + (num ? " ipx-num" : ""), type: num ? "number" : "text" });
      if (w[key] !== undefined) input.value = w[key];
      input.addEventListener("input", () => { w[key] = num ? (input.value === "" ? undefined : Number(input.value)) : input.value; this._schedulePreview(); });
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
      this._library[name] = clone(this._page);
      this._refreshLibraryList(); this._librarySel.value = name; this._status(`Saved “${name}”.`);
    } catch (e) { this._status("Save failed: " + e, true); }
  }
  _loadPage(name) {
    if (!name || !this._library[name]) return;
    this._page = clone(this._library[name]);
    if (this._nameInput) this._nameInput.value = name;
    this._codeText = null; this._renderEditor(); this._schedulePreview(); this._status(`Loaded “${name}”.`);
  }
  async _deletePage() {
    const name = this._librarySel.value; if (!name) return this._status("Pick a page to delete.", true);
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/delete", name });
      delete this._library[name]; this._refreshLibraryList(); this._status(`Deleted “${name}”.`);
    } catch (e) { this._status("Delete failed: " + e, true); }
  }
  _loadExample(name) {
    if (!name || !EXAMPLES[name]) return;
    this._page = clone(EXAMPLES[name]);
    this._codeText = null;
    if (this._mode !== "visual") this._setMode("visual"); else this._renderEditor();
    this._schedulePreview();
    this._status(`Loaded example “${name}” — change the entity names to yours.`);
  }
  async _sendNow() {
    if (!this._device) return this._status("No device selected.", true);
    this._status("Sending…");
    try {
      await this._hass.callService("ipixel_color", "show_page", { page: this._page }, { device_id: this._device });
      this._status("Sent to display.");
    } catch (e) { this._status("Send failed: " + e, true); }
  }

  // ============================================================ DRAW
  _tabDraw() {
    const wrap = el("div", { class: "ipx-cols" });

    const tools = el("div", { class: "ipx-pane ipx-side" });
    tools.appendChild(this._paneHead("Tools"));
    const pal = el("div", { class: "ipx-palette" });
    PALETTE.forEach((c) => {
      const sw = el("button", { class: "ipx-swatch", style: `background:#${c};`, title: c, onclick: () => { this._brush = c; this._markBrush(pal, c); this._status("Colour #" + c); } });
      sw.dataset.c = c;
      pal.appendChild(sw);
    });
    tools.appendChild(this._labeled("Palette", pal));
    const custom = el("input", { type: "color", class: "ipx-color", value: "#ff0000", oninput: (e) => { this._brush = e.target.value.replace("#", ""); this._markBrush(pal, null); } });
    tools.appendChild(this._labeled("Custom colour", custom));

    const live = el("input", { type: "checkbox", class: "ipx-check" });
    live.checked = this._liveDraw;
    live.addEventListener("change", async () => {
      this._liveDraw = live.checked;
      if (this._liveDraw && this._device) {
        await this._hass.callService("ipixel_color", "set_fun_mode", { enable: true }, { device_id: this._device });
        this._status("Live draw ON — DIY mode enabled on the panel.");
      }
    });

    tools.appendChild(el("div", { class: "ipx-flex ipx-toolbar" }, [
      el("button", { class: "ipx-btn", title: "Eraser", onclick: () => { this._brush = null; this._markBrush(pal, null); this._status("Eraser selected"); } }, [icon("mdi:eraser"), "Eraser"]),
      el("button", { class: "ipx-btn", title: "Clear", onclick: () => this._clearGrid() }, [icon("mdi:close-circle-outline"), "Clear"]),
    ]));
    tools.appendChild(el("label", { class: "ipx-lbl ipx-inline" }, [live, el("span", { class: "ipx-lblt" }, "Live draw (paint directly on panel)")]));
    tools.appendChild(el("button", { class: "ipx-btn ipx-primary ipx-wide", onclick: () => this._sendDrawing() }, [icon("mdi:send"), "Send drawing"]));
    tools.appendChild(el("div", { class: "ipx-hint" },
      "Click or drag to paint. “Send drawing” pushes the whole picture at once. " +
      "“Live draw” lights each pixel on the panel as you click (enables DIY mode)."));
    wrap.appendChild(tools);

    const gridWrap = el("div", { class: "ipx-pane ipx-grow" });
    gridWrap.appendChild(this._paneHead("Canvas", `${this._gw}×${this._gh}`));
    const cw = Math.max(4, Math.floor(384 / this._gw));
    this._gridEl = el("div", { class: "ipx-grid",
      style: `grid-template-columns:repeat(${this._gw},1fr);width:${this._gw * cw}px;height:${this._gh * cw}px;` });
    for (let i = 0; i < this._gw * this._gh; i++) {
      const c = this._grid[i];
      const cell = el("div", { class: "ipx-cell", "data-i": i, style: c ? `background:#${c};` : "" });
      this._gridEl.appendChild(cell);
    }
    this._gridEl.addEventListener("pointerdown", (e) => { this._painting = true; this._paintCell(e.target); e.preventDefault(); });
    this._gridEl.addEventListener("pointerover", (e) => { if (this._painting) this._paintCell(e.target); });
    window.addEventListener("pointerup", () => { this._painting = false; });
    gridWrap.appendChild(el("div", { class: "ipx-previewwrap" }, [this._gridEl]));
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
    if (this._grid[i] === this._brush) return;     // no change, don't re-send
    this._grid[i] = this._brush;                   // null = erase
    cell.setAttribute("style", this._brush ? `background:#${this._brush};` : "");
    if (this._liveDraw && this._device && this._brush) {
      const x = i % this._gw, y = Math.floor(i / this._gw);
      this._liveQueue.push({ x, y, color: this._brush });
      this._flushLive();
    }
  }

  // Send queued pixels one at a time so a fast drag can't flood the BLE link.
  async _flushLive() {
    if (this._liveFlushing) return;
    this._liveFlushing = true;
    while (this._liveQueue.length) {
      const p = this._liveQueue.shift();
      try {
        await this._hass.callService("ipixel_color", "set_pixel",
          { x: p.x, y: p.y, color: p.color }, { device_id: this._device });
      } catch (e) {
        this._status("set_pixel failed: " + e, true);
      }
    }
    this._liveFlushing = false;
  }

  async _sendDrawing() {
    if (!this._device) return this._status("No device selected.", true);
    this._status("Sending…");
    try {
      await this._hass.connection.sendMessagePromise({
        type: "ipixel_color/draw_grid", target: this._device,
        width: this._gw, height: this._gh, background: "000000",
        pixels: this._grid.map((c) => c || ""),
      });
      this._status("Drawing sent.");
    } catch (e) { this._status("Send failed: " + e, true); }
  }

  _clearGrid() {
    this._grid = new Array(this._gw * this._gh).fill(null);
    if (this._gridEl) [...this._gridEl.children].forEach((c) => c.setAttribute("style", ""));
    this._status("Cleared (press Send to blank the panel).");
  }

  // ============================================================ PLAYLIST
  _tabPlaylist() {
    const box = el("div", { class: "ipx-pane" });
    box.appendChild(this._paneHead("Auto-rotate pages"));
    box.appendChild(el("div", { class: "ipx-hint" },
      "Each page re-renders on its interval, so dynamic data stays live. " +
      "For a single live page, add just that one. For a pure clock, use show_clock."));

    this._plEnabled = el("input", { type: "checkbox", class: "ipx-check" });
    box.appendChild(el("label", { class: "ipx-lbl ipx-inline" }, [this._plEnabled, el("span", { class: "ipx-lblt" }, "Enabled")]));
    this._plTarget = el("select", { class: "ipx-input" });
    box.appendChild(this._labeled("Target device", this._plTarget));
    this._plList = el("div", { class: "ipx-vstack" });
    box.appendChild(this._plList);

    const addSel = el("select", { class: "ipx-input ipx-grow" });
    const names = Object.keys(this._library).sort();
    if (!names.length) addSel.appendChild(el("option", { value: "" }, "library empty"));
    names.forEach((n) => addSel.appendChild(el("option", { value: n }, n)));
    box.appendChild(this._labeled("Add page", el("div", { class: "ipx-flex" }, [
      addSel,
      el("button", { class: "ipx-btn", onclick: () => {
        if (!addSel.value) return;
        this._playlist.items = this._playlist.items || [];
        this._playlist.items.push({ name: addSel.value, duration: 10 });
        this._refreshPlaylist();
      } }, [icon("mdi:plus"), "Add"]),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._savePlaylist() }, [icon("mdi:content-save"), "Save playlist"]),
    ])));
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
    const items = this._playlist.items || [];
    if (!items.length) this._plList.appendChild(el("div", { class: "ipx-hint" }, "No pages yet — add some below."));
    items.forEach((it, i) => {
      const dur = el("input", { class: "ipx-input ipx-num", type: "number", value: it.duration });
      dur.addEventListener("input", () => { it.duration = Number(dur.value); });
      this._plList.appendChild(el("div", { class: "ipx-row" }, [
        el("span", { class: "ipx-pill" }, String(i + 1)),
        el("span", { class: "ipx-grow" }, it.name),
        this._labeled("seconds", dur),
        el("button", { class: "ipx-iconbtn ipx-danger", title: "Remove", onclick: () => { this._playlist.items.splice(i, 1); this._refreshPlaylist(); } }, icon("mdi:delete")),
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
    box.appendChild(this._paneHead("Device slots — native animation"));
    box.appendChild(el("div", { class: "ipx-hint" },
      "Save pages into the panel's own memory, then let it cycle them by itself — " +
      "no Home Assistant, no Bluetooth needed afterwards."));

    const names = Object.keys(this._library).sort();
    if (!names.length) box.appendChild(el("div", { class: "ipx-hint" }, "Save some pages in the Designer first."));
    names.forEach((n) => {
      const slot = el("input", { class: "ipx-input ipx-num", type: "number", min: 1, max: 255, value: 1 });
      box.appendChild(el("div", { class: "ipx-row" }, [
        el("span", { class: "ipx-grow" }, n),
        this._labeled("slot", slot),
        el("button", { class: "ipx-btn", onclick: () => this._saveToSlot(n, +slot.value) }, [icon("mdi:content-save"), "Save to slot"]),
      ]));
    });

    box.appendChild(el("hr", { class: "ipx-hr" }));
    box.appendChild(el("b", {}, "Cycle slots (animation)"));
    const order = el("input", { class: "ipx-input", type: "text", placeholder: "1,2,3", style: "width:120px;" });
    box.appendChild(el("div", { class: "ipx-flex" }, [
      this._labeled("order", order),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._startProgram(order.value) }, [icon("mdi:play"), "Start cycling"]),
    ]));

    const one = el("input", { class: "ipx-input ipx-num", type: "number", min: 0, max: 255, value: 1 });
    box.appendChild(el("div", { class: "ipx-flex", style: "margin-top:6px;" }, [
      this._labeled("slot", one),
      el("button", { class: "ipx-btn", onclick: () => this._svc("show_slot", { slot: +one.value }) }, "Show slot"),
      el("button", { class: "ipx-iconbtn ipx-danger", title: "Delete slot", onclick: () => this._svc("delete_slot", { slot: +one.value }) }, icon("mdi:delete")),
    ]));
    this._content.appendChild(box);
  }

  async _saveToSlot(name, slot) {
    const page = this._library[name];
    if (!page) return;
    if (!this._device) return this._status("No device selected.", true);
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
    box.appendChild(this._paneHead("Device controls"));
    const ents = this._deviceEntities();
    if (!ents.length) box.appendChild(el("div", { class: "ipx-hint" }, "No controllable entities found for this device."));
    ents.forEach((eid) => {
      const st = this._hass.states[eid];
      if (!st) return;
      const domain = eid.split(".")[0];
      const label = (st.attributes && st.attributes.friendly_name) || eid;
      let control = null;
      if (domain === "switch") {
        let on = st.state === "on";
        const btn = el("button", { class: "ipx-btn" + (on ? " ipx-primary" : ""), onclick: () => {
          on = !on;
          btn.classList.toggle("ipx-primary", on);
          btn.textContent = on ? "ON" : "OFF";
          this._hass.callService("switch", on ? "turn_on" : "turn_off", {}, { entity_id: eid })
            .catch((e) => this._status(label + ": " + e, true));
        } }, on ? "ON" : "OFF");
        control = btn;
      } else if (domain === "number") {
        const a = st.attributes || {};
        const rng = el("input", { type: "range", class: "ipx-range", min: a.min ?? 1, max: a.max ?? 100, step: a.step ?? 1, value: st.state });
        const val = el("span", { class: "ipx-val" }, st.state);
        rng.addEventListener("input", () => { val.textContent = rng.value; });
        rng.addEventListener("change", () => { this._hass.callService("number", "set_value", { value: Number(rng.value) }, { entity_id: eid }); });
        control = el("div", { class: "ipx-flex ipx-grow" }, [rng, val]);
      } else if (domain === "select") {
        const sel = el("select", { class: "ipx-input" });
        (st.attributes.options || []).forEach((o) => sel.appendChild(el("option", { value: o, ...(o === st.state ? { selected: "" } : {}) }, o)));
        sel.addEventListener("change", () => this._hass.callService("select", "select_option", { option: sel.value }, { entity_id: eid }));
        control = sel;
      }
      if (control) box.appendChild(el("div", { class: "ipx-row" }, [el("span", { class: "ipx-grow" }, label), control]));
    });

    box.appendChild(el("hr", { class: "ipx-hr" }));
    box.appendChild(el("b", {}, "Rhythm / visualizer"));
    const style = el("input", { class: "ipx-input ipx-num", type: "number", min: 0, max: 1, value: 1 });
    const frame = el("input", { class: "ipx-input ipx-num", type: "number", min: 0, max: 7, value: 3 });
    box.appendChild(el("div", { class: "ipx-flex" }, [
      this._labeled("style", style), this._labeled("frame", frame),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._svc("set_rhythm_animation", { style: +style.value, frame: +frame.value }) }, [icon("mdi:play"), "Play animation"]),
    ]));
    box.appendChild(el("div", { class: "ipx-hint" }, "Self-contained visualizer (no audio source needed)."));
    this._content.appendChild(box);
  }

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
      .ipx-root{padding:16px;display:flex;flex-direction:column;gap:14px;
        --ipx-radius:14px;--ipx-radius-sm:9px;}
      .ipx-root *{box-sizing:border-box;}
      .ipx-head{display:flex;align-items:center;gap:12px;justify-content:space-between;flex-wrap:wrap;}
      .ipx-brand{display:flex;align-items:center;gap:8px;}
      .ipx-brand ha-icon{color:var(--primary-color);}
      .ipx-title{font-size:20px;font-weight:700;letter-spacing:.2px;}
      .ipx-ic{--mdc-icon-size:18px;width:18px;height:18px;flex:none;}

      .ipx-tabs{display:flex;gap:4px;flex-wrap:wrap;background:var(--secondary-background-color);
        padding:4px;border-radius:var(--ipx-radius);}
      .ipx-tab{display:flex;align-items:center;gap:6px;padding:8px 14px;border:none;border-radius:10px;
        cursor:pointer;font:inherit;background:transparent;color:var(--secondary-text-color);
        transition:background .15s,color .15s;}
      .ipx-tab:hover{color:var(--primary-text-color);}
      .ipx-tab.active{background:var(--card-background-color);color:var(--primary-color);
        font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.12);}
      .ipx-tab.active ha-icon{color:var(--primary-color);}

      .ipx-content{min-height:200px;}
      .ipx-cols{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;}
      .ipx-side{width:300px;}
      .ipx-pane{display:flex;flex-direction:column;gap:12px;padding:14px;
        border:1px solid var(--divider-color);border-radius:var(--ipx-radius);
        background:var(--card-background-color);box-shadow:0 1px 2px rgba(0,0,0,.06);}
      .ipx-grow{flex:1;min-width:300px;}
      .ipx-paneh{display:flex;align-items:baseline;gap:8px;font-weight:600;font-size:15px;}
      .ipx-paneh .ipx-sub{font-weight:400;font-size:12px;color:var(--secondary-text-color);}

      .ipx-input{padding:7px 9px;border:1px solid var(--divider-color);border-radius:var(--ipx-radius-sm);
        background:var(--card-background-color);color:var(--primary-text-color);font:inherit;min-width:0;}
      .ipx-input:focus{outline:none;border-color:var(--primary-color);}
      .ipx-num{width:74px;}
      .ipx-mono{font-family:var(--code-font-family,monospace);}
      select.ipx-input{cursor:pointer;}

      .ipx-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 13px;border:1px solid var(--divider-color);
        border-radius:var(--ipx-radius-sm);cursor:pointer;background:var(--card-background-color);
        color:var(--primary-text-color);font:inherit;transition:transform .05s,box-shadow .15s,background .15s;}
      .ipx-btn:hover{box-shadow:0 2px 6px rgba(0,0,0,.12);}
      .ipx-btn:active{transform:translateY(1px);}
      .ipx-primary{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:transparent;}
      .ipx-danger:hover{color:var(--error-color);}
      .ipx-wide{width:100%;justify-content:center;}
      .ipx-add{text-transform:capitalize;}
      .ipx-iconbtn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;flex:none;
        border:1px solid var(--divider-color);border-radius:var(--ipx-radius-sm);cursor:pointer;
        background:var(--card-background-color);color:var(--primary-text-color);transition:background .15s,color .15s;}
      .ipx-iconbtn:hover{background:var(--secondary-background-color);}

      .ipx-flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
      .ipx-toolbar{margin-top:2px;}
      .ipx-vstack{display:flex;flex-direction:column;gap:10px;}
      .ipx-addbar{display:flex;gap:6px;flex-wrap:wrap;}

      .ipx-segment{display:inline-flex;gap:0;background:var(--secondary-background-color);
        border-radius:var(--ipx-radius-sm);padding:3px;}
      .ipx-seg{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border:none;border-radius:7px;
        cursor:pointer;font:inherit;background:transparent;color:var(--secondary-text-color);transition:all .15s;}
      .ipx-seg.active{background:var(--card-background-color);color:var(--primary-color);font-weight:600;
        box-shadow:0 1px 2px rgba(0,0,0,.12);}
      .ipx-segsm .ipx-seg{padding:5px 10px;font-size:12px;}

      .ipx-lbl{font-size:12px;color:var(--secondary-text-color);display:flex;flex-direction:column;gap:4px;}
      .ipx-lbl.ipx-inline{flex-direction:row;align-items:center;gap:8px;cursor:pointer;}
      .ipx-lblt{font-weight:500;}

      .ipx-previewwrap{display:flex;justify-content:center;padding:10px;border-radius:var(--ipx-radius-sm);
        background:
          linear-gradient(45deg,#2b2b2b 25%,transparent 25%),
          linear-gradient(-45deg,#2b2b2b 25%,transparent 25%),
          linear-gradient(45deg,transparent 75%,#2b2b2b 75%),
          linear-gradient(-45deg,transparent 75%,#2b2b2b 75%);
        background-size:16px 16px;background-position:0 0,0 8px,8px -8px,-8px 0;background-color:#1b1b1b;}
      .ipx-preview{image-rendering:pixelated;border-radius:4px;box-shadow:0 2px 10px rgba(0,0,0,.4);}

      .ipx-status{min-height:20px;font-size:12.5px;color:var(--secondary-text-color);padding-left:2px;}
      .ipx-status.ok{color:var(--success-color,#3c3);}
      .ipx-status.err{color:var(--error-color);}

      .ipx-wcard{border:1px solid var(--divider-color);border-left:3px solid var(--primary-color);
        border-radius:var(--ipx-radius-sm);background:var(--secondary-background-color);overflow:hidden;}
      .ipx-whead{display:flex;align-items:center;gap:8px;padding:8px 10px;
        background:var(--card-background-color);border-bottom:1px solid var(--divider-color);}
      .ipx-whead select{flex:1;}
      .ipx-wctrl{display:flex;gap:4px;margin-left:auto;}
      .ipx-wctrl .ipx-iconbtn{width:30px;height:30px;}
      .ipx-fields{display:flex;flex-wrap:wrap;gap:10px 14px;padding:12px;}
      .ipx-pill{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;padding:0 6px;
        font-size:11px;font-weight:700;border-radius:11px;background:var(--primary-color);color:var(--text-primary-color,#fff);}

      .ipx-posbox{display:flex;flex-direction:column;gap:8px;}
      .ipx-anchorpad{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;width:78px;}
      .ipx-anchor{width:22px;height:22px;border:1px solid var(--divider-color);border-radius:5px;cursor:pointer;
        background:var(--card-background-color);padding:0;transition:all .12s;}
      .ipx-anchor:hover{border-color:var(--primary-color);}
      .ipx-anchor.sel{background:var(--primary-color);border-color:transparent;box-shadow:0 0 0 2px var(--primary-color) inset;}

      .ipx-color{width:42px;height:34px;padding:2px;border:1px solid var(--divider-color);
        border-radius:var(--ipx-radius-sm);background:var(--card-background-color);cursor:pointer;flex:none;}
      .ipx-check{width:18px;height:18px;accent-color:var(--primary-color);cursor:pointer;}
      .ipx-range{accent-color:var(--primary-color);flex:1;min-width:120px;}

      textarea.ipx-code{width:100%;min-height:300px;font-family:var(--code-font-family,monospace);
        font-size:13px;line-height:1.5;resize:vertical;}
      .ipx-codewrap{display:flex;flex-direction:column;gap:10px;}
      .ipx-hint{font-size:12px;color:var(--secondary-text-color);line-height:1.5;}

      .ipx-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:9px 11px;
        border:1px solid var(--divider-color);border-radius:var(--ipx-radius-sm);background:var(--secondary-background-color);}
      .ipx-palette{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;max-width:210px;}
      .ipx-swatch{width:28px;height:28px;border-radius:7px;border:2px solid transparent;cursor:pointer;
        box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .08s;}
      .ipx-swatch:hover{transform:scale(1.08);}
      .ipx-swatch.sel{border-color:var(--primary-text-color,#fff);outline:2px solid var(--primary-color);}
      .ipx-grid{display:grid;gap:0;border:1px solid var(--divider-color);background:#000;touch-action:none;
        user-select:none;border-radius:4px;overflow:hidden;}
      .ipx-cell{border:1px solid rgba(128,128,128,.12);background:transparent;}
      .ipx-val{min-width:34px;text-align:right;font-variant-numeric:tabular-nums;}
      .ipx-hr{border:none;border-top:1px solid var(--divider-color);width:100%;margin:6px 0;}

      @media (max-width:680px){
        .ipx-side{width:100%;}
        .ipx-tab span{display:none;}
        .ipx-tab{padding:8px 12px;}
      }
    `);
  }
}

customElements.define("ipixel-card", IPixelCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "ipixel-card", name: "iPIXEL Studio",
  description: "Design pages, draw pixels, manage playlists/slots and control your iPIXEL panel." });
console.info("%c iPIXEL-CARD ", "background:#222;color:#0cf", "loaded (studio v2)");
