/* iPIXEL Enhanced — page designer card
 * Visual widget editor + live 32x32 preview + page library + playlist.
 * Plain custom element (no build step, no external deps).
 */

const PREVIEW_SCALE = 8;
const ANCHORS = [
  "top_left", "top_center", "top_right",
  "center_left", "center", "center_right",
  "bottom_left", "bottom_center", "bottom_right",
];
const FONTS = ["5x5", "7x5", "3x5-de", "WP7xn", "OpenSans-Light", "NotoColorEmoji"];

// Which editable fields each widget type exposes, beyond the common ones.
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
const POSITIONLESS = new Set(["line"]); // uses x/y directly

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

class IPixelCard extends HTMLElement {
  constructor() {
    super();
    this._page = { background: "000000", widgets: [] };
    this._mode = "visual";
    this._devices = [];
    this._library = {};
    this._playlist = { enabled: false, items: [], target: null };
    this._device = null;
    this._previewTimer = null;
    this._built = false;
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

  getCardSize() { return 12; }

  // ---- server calls ----
  async _loadLibrary() {
    try {
      const res = await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/list" });
      this._library = res.pages || {};
      this._playlist = res.playlist || this._playlist;
      this._devices = res.devices || [];
      if (!this._device && this._devices.length) this._device = this._devices[0].id;
      this._refreshDeviceList();
      this._refreshLibraryList();
      this._refreshPlaylist();
    } catch (e) {
      this._status("Could not reach the integration: " + e, true);
    }
  }

  _schedulePreview() {
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._renderPreview(), 250);
  }

