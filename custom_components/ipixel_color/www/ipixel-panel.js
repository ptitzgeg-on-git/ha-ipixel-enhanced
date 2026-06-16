/* iPIXEL Enhanced — sidebar panel.
 * Thin wrapper that hosts the <ipixel-card> designer as a full page so the
 * tool is discoverable from the HA sidebar (no manual Lovelace card needed).
 * The card element is loaded globally via add_extra_js_url.
 */
class IPixelPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._card) {
      const wrap = document.createElement("div");
      wrap.style.cssText = "max-width:920px;margin:0 auto;padding:16px;";
      this._card = document.createElement("ipixel-card");
      if (typeof this._card.setConfig === "function") this._card.setConfig({});
      wrap.appendChild(this._card);
      this.appendChild(wrap);
    }
    this._card.hass = hass;
  }
  set narrow(v) { this._narrow = v; }
  set route(v) { this._route = v; }
  set panel(v) { this._panel = v; }
}

if (!customElements.get("ipixel-panel")) {
  customElements.define("ipixel-panel", IPixelPanel);
}
