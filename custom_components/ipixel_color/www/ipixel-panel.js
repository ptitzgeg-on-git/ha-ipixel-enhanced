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
      // Full-height surface that adopts the active HA theme, with the designer
      // centred and a comfortable max width on desktop.
      this.style.cssText =
        "display:block;min-height:100%;box-sizing:border-box;" +
        "background:var(--primary-background-color);color:var(--primary-text-color);";
      this._wrap = document.createElement("div");
      this._card = document.createElement("ipixel-card");
      if (typeof this._card.setConfig === "function") this._card.setConfig({});
      this._wrap.appendChild(this._card);
      this.appendChild(this._wrap);
      this._applyLayout();
    }
    this._card.hass = hass;
  }
  // Tighten padding and drop the max width when HA reports a narrow viewport
  // (mobile / collapsed sidebar) so the grid uses the full screen.
  _applyLayout() {
    if (!this._wrap) return;
    const pad = this._narrow ? "8px" : "16px";
    const maxw = this._narrow ? "100%" : "960px";
    this._wrap.style.cssText = `max-width:${maxw};margin:0 auto;padding:${pad};`;
  }
  set narrow(v) { this._narrow = v; this._applyLayout(); }
  set route(v) { this._route = v; }
  set panel(v) { this._panel = v; }
}

if (!customElements.get("ipixel-panel")) {
  customElements.define("ipixel-panel", IPixelPanel);
}
