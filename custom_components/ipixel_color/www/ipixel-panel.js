/* iPIXEL Enhanced — sidebar panel.
 * Thin wrapper that hosts the <ipixel-card> designer as a full page so the
 * tool is discoverable from the HA sidebar (no manual Lovelace card needed).
 * It loads the card itself if it isn't defined yet, so it no longer depends on
 * add_extra_js_url having run first.
 */
// Load the card from the same folder, carrying over our own ?v= cache-buster
// so an upgrade always fetches the matching card.
const HERE = new URL(import.meta.url);
const CARD_URL = new URL("ipixel-card.js" + HERE.search, HERE).href;

async function ensureCard() {
  if (customElements.get("ipixel-card")) return;
  try {
    await import(CARD_URL);
  } catch (e) {
    console.error("iPIXEL panel: could not load the card module", e);
  }
}

class IPixelPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._mounting) {
      this._mounting = ensureCard().then(() => this._mount(hass));
    } else if (this._card) {
      this._card.hass = hass;
    }
  }
  _mount(hass) {
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