  async _renderPreview() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callApi("POST", "ipixel_color/preview", {
        page: this._page, width: 32, height: 32, scale: PREVIEW_SCALE,
      });
      this._img.src = res.image;
    } catch (e) {
      this._status("Preview error: " + (e.body && e.body.message ? e.body.message : e), true);
    }
  }

  // ---- UI build ----
  _build() {
    const card = el("ha-card", { header: "iPIXEL — Page designer" });
    const root = el("div", { style: "padding:12px;display:flex;flex-direction:column;gap:12px;" });

    // preview + device row
    const top = el("div", { style: "display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;" });
    this._img = el("img", {
      style: `width:${32 * PREVIEW_SCALE}px;height:${32 * PREVIEW_SCALE}px;image-rendering:pixelated;` +
             "background:#111;border:1px solid var(--divider-color);border-radius:6px;",
    });
    const right = el("div", { style: "flex:1;min-width:240px;display:flex;flex-direction:column;gap:8px;" });

    this._deviceSel = el("select", { class: "ipx-input", onchange: (e) => { this._device = e.target.value; } });
    right.appendChild(this._labeled("Device", this._deviceSel));

    const sendRow = el("div", { style: "display:flex;gap:8px;" }, [
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._sendNow() }, "Send now"),
    ]);
    right.appendChild(sendRow);

    // library
    this._nameInput = el("input", { class: "ipx-input", type: "text", placeholder: "page name" });
    this._librarySel = el("select", { class: "ipx-input", onchange: (e) => this._loadPage(e.target.value) });
    right.appendChild(this._labeled("Save as", el("div", { style: "display:flex;gap:6px;" }, [
      this._nameInput,
      el("button", { class: "ipx-btn", onclick: () => this._savePage() }, "Save"),
    ])));
    right.appendChild(this._labeled("Load", el("div", { style: "display:flex;gap:6px;" }, [
      this._librarySel,
      el("button", { class: "ipx-btn", onclick: () => this._deletePage() }, "Delete"),
    ])));

    top.appendChild(this._img);
    top.appendChild(right);
    root.appendChild(top);

    this._statusBar = el("div", { style: "min-height:18px;font-size:12px;color:var(--secondary-text-color);" });
    root.appendChild(this._statusBar);

    // mode tabs
    const tabs = el("div", { style: "display:flex;gap:6px;" }, [
      el("button", { class: "ipx-btn", onclick: () => this._setMode("visual") }, "Visual editor"),
      el("button", { class: "ipx-btn", onclick: () => this._setMode("code") }, "Code (JSON)"),
    ]);
    root.appendChild(tabs);

    // editor container (visual or code)
    this._editor = el("div", {});
    root.appendChild(this._editor);

    // playlist section
    root.appendChild(this._buildPlaylistSection());

    card.appendChild(root);
    card.appendChild(this._styles());
    this.appendChild(card);

    this._renderEditor();
    this._renderPreview();
  }

  _styles() {
    return el("style", {}, `
      .ipx-input{padding:4px 6px;border:1px solid var(--divider-color);border-radius:4px;
        background:var(--card-background-color);color:var(--primary-text-color);font:inherit;}
      .ipx-btn{padding:5px 10px;border:1px solid var(--divider-color);border-radius:4px;cursor:pointer;
        background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit;}
      .ipx-btn:hover{filter:brightness(1.1);}
      .ipx-primary{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:transparent;}
      .ipx-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:6px;border:1px solid var(--divider-color);
        border-radius:6px;margin-bottom:6px;}
      .ipx-lbl{font-size:12px;color:var(--secondary-text-color);display:flex;flex-direction:column;gap:2px;}
      textarea.ipx-input{width:100%;min-height:240px;font-family:monospace;}
      .ipx-pill{font-size:11px;padding:1px 6px;border-radius:10px;background:var(--primary-color);color:#fff;}
    `);
  }

  _labeled(text, node) {
    return el("label", { class: "ipx-lbl" }, [text, node]);
  }

  _status(msg, isError) {
    this._statusBar.textContent = msg || "";
    this._statusBar.style.color = isError ? "var(--error-color)" : "var(--secondary-text-color)";
  }

  _refreshDeviceList() {
    this._deviceSel.innerHTML = "";
    if (!this._devices.length) {
      this._deviceSel.appendChild(el("option", { value: "" }, "no device"));
      return;
    }
    for (const d of this._devices) {
      this._deviceSel.appendChild(el("option", { value: d.id }, d.name));
    }
    if (this._device) this._deviceSel.value = this._device;
  }

  _refreshLibraryList() {
    const names = Object.keys(this._library).sort();
    this._librarySel.innerHTML = "";
    this._librarySel.appendChild(el("option", { value: "" }, names.length ? "— pick a page —" : "library empty"));
    for (const n of names) this._librarySel.appendChild(el("option", { value: n }, n));
  }

  // ---- editor (visual + code) ----
  _setMode(mode) {
    if (mode === "code") this._codeText = JSON.stringify(this._page, null, 2);
    this._mode = mode;
    this._renderEditor();
  }

  _renderEditor() {
    this._editor.innerHTML = "";
    if (this._mode === "code") return this._renderCodeEditor();
    return this._renderVisualEditor();
  }

  _renderCodeEditor() {
    const ta = el("textarea", { class: "ipx-input" });
    ta.value = this._codeText != null ? this._codeText : JSON.stringify(this._page, null, 2);
    ta.addEventListener("input", () => { this._codeText = ta.value; });
    const apply = el("button", { class: "ipx-btn ipx-primary", onclick: () => {
      try {
        this._page = JSON.parse(ta.value);
        this._status("Applied.");
        this._schedulePreview();
      } catch (e) { this._status("Invalid JSON: " + e.message, true); }
    } }, "Apply");
    this._editor.appendChild(el("div", { style: "display:flex;flex-direction:column;gap:6px;" }, [ta, apply]));
  }

  _renderVisualEditor() {
    const wrap = el("div", {});

    const bg = el("input", { class: "ipx-input", type: "text", value: this._page.background || "000000" });
    bg.addEventListener("input", () => { this._page.background = bg.value; this._schedulePreview(); });
    wrap.appendChild(el("div", { class: "ipx-row" }, [this._labeled("Background", bg)]));

    (this._page.widgets || []).forEach((w, i) => wrap.appendChild(this._widgetRow(w, i)));

    const addSel = el("select", { class: "ipx-input" });
    WIDGET_TYPES.forEach((t) => addSel.appendChild(el("option", { value: t }, t)));
    const addBtn = el("button", { class: "ipx-btn ipx-primary", onclick: () => {
      this._page.widgets = this._page.widgets || [];
      this._page.widgets.push(this._defaultWidget(addSel.value));
      this._renderEditor();
      this._schedulePreview();
    } }, "+ Add widget");
    wrap.appendChild(el("div", { style: "display:flex;gap:6px;margin-top:6px;" }, [addSel, addBtn]));

    this._editor.appendChild(wrap);
  }

  _defaultWidget(type) {
    const w = { type, anchor: "center", color: "ffffff" };
    if (type === "text") { w.text = "Hello"; w.font = "5x5"; w.size = 5; }
    if (type === "emoji") { w.emoji = "⭐"; w.size = 12; }
    if (type === "clock") { w.format = "%H:%M"; w.font = "5x5"; w.size = 5; }
    if (type === "line") { delete w.anchor; w.x = 0; w.y = 16; w.x2 = 31; w.y2 = 16; w.color = "888888"; }
    if (type === "rect") { w.width = 8; w.height = 8; w.fill = true; }
    if (type === "progress") { w.value = "50"; w.width = 30; w.height = 4; w.color = "00cc33"; }
    if (type === "image") { w.src = "/local/"; w.width = 32; w.height = 32; w.fit = "contain"; }
    return w;
  }

  _widgetRow(w, i) {
    const row = el("div", { class: "ipx-row" });
    row.appendChild(el("span", { class: "ipx-pill" }, w.type));

    // type switcher
    const typeSel = el("select", { class: "ipx-input" });
    WIDGET_TYPES.forEach((t) => typeSel.appendChild(el("option", { value: t, ...(t === w.type ? { selected: "" } : {}) }, t)));
    typeSel.addEventListener("change", () => {
      this._page.widgets[i] = this._defaultWidget(typeSel.value);
      this._renderEditor(); this._schedulePreview();
    });
    row.appendChild(this._labeled("type", typeSel));

    // position (anchor or x/y) unless the widget is positionless
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
      if (!w.anchor) {
        row.appendChild(this._field(w, "x", "number", "x"));
        row.appendChild(this._field(w, "y", "number", "y"));
      } else {
        row.appendChild(this._field(w, "dx", "number", "dx"));
        row.appendChild(this._field(w, "dy", "number", "dy"));
      }
    }

    // colour (most widgets)
    if (w.type !== "image") row.appendChild(this._field(w, "color", "text", "color"));

    // type-specific fields
    for (const [key, kind, label] of (WIDGET_FIELDS[w.type] || [])) {
      row.appendChild(this._field(w, key, kind, label));
    }

    // controls
    const ctrl = el("div", { style: "margin-left:auto;display:flex;gap:4px;" }, [
      el("button", { class: "ipx-btn", onclick: () => this._move(i, -1) }, "↑"),
      el("button", { class: "ipx-btn", onclick: () => this._move(i, 1) }, "↓"),
      el("button", { class: "ipx-btn", onclick: () => { this._page.widgets.splice(i, 1); this._renderEditor(); this._schedulePreview(); } }, "✕"),
    ]);
    row.appendChild(ctrl);
    return row;
  }

  _field(w, key, kind, label) {
    let input;
    if (kind === "bool") {
      input = el("input", { type: "checkbox" });
      input.checked = !!w[key];
      input.addEventListener("change", () => { w[key] = input.checked; this._schedulePreview(); });
    } else if (kind === "font") {
      input = el("select", { class: "ipx-input" });
      FONTS.forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; this._schedulePreview(); });
    } else if (kind === "fit") {
      input = el("select", { class: "ipx-input" });
      ["contain", "cover", "stretch"].forEach((f) => input.appendChild(el("option", { value: f, ...(w[key] === f ? { selected: "" } : {}) }, f)));
      input.addEventListener("change", () => { w[key] = input.value; this._schedulePreview(); });
    } else {
      input = el("input", { class: "ipx-input", type: kind === "number" ? "number" : "text", style: "width:90px;" });
      if (w[key] !== undefined) input.value = w[key];
      input.addEventListener("input", () => {
        w[key] = kind === "number" ? (input.value === "" ? undefined : Number(input.value)) : input.value;
        this._schedulePreview();
      });
    }
    return this._labeled(label || key, input);
  }

  _move(i, dir) {
    const j = i + dir;
    const a = this._page.widgets;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]];
    this._renderEditor(); this._schedulePreview();
  }

  // ---- library actions ----
  async _savePage() {
    const name = (this._nameInput.value || "").trim();
    if (!name) return this._status("Enter a page name first.", true);
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/save", name, page: this._page });
      this._library[name] = JSON.parse(JSON.stringify(this._page));
      this._refreshLibraryList();
      this._status(`Saved “${name}”.`);
    } catch (e) { this._status("Save failed: " + e, true); }
  }

  _loadPage(name) {
    if (!name || !this._library[name]) return;
    this._page = JSON.parse(JSON.stringify(this._library[name]));
    this._nameInput.value = name;
    this._codeText = null;
    this._renderEditor();
    this._schedulePreview();
    this._status(`Loaded “${name}”.`);
  }

  async _deletePage() {
    const name = this._librarySel.value;
    if (!name) return;
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/pages/delete", name });
      delete this._library[name];
      this._refreshLibraryList();
      this._status(`Deleted “${name}”.`);
    } catch (e) { this._status("Delete failed: " + e, true); }
  }

  async _sendNow() {
    if (!this._device) return this._status("No device selected.", true);
    try {
      await this._hass.callService("ipixel_color", "show_page", { page: this._page }, { device_id: this._device });
      this._status("Sent to display.");
    } catch (e) { this._status("Send failed: " + e, true); }
  }

  // ---- playlist ----
  _buildPlaylistSection() {
    const box = el("div", { style: "border-top:1px solid var(--divider-color);padding-top:10px;display:flex;flex-direction:column;gap:8px;" });
    box.appendChild(el("b", {}, "Playlist (auto-rotate pages)"));
    this._plEnabled = el("input", { type: "checkbox" });
    this._plList = el("div", {});
    this._plTarget = el("select", { class: "ipx-input" });

    box.appendChild(el("label", { class: "ipx-lbl", style: "flex-direction:row;align-items:center;gap:6px;" }, [this._plEnabled, "Enabled"]));
    box.appendChild(this._labeled("Target device", this._plTarget));
    box.appendChild(this._plList);

    const addSel = el("select", { class: "ipx-input" });
    const refreshAdd = () => {
      addSel.innerHTML = "";
      Object.keys(this._library).sort().forEach((n) => addSel.appendChild(el("option", { value: n }, n)));
    };
    this._refreshPlaylistAddSel = refreshAdd;

    box.appendChild(el("div", { style: "display:flex;gap:6px;" }, [
      addSel,
      el("button", { class: "ipx-btn", onclick: () => {
        if (!addSel.value) return;
        this._playlist.items = this._playlist.items || [];
        this._playlist.items.push({ name: addSel.value, duration: 10 });
        this._refreshPlaylist();
      } }, "+ Add to playlist"),
      el("button", { class: "ipx-btn ipx-primary", onclick: () => this._savePlaylist() }, "Save playlist"),
    ]));
    return box;
  }

  _refreshPlaylist() {
    if (!this._plList) return;
    this._plEnabled.checked = !!this._playlist.enabled;
    this._plTarget.innerHTML = "";
    this._plTarget.appendChild(el("option", { value: "" }, "first device"));
    for (const d of this._devices) {
      this._plTarget.appendChild(el("option", { value: d.id, ...(this._playlist.target === d.id ? { selected: "" } : {}) }, d.name));
    }
    this._plList.innerHTML = "";
    (this._playlist.items || []).forEach((it, i) => {
      const dur = el("input", { class: "ipx-input", type: "number", value: it.duration, style: "width:70px;" });
      dur.addEventListener("input", () => { it.duration = Number(dur.value); });
      this._plList.appendChild(el("div", { class: "ipx-row" }, [
        el("span", {}, `${i + 1}. ${it.name}`),
        this._labeled("seconds", dur),
        el("button", { class: "ipx-btn", style: "margin-left:auto;", onclick: () => { this._playlist.items.splice(i, 1); this._refreshPlaylist(); } }, "✕"),
      ]));
    });
    if (this._refreshPlaylistAddSel) this._refreshPlaylistAddSel();
  }

  async _savePlaylist() {
    this._playlist.enabled = this._plEnabled.checked;
    this._playlist.target = this._plTarget.value || null;
    try {
      await this._hass.connection.sendMessagePromise({ type: "ipixel_color/playlist/set", playlist: this._playlist });
      this._status("Playlist saved.");
    } catch (e) { this._status("Playlist save failed: " + e, true); }
  }
}

customElements.define("ipixel-card", IPixelCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ipixel-card",
  name: "iPIXEL Page Designer",
  description: "Design pages with live 32x32 preview and push them to your iPIXEL display.",
});
console.info("%c iPIXEL-CARD ", "background:#222;color:#0cf", "loaded");
