/* CC Installer - TSR Community Manager */

function toast(message, kind = "info") {
  const host = document.getElementById("toasts");
  if (!host) return;
  const el = document.createElement("div");
  el.className = `toast${kind === "error" ? " error" : kind === "success" ? " success" : ""}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function proxied(url) {
  if (!url) return "";
  return `/api/image?url=${encodeURIComponent(url)}`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function formatArtist(artist) {
  if (!artist) return null;
  const name = String(artist).replace(/^by\s+/i, "").trim();
  return name ? `By ${name}` : null;
}

function artistHref(slug) {
  if (!slug) return "";
  return `/artist/${encodeURIComponent(slug)}`;
}

function artistName(artist) {
  return String(artist || "").replace(/^by\s+/i, "").trim();
}

function slugFromCreatorInput(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const fromUrl = raw.match(/members\/([^/?#]+)/i);
  if (fromUrl) return fromUrl[1];
  return raw.replace(/\s+/g, "_");
}

const BrowseMenu = {
  open: false,

  init() {
    const trigger = document.getElementById("browse-trigger");
    const panel = document.getElementById("browse-panel");
    if (!trigger || !panel) return;

    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.toggle();
    });
    panel.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", (e) => {
      if (!this.open) return;
      if (e.target.closest("#browse-menu")) return;
      this.close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.close();
    });

    panel.querySelectorAll(".browse-tab").forEach((tab) => {
      tab.addEventListener("click", () => this.showTab(tab.dataset.tab));
    });
    panel.querySelectorAll(".cat-link").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.selectCategory(btn.dataset.path, btn.dataset.label);
      });
    });
    document.getElementById("creator-go")?.addEventListener("click", () => this.goCreator());
    document.getElementById("creator-query")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.goCreator();
      }
    });

    this.syncFromInput();
  },

  goCreator() {
    const slug = slugFromCreatorInput(document.getElementById("creator-query")?.value);
    if (!slug) return;
    location.href = artistHref(slug);
  },

  syncFromInput() {
    const input = document.getElementById("category");
    const labelEl = document.getElementById("browse-trigger-label");
    if (!input || !labelEl) return;
    const active = [...document.querySelectorAll(".cat-link")].find(
      (b) => b.dataset.path === input.value
    );
    if (active) {
      labelEl.textContent = active.dataset.label || active.textContent;
      document.querySelectorAll(".cat-link").forEach((b) => b.classList.toggle("active", b === active));
    }
  },

  toggle() {
    if (this.open) this.close();
    else this.openPanel();
  },

  async openPanel() {
    const trigger = document.getElementById("browse-trigger");
    const panel = document.getElementById("browse-panel");
    if (!panel) return;
    panel.hidden = false;
    trigger?.setAttribute("aria-expanded", "true");
    this.open = true;
    await this.refreshLists();
  },

  close() {
    const trigger = document.getElementById("browse-trigger");
    const panel = document.getElementById("browse-panel");
    if (panel) panel.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
    this.open = false;
  },

  showTab(name) {
    document.querySelectorAll(".browse-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    document.querySelectorAll(".browse-pane").forEach((p) => {
      p.hidden = p.dataset.pane !== name;
    });
    if (name === "creators" || name === "hidden") this.refreshLists();
  },

  selectCategory(path, label) {
    const input = document.getElementById("category");
    if (input) input.value = path;
    const labelEl = document.getElementById("browse-trigger-label");
    if (labelEl) labelEl.textContent = label || "Category";
    document.querySelectorAll(".cat-link").forEach((b) => {
      b.classList.toggle("active", b.dataset.path === path);
    });
    this.close();
    if (typeof BrowsePage !== "undefined") {
      BrowsePage.page = 1;
      BrowsePage.load();
    }
  },

  async refreshLists() {
    await Promise.all([this.renderRecent(), this.renderHidden()]);
  },

  async renderRecent() {
    const host = document.getElementById("creator-recent");
    if (!host) return;
    try {
      const data = await api("/api/creators/recent");
      const items = data.items || [];
      if (!items.length) {
        host.className = "creator-empty-host";
        host.innerHTML = `<div class="creator-empty">Browse items to build a recent list, or search above.</div>`;
        return;
      }
      host.className = "cat-grid";
      host.innerHTML = "";
      for (const item of items) host.appendChild(this.creatorLink(item, "hide"));
    } catch (e) {
      host.className = "creator-empty-host";
      host.innerHTML = `<div class="creator-empty">${escapeHtml(e.message)}</div>`;
    }
  },

  async renderHidden() {
    const host = document.getElementById("creator-hidden");
    if (!host) return;
    try {
      const data = await api("/api/creators/hidden");
      const items = data.items || [];
      if (!items.length) {
        host.className = "creator-empty-host";
        host.innerHTML = `<div class="creator-empty">No hidden creators.</div>`;
        return;
      }
      host.className = "cat-grid";
      host.innerHTML = "";
      for (const item of items) host.appendChild(this.creatorLink(item, "unhide"));
    } catch (e) {
      host.className = "creator-empty-host";
      host.innerHTML = `<div class="creator-empty">${escapeHtml(e.message)}</div>`;
    }
  },

  creatorLink(item, mode) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cat-link";
    const name = item.name || item.slug;
    btn.textContent = name;
    btn.title =
      mode === "hide"
        ? "Open creator (right-click to hide)"
        : "Open creator (right-click to unhide)";
    btn.addEventListener("click", () => {
      location.href = artistHref(item.slug);
    });
    btn.addEventListener("contextmenu", async (e) => {
      e.preventDefault();
      try {
        if (mode === "hide") {
          await api("/api/creators/hide", {
            method: "POST",
            body: JSON.stringify({ slug: item.slug, name }),
          });
          toast(`Hidden ${name}`, "success");
        } else {
          await api("/api/creators/unhide", {
            method: "POST",
            body: JSON.stringify({ slug: item.slug }),
          });
          toast(`Unhid ${name}`, "success");
        }
        await this.refreshLists();
        if (typeof BrowsePage !== "undefined" && BrowsePage.load) BrowsePage.load();
      } catch (err) {
        toast(err.message, "error");
      }
    });
    return btn;
  },
};

const Session = {
  ready: false,

  async refresh() {
    try {
      const s = await api("/api/session");
      this.ready = !!s.ready;
      return s;
    } catch {
      this.ready = false;
      return { ready: false };
    }
  },

  async start() {
    try {
      const s = await api("/api/session/start", { method: "POST" });
      if (s.needs_captcha) {
        this.showCaptcha();
        return;
      }
      await this.refresh();
      if (s.ready) toast("Ready to download", "success");
    } catch (e) {
      await this.refresh();
      toast(e.message || "Session failed", "error");
    }
  },

  showCaptcha() {
    const modal = document.getElementById("captcha-modal");
    const img = document.getElementById("captcha-img");
    if (img) img.src = `/api/captcha.png?t=${Date.now()}`;
    if (modal) modal.showModal();
  },

  async submitCaptcha() {
    const code = document.getElementById("captcha-code")?.value?.trim();
    if (!code) return;
    try {
      await api("/api/session/captcha", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      document.getElementById("captcha-modal")?.close();
      await this.refresh();
      toast("Ready to download", "success");
    } catch (e) {
      toast(e.message || "Invalid captcha", "error");
      const img = document.getElementById("captcha-img");
      if (img) img.src = `/api/captcha.png?t=${Date.now()}`;
    }
  },
};

const Settings = {
  suggested: "",

  async load() {
    const data = await api("/api/settings");
    const s = data.settings || {};
    this.suggested = data.suggested_download_directory || "";
    const dir = document.getElementById("setting-download-dir");
    const max = document.getElementById("setting-max-downloads");
    const queue = document.getElementById("setting-save-queue");
    const debug = document.getElementById("setting-debug");
    if (dir) dir.value = s.downloadDirectory || this.suggested || "";
    if (max) max.value = String(s.maxActiveDownloads ?? 4);
    if (queue) queue.checked = !!s.saveDownloadQueue;
    if (debug) debug.checked = !!s.debug;
    try {
      const cache = await api("/api/cache/status");
      const el = document.getElementById("cache-status");
      if (el) {
        const ttl = cache.ttl_hours || {};
        const parts = Object.entries(ttl)
          .map(([k, v]) => `${k} ${v}h`)
          .join(", ");
        el.textContent = parts
          ? `Cache TTLs: ${parts} (oldest entry ${cache.age_hours}h)`
          : `Cache oldest entry ${cache.age_hours}h`;
      }
    } catch {
      /* ignore */
    }
    return data;
  },

  open() {
    Shell.closeSidebar();
    document.getElementById("settings-panel")?.classList.add("open");
    document.getElementById("settings-panel")?.setAttribute("aria-hidden", "false");
    const backdrop = document.getElementById("settings-backdrop");
    if (backdrop) backdrop.hidden = false;
    this.load().catch((e) => toast(e.message, "error"));
  },

  close() {
    document.getElementById("settings-panel")?.classList.remove("open");
    document.getElementById("settings-panel")?.setAttribute("aria-hidden", "true");
    const backdrop = document.getElementById("settings-backdrop");
    if (backdrop) backdrop.hidden = true;
  },

  async pickFolder() {
    try {
      const data = await api("/api/settings/pick-folder", { method: "POST" });
      if (data.path) {
        const dir = document.getElementById("setting-download-dir");
        if (dir) dir.value = data.path;
      }
    } catch (e) {
      toast(e.message || "Folder picker failed", "error");
    }
  },

  async save(extra = {}) {
    const body = {
      downloadDirectory: document.getElementById("setting-download-dir")?.value?.trim() || "",
      maxActiveDownloads: Number(document.getElementById("setting-max-downloads")?.value || 4),
      saveDownloadQueue: !!document.getElementById("setting-save-queue")?.checked,
      debug: !!document.getElementById("setting-debug")?.checked,
      ...extra,
    };
    const data = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(body),
    });
    toast("Settings saved", "success");
    return data;
  },
};

const Onboard = {
  step: 0,
  forced: false,

  steps: [
    {
      title: "CC Installer - TSR Community Manager",
      text: "Browse free Sims 4 CC, open item pages, and download without the VIP ads.",
      extra: "",
    },
    {
      title: "Downloads folder",
      text: "Pick any folder inside your Sims 4 Mods directory. Packages unpack there.",
      extra: "folder",
    },
    {
      title: "How to use",
      text: "A few things to know:",
      extra: "tips",
    },
  ],

  async maybeStart() {
    try {
      const data = await api("/api/settings");
      if (data.needs_onboarding) this.start(false);
    } catch {
      this.start(false);
    }
  },

  start(forced = true) {
    this.forced = forced;
    this.step = 0;
    this.render();
    const el = document.getElementById("onboard");
    if (el) el.hidden = false;
  },

  close() {
    const el = document.getElementById("onboard");
    if (el) el.hidden = true;
  },

  render() {
    const total = this.steps.length;
    const s = this.steps[this.step];
    document.getElementById("onboard-step-label").textContent = `Step ${this.step + 1} of ${total}`;
    document.getElementById("onboard-title").textContent = s.title;
    document.getElementById("onboard-text").textContent = s.text;
    const back = document.getElementById("onboard-back");
    const next = document.getElementById("onboard-next");
    if (back) {
      back.hidden = this.step === 0;
    }
    if (next) next.textContent = this.step === total - 1 ? "Finish" : "Next";

    const extra = document.getElementById("onboard-extra");
    if (!extra) return;
    if (s.extra === "folder") {
      const suggested = Settings.suggested || "";
      extra.innerHTML = `
        <div class="field-row" style="margin-top:14px">
          <input id="onboard-dir" class="field" type="text" value="${escapeHtml(document.getElementById("setting-download-dir")?.value || suggested)}" />
          <button type="button" class="btn btn-ghost" id="onboard-pick">Browse</button>
        </div>
      `;
      document.getElementById("onboard-pick")?.addEventListener("click", async () => {
        await Settings.pickFolder();
        const src = document.getElementById("setting-download-dir");
        const dst = document.getElementById("onboard-dir");
        if (src && dst) dst.value = src.value;
      });
    } else if (s.extra === "tips") {
      extra.innerHTML = `
        <ul class="onboard-list">
          <li>Pick a category and search if you need to.</li>
          <li>Click a card for details, or Add to queue several and Download all from the basket.</li>
          <li>Downloads start a session automatically when needed.</li>
          <li>Files unpack into the Mods folder you chose.</li>
        </ul>
      `;
    } else {
      extra.innerHTML = "";
    }
  },

  async next() {
    if (this.step === 1) {
      const dir = document.getElementById("onboard-dir")?.value?.trim();
      if (!dir) {
        toast("Pick a downloads folder", "error");
        return;
      }
      const settingDir = document.getElementById("setting-download-dir");
      if (settingDir) settingDir.value = dir;
      try {
        await Settings.save({ setupComplete: false });
      } catch (e) {
        toast(e.message, "error");
        return;
      }
    }
    if (this.step >= this.steps.length - 1) {
      try {
        await Settings.save({ setupComplete: true });
        this.close();
        toast("Setup done", "success");
        Session.start();
      } catch (e) {
        toast(e.message, "error");
      }
      return;
    }
    this.step += 1;
    this.render();
  },

  back() {
    if (this.step <= 0) return;
    this.step -= 1;
    this.render();
  },
};


function parseSizeToBytes(size) {
  if (!size) return 0;
  const m = String(size).trim().match(/^([\d.]+)\s*(KB|MB|GB|B)?$/i);
  if (!m) return 0;
  const n = parseFloat(m[1]);
  if (!Number.isFinite(n)) return 0;
  const u = (m[2] || "B").toUpperCase();
  if (u === "GB") return n * 1024 * 1024 * 1024;
  if (u === "MB") return n * 1024 * 1024;
  if (u === "KB") return n * 1024;
  return n;
}

function formatBytes(bytes) {
  if (!bytes) return "-";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${Math.round(bytes)} B`;
}

const Basket = {
  KEY: "tsr_basket_v1",
  items: {},
  selected: new Set(),
  downloading: false,

  init() {
    this.load();
    this.bind();
    this.renderBadge();
  },

  load() {
    try {
      const raw = localStorage.getItem(this.KEY);
      this.items = raw ? JSON.parse(raw) || {} : {};
    } catch {
      this.items = {};
    }
  },

  save() {
    localStorage.setItem(this.KEY, JSON.stringify(this.items));
    this.renderBadge();
  },

  count() {
    return Object.keys(this.items).length;
  },

  has(id) {
    return !!this.items[String(id)];
  },

  normalize(item) {
    const id = Number(item.item_id ?? item.itemId ?? item.id);
    return {
      item_id: id,
      title: item.title || `Item ${id}`,
      artist: item.artist || "",
      size: item.size || "",
      thumbnail_url: item.thumbnail_url || item.thumbnail || null,
      url: item.url || `/item/${id}`,
    };
  },

  add(item) {
    const row = this.normalize(item);
    if (!row.item_id) return false;
    this.items[String(row.item_id)] = row;
    this.save();
    toast("Added to basket", "success");
    this.render();
    return true;
  },

  remove(ids) {
    for (const id of ids) {
      delete this.items[String(id)];
      this.selected.delete(String(id));
    }
    this.save();
    this.render();
  },

  clear() {
    this.items = {};
    this.selected.clear();
    this.save();
    this.render();
  },

  list() {
    return Object.values(this.items);
  },

  totalBytes() {
    return this.list().reduce((sum, it) => sum + parseSizeToBytes(it.size), 0);
  },

  renderBadge() {
    const el = document.getElementById("basket-count");
    if (el) el.textContent = String(this.count());
  },

  open() {
    document.getElementById("basket-panel")?.classList.add("open");
    document.getElementById("basket-panel")?.setAttribute("aria-hidden", "false");
    const backdrop = document.getElementById("basket-backdrop");
    if (backdrop) backdrop.hidden = false;
    this.render();
  },

  close() {
    document.getElementById("basket-panel")?.classList.remove("open");
    document.getElementById("basket-panel")?.setAttribute("aria-hidden", "true");
    const backdrop = document.getElementById("basket-backdrop");
    if (backdrop) backdrop.hidden = true;
  },

  bind() {
    document.getElementById("basket-toggle")?.addEventListener("click", () => this.open());
    document.getElementById("basket-close")?.addEventListener("click", () => this.close());
    document.getElementById("basket-backdrop")?.addEventListener("click", () => this.close());
    document.getElementById("basket-select-all")?.addEventListener("change", (e) => {
      const on = !!e.target.checked;
      this.selected = on ? new Set(Object.keys(this.items)) : new Set();
      this.render();
    });
    document.getElementById("basket-remove-selected")?.addEventListener("click", () => {
      if (!this.selected.size) {
        toast("Select items to remove", "error");
        return;
      }
      this.remove([...this.selected]);
    });
    document.getElementById("basket-remove-all")?.addEventListener("click", () => {
      if (!this.count()) return;
      this.clear();
      toast("Basket cleared", "success");
    });
    document.getElementById("basket-download-all")?.addEventListener("click", () => this.downloadAll());
  },

  render() {
    const empty = document.getElementById("basket-empty");
    const grid = document.getElementById("basket-grid");
    const total = document.getElementById("basket-total");
    const selectAll = document.getElementById("basket-select-all");
    if (!grid) return;
    const items = this.list();
    if (empty) empty.hidden = items.length > 0;
    grid.hidden = items.length === 0;
    grid.innerHTML = "";
    for (const item of items) {
      const id = String(item.item_id);
      const card = document.createElement("div");
      card.className = "basket-card";
      const thumb = item.thumbnail_url
        ? `<img src="${proxied(item.thumbnail_url)}" alt="" loading="lazy" />`
        : "";
      card.innerHTML = `
        <div class="basket-card-thumb">${thumb}</div>
        <p class="basket-card-title">${escapeHtml(item.title)}</p>
        <div class="basket-card-meta">
          <input type="checkbox" data-id="${id}" ${this.selected.has(id) ? "checked" : ""} />
          <p class="hint">${escapeHtml(item.size || "-")}</p>
        </div>
      `;
      card.querySelector("input")?.addEventListener("change", (e) => {
        if (e.target.checked) this.selected.add(id);
        else this.selected.delete(id);
        if (selectAll) {
          selectAll.checked = this.selected.size === items.length && items.length > 0;
        }
      });
      card.querySelector(".basket-card-thumb")?.addEventListener("click", () => {
        location.href = `/item/${item.item_id}`;
      });
      grid.appendChild(card);
    }
    if (selectAll) {
      selectAll.checked = items.length > 0 && this.selected.size === items.length;
      selectAll.indeterminate = this.selected.size > 0 && this.selected.size < items.length;
    }
    if (total) total.textContent = `Total size: ${formatBytes(this.totalBytes())} / ${items.length} item${items.length === 1 ? "" : "s"}`;
    this.renderBadge();
    document.querySelectorAll("button.glass-add").forEach((btn) => {
      const id = btn.getAttribute("data-id");
      if (!id) return;
      const on = this.has(id);
      btn.classList.toggle("is-in", on);
      btn.textContent = on ? "Added" : "Add";
    });
    const addBtn = document.getElementById("btn-add-basket");
    if (addBtn && ItemPage?.itemId) {
      const on = this.has(ItemPage.itemId);
      addBtn.textContent = on ? "In basket" : "Add to basket";
      addBtn.disabled = false;
    }
  },

  async downloadOne(itemId) {
    await api(`/api/download/${itemId}`, { method: "POST" });
    for (;;) {
      const st = await api(`/api/download/${itemId}/status`);
      const status = st.status || "";
      if (status === "Downloaded") return true;
      if (String(status).startsWith("Failed")) throw new Error(status);
      await new Promise((r) => setTimeout(r, 1200));
    }
  },

  async downloadAll() {
    const items = this.list();
    if (!items.length) {
      toast("Basket is empty", "error");
      return;
    }
    if (this.downloading) return;
    const s = await Session.refresh();
    if (!s.ready) {
      toast("Session not ready yet - try again in a moment", "error");
      return;
    }
    this.downloading = true;
    const btn = document.getElementById("basket-download-all");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Downloading...";
    }
    let ok = 0;
    let fail = 0;
    try {
      let max = 2;
      const maxEl = document.getElementById("setting-max-downloads");
      if (maxEl) max = Math.max(1, Math.min(8, Number(maxEl.value) || 2));
      else {
        try {
          const data = await api("/api/settings");
          max = Math.max(1, Math.min(8, Number(data.settings?.maxActiveDownloads) || 2));
        } catch (_) {}
      }

      const doneIds = new Set();
      let cursor = 0;
      const workers = Array.from({ length: Math.min(max, items.length) }, async () => {
        while (cursor < items.length) {
          const idx = cursor++;
          const item = items[idx];
          try {
            await this.downloadOne(item.item_id);
            ok += 1;
            doneIds.add(String(item.item_id));
            if (typeof BrowsePage !== "undefined" && BrowsePage.installedIds) {
              BrowsePage.installedIds.add(Number(item.item_id));
            }
          } catch (e) {
            fail += 1;
            console.error(e);
          }
        }
      });
      await Promise.all(workers);
      if (ok) toast(`Downloaded ${ok} item${ok === 1 ? "" : "s"}`, "success");
      if (fail) toast(`${fail} failed`, "error");
      if (doneIds.size) {
        for (const id of doneIds) {
          delete this.items[id];
          this.selected.delete(id);
        }
        this.save();
        this.render();
      }
    } finally {
      this.downloading = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Download all";
      }
    }
  },
};


const Shell = {
  bound: false,

  init() {
    if (this.bound) return;
    this.bound = true;

    this.bindWindowChrome();
    Basket.init();

    document.getElementById("btn-menu")?.addEventListener("click", () => this.openSidebar());
    document.getElementById("sidebar-close")?.addEventListener("click", () => this.closeSidebar());
    document.getElementById("sidebar-backdrop")?.addEventListener("click", () => this.closeSidebar());
    document.getElementById("settings-close")?.addEventListener("click", () => Settings.close());
    document.getElementById("settings-backdrop")?.addEventListener("click", () => Settings.close());
    document.getElementById("legal-close")?.addEventListener("click", () => Legal.close());
    document.getElementById("legal-backdrop")?.addEventListener("click", () => Legal.close());
    document.getElementById("setting-pick-folder")?.addEventListener("click", () => Settings.pickFolder());
    document.getElementById("setting-save")?.addEventListener("click", async () => {
      try {
        await Settings.save({ setupComplete: true });
        Settings.close();
      } catch (e) {
        toast(e.message, "error");
      }
    });
    document.getElementById("setting-clear-cache")?.addEventListener("click", async () => {
      try {
        await api("/api/cache/clear", { method: "POST" });
        toast("Cache cleared", "success");
        Settings.load();
      } catch (e) {
        toast(e.message, "error");
      }
    });
    document.getElementById("captcha-submit")?.addEventListener("click", () => Session.submitCaptcha());
    document.getElementById("onboard-next")?.addEventListener("click", () => Onboard.next());
    document.getElementById("onboard-back")?.addEventListener("click", () => Onboard.back());

    document.querySelectorAll("[data-nav]").forEach((btn) => {
      btn.addEventListener("click", () => this.onNav(btn.getAttribute("data-nav")));
    });

    Settings.load()
      .then((data) => {
        if (data.needs_onboarding) Onboard.start(false);
        else Session.refresh().then(() => Session.start());
      })
      .catch(() => Onboard.start(false));
  },

  async winApi(name, ...args) {
    const apiFn = window.pywebview?.api?.[name];
    if (typeof apiFn !== "function") return null;
    return apiFn(...args);
  },

  setMaximizedUi(on) {
    document.body.classList.toggle("is-maximized", !!on);
    const btn = document.getElementById("win-maximize");
    if (btn) {
      btn.title = on ? "Restore" : "Maximize";
      btn.setAttribute("aria-label", on ? "Restore" : "Maximize");
    }
  },

  bindWindowChrome() {
    const sync = async () => {
      const maximized = await this.winApi("is_maximized");
      if (typeof maximized === "boolean") this.setMaximizedUi(maximized);
    };
    const ready = () => {
      sync().catch(() => {});
    };
    if (window.pywebview?.api) ready();
    else window.addEventListener("pywebviewready", ready, { once: true });

    document.getElementById("win-minimize")?.addEventListener("click", () => {
      this.winApi("minimize").catch(() => {});
    });
    document.getElementById("win-maximize")?.addEventListener("click", async () => {
      try {
        const maximized = await this.winApi("toggle_maximize");
        if (typeof maximized === "boolean") this.setMaximizedUi(maximized);
      } catch (_) {}
    });
    document.getElementById("win-close")?.addEventListener("click", () => {
      this.winApi("close").catch(() => {});
    });
    document.getElementById("window-drag")?.addEventListener("dblclick", async () => {
      try {
        const maximized = await this.winApi("toggle_maximize");
        if (typeof maximized === "boolean") this.setMaximizedUi(maximized);
      } catch (_) {}
    });
  },

  openSidebar() {
    document.getElementById("sidebar")?.classList.add("open");
    document.getElementById("sidebar")?.setAttribute("aria-hidden", "false");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (backdrop) backdrop.hidden = false;
  },

  closeSidebar() {
    document.getElementById("sidebar")?.classList.remove("open");
    document.getElementById("sidebar")?.setAttribute("aria-hidden", "true");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (backdrop) backdrop.hidden = true;
  },

  onNav(action) {
    this.closeSidebar();
    if (action === "browse") {
      if (location.pathname !== "/" && !location.pathname.endsWith("/")) {
        location.href = "/";
      }
      return;
    }
    if (action === "library") {
      if (!location.pathname.includes("/library")) {
        location.href = "/library";
      }
      return;
    }
    if (action === "settings") {
      Settings.open();
      return;
    }
    if (action === "help") {
      Onboard.start(true);
      return;
    }
    if (action === "legal") {
      Legal.open();
    }
  },
};

const Legal = {
  loaded: false,

  async open() {
    document.getElementById("legal-panel")?.classList.add("open");
    document.getElementById("legal-panel")?.setAttribute("aria-hidden", "false");
    const backdrop = document.getElementById("legal-backdrop");
    if (backdrop) backdrop.hidden = false;
    if (this.loaded) return;
    try {
      const data = await api("/api/legal");
      const el = document.getElementById("legal-mit");
      if (el) el.textContent = data.license || "MIT License file missing.";
      this.loaded = true;
    } catch (e) {
      const el = document.getElementById("legal-mit");
      if (el) el.textContent = e.message || "Could not load license.";
    }
  },

  close() {
    document.getElementById("legal-panel")?.classList.remove("open");
    document.getElementById("legal-panel")?.setAttribute("aria-hidden", "true");
    const backdrop = document.getElementById("legal-backdrop");
    if (backdrop) backdrop.hidden = true;
  },
};

const BrowsePage = {
  page: 1,
  loading: false,
  installedIds: new Set(),
  maxPage: null,

  init() {
    document.getElementById("search-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      this.page = 1;
      this.load();
    });

    const params = new URLSearchParams(location.search);
    if (params.get("q")) document.getElementById("query").value = params.get("q");
    if (params.get("category")) {
      const input = document.getElementById("category");
      if (input) input.value = params.get("category");
      BrowseMenu.syncFromInput();
    }
    if (params.get("page")) this.page = Math.max(1, parseInt(params.get("page"), 10) || 1);

    this.load();
  },

  state() {
    return {
      category: document.getElementById("category")?.value || "",
      q: document.getElementById("query")?.value?.trim() || "",
      page: this.page,
    };
  },

  syncUrl() {
    const { category, q, page } = this.state();
    const p = new URLSearchParams();
    p.set("category", category);
    if (q) p.set("q", q);
    if (page > 1) p.set("page", String(page));
    history.replaceState(null, "", `?${p.toString()}`);
  },

  setVisible(id, on) {
    document.getElementById(id)?.classList.toggle("hidden", !on);
  },

  async refreshInstalled() {
    try {
      const data = await api("/api/library");
      this.installedIds = new Set(
        (data.items || []).map((i) => Number(i.item_id)).filter(Boolean)
      );
    } catch {
      this.installedIds = new Set();
    }
  },

  async load() {
    if (this.loading) return;
    this.loading = true;
    this.syncUrl();

    const grid = document.getElementById("grid");
    grid.innerHTML = "";
    this.setVisible("empty", false);
    this.setVisible("loading", true);

    const { category, q, page } = this.state();
    const qs = new URLSearchParams({ category, page: String(page) });
    if (q) qs.set("q", q);

    try {
      const [data] = await Promise.all([api(`/api/browse?${qs}`), this.refreshInstalled()]);
      this.setVisible("loading", false);

      const heading = document.getElementById("page-heading");
      const creations = document.getElementById("creations-count");
      if (heading) heading.textContent = data.category_label || "Trending Now";
      if (creations) {
        creations.textContent = data.total_creations
          ? `${data.total_creations} creations`
          : "";
      }

      document.getElementById("status-line").textContent =
        `${data.count} items, page ${data.page}`;

      if (!data.items.length) {
        this.setVisible("empty", true);
      } else {
        for (const item of data.items) grid.appendChild(this.card(item));
      }
      this.renderPaginator(data.page, data.count);
    } catch (e) {
      this.setVisible("loading", false);
      this.setVisible("empty", true);
      document.getElementById("status-line").textContent = `Failed: ${e.message}`;
      toast(e.message, "error");
      this.renderPaginator(this.page, 0);
    } finally {
      this.loading = false;
    }
  },

  card(item) {
    const wrap = document.createElement("div");
    wrap.className = "product-card";
    const installed = this.installedIds.has(Number(item.item_id));
    const name = artistName(item.artist);
    const slug = item.artist_slug || "";
    const artistHtml = name
      ? slug
        ? `<a class="artist-link" href="${artistHref(slug)}">By ${escapeHtml(name)}</a>`
        : `By ${escapeHtml(name)}`
      : "";
    const sizeText = item.size ? escapeHtml(item.size) : "-";
    const artistBit = artistHtml || "By -";
    const thumb = item.thumbnail_url
      ? `<img src="${proxied(item.thumbnail_url)}" alt="" loading="lazy" />`
      : "";
    const inBasket = Basket.has(item.item_id);
    const action = installed
      ? `<a class="glass-dl is-done" href="/item/${item.item_id}">Manage</a>`
      : `<div class="glass-actions">
           <button type="button" class="glass-add${inBasket ? " is-in" : ""}" data-id="${item.item_id}">${inBasket ? "Added" : "Add"}</button>
           <button type="button" class="glass-dl">Download</button>
         </div>`;

    wrap.innerHTML = `
      <div class="media">
        ${thumb}
        <div class="glass">
          <button type="button" class="info open-btn">
            <p class="title">${escapeHtml(item.title)}</p>
            <p class="sub">
              <span class="sub-artist">${artistBit}</span>
              <span class="sub-sep">/</span>
              <span class="sub-size">${sizeText}</span>
            </p>
          </button>
          ${action}
        </div>
      </div>
    `;

    const openItem = () => {
      window.location.href = `/item/${item.item_id}`;
    };
    wrap.querySelector(".media")?.addEventListener("click", (e) => {
      if (e.target.closest(".artist-link, .glass-dl, .glass-add")) return;
      openItem();
    });
    wrap.querySelector(".artist-link")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      window.location.href = artistHref(slug);
    });
    wrap.querySelector("button.glass-add")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const btn = e.currentTarget;
      if (Basket.has(item.item_id)) {
        Basket.remove([item.item_id]);
        btn.classList.remove("is-in");
        btn.textContent = "Add";
        toast("Removed from basket", "success");
      } else {
        Basket.add(item);
        btn.classList.add("is-in");
        btn.textContent = "Added";
      }
    });
    wrap.querySelector("button.glass-dl")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.quickDownload(item, wrap.querySelector("button.glass-dl"));
    });
    return wrap;
  },

  async quickDownload(item, btn) {
    if (!btn || btn.disabled) return;
    const s = await Session.refresh();
    if (!s.ready) {
      toast("Session not ready yet. Try again in a moment", "error");
      return;
    }
    btn.disabled = true;
    btn.classList.add("is-busy");
    btn.classList.remove("is-done");
    btn.textContent = "...";
    try {
      await api(`/api/download/${item.item_id}`, { method: "POST" });
      const tick = async () => {
        const st = await api(`/api/download/${item.item_id}/status`);
        const status = st.status || "";
        if (status === "Downloaded") {
          this.installedIds.add(Number(item.item_id));
          const link = document.createElement("a");
          link.className = "glass-dl is-done";
          link.href = `/item/${item.item_id}`;
          link.textContent = "Manage";
          btn.replaceWith(link);
          toast("Downloaded", "success");
          return;
        }
        if (String(status).startsWith("Failed")) {
          btn.classList.remove("is-busy");
          btn.disabled = false;
          btn.textContent = "Download";
          toast(status, "error");
          return;
        }
        btn.textContent = status.startsWith("Downloading") ? "..." : "...";
        setTimeout(tick, 1200);
      };
      tick();
    } catch (e) {
      btn.classList.remove("is-busy");
      btn.disabled = false;
      btn.textContent = "Download";
      toast(e.message, "error");
    }
  },

  goToPage(target) {
    let page = Math.max(1, parseInt(target, 10) || 1);
    if (this.maxPage != null) page = Math.min(page, this.maxPage);
    this.page = page;
    this.load();
    window.scrollTo({ top: 0, behavior: "smooth" });
  },

  renderPaginator(page, count) {
    const hosts = [
      document.getElementById("paginator-top"),
      document.getElementById("paginator-bottom"),
      document.getElementById("paginator"),
    ].filter(Boolean);
    if (!hosts.length) return;

    const maxPage = this.maxPage;
    const hasNext = maxPage != null ? page < maxPage : count > 0;
    const start = Math.max(1, page - 2);
    const pages = [];
    for (let p = start; p < start + 5; p++) {
      if (maxPage != null && p > maxPage) break;
      pages.push(p);
    }

    const fill = (nav) => {
      nav.innerHTML = "";
      const inner = document.createElement("div");
      inner.className = "pager-inner";

      const addBtn = (label, target, opts = {}) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = label;
        if (opts.active) b.classList.add("active");
        if (opts.disabled) b.disabled = true;
        else {
          b.addEventListener("click", () => this.goToPage(target));
        }
        inner.appendChild(b);
      };

      addBtn("«", page - 1, { disabled: page <= 1 });
      for (const p of pages) {
        addBtn(String(p), p, { active: p === page });
      }
      addBtn("»", page + 1, { disabled: !hasNext });

      const jump = document.createElement("form");
      jump.className = "pager-jump";
      jump.innerHTML = `
        <input type="number" min="1" ${maxPage != null ? `max="${maxPage}"` : ""} inputmode="numeric" aria-label="Jump to page" placeholder="#" value="${page}" />
        <button type="submit" aria-label="Go to page">Go</button>
      `;
      jump.addEventListener("submit", (e) => {
        e.preventDefault();
        const input = jump.querySelector("input");
        this.goToPage(input?.value);
      });
      inner.appendChild(jump);
      nav.appendChild(inner);
    };

    hosts.forEach(fill);
  },
};

const LibraryPage = {
  loading: false,

  init() {
    this.load();
  },

  setVisible(id, on) {
    document.getElementById(id)?.classList.toggle("hidden", !on);
  },

  async load() {
    if (this.loading) return;
    this.loading = true;
    const grid = document.getElementById("grid");
    if (!grid) return;
    grid.innerHTML = "";
    this.setVisible("empty", false);
    this.setVisible("loading", true);

    try {
      const data = await api("/api/library");
      this.setVisible("loading", false);
      const items = data.items || [];
      const count = document.getElementById("library-count");
      if (count) count.textContent = `${items.length} installed`;
      document.getElementById("status-line").textContent =
        items.length ? "Click a card for details. Uninstall deletes the files." : "";

      if (!items.length) {
        this.setVisible("empty", true);
      } else {
        for (const item of items) grid.appendChild(this.card(item));
      }
    } catch (e) {
      this.setVisible("loading", false);
      this.setVisible("empty", true);
      document.getElementById("status-line").textContent = `Failed: ${e.message}`;
      toast(e.message, "error");
    } finally {
      this.loading = false;
    }
  },

  card(item) {
    const wrap = document.createElement("div");
    wrap.className = "product-card library-card";
    const sub = [
      formatArtist(item.artist) || "By -",
      item.size || "-",
      item.files_existing != null
        ? `${item.files_existing}/${item.files_total || 0} files`
        : null,
    ]
      .filter((part) => part != null && part !== "")
      .join(" / ");
    const thumb = item.thumbnail_url
      ? `<img src="${proxied(item.thumbnail_url)}" alt="" loading="lazy" />`
      : `<div class="thumb-fallback">No image</div>`;

    wrap.innerHTML = `
      <button type="button" class="media open-btn">
        ${thumb}
        <div class="glass">
          <div class="info">
            <p class="title">${escapeHtml(item.title || "Untitled")}</p>
            <p class="sub">${escapeHtml(sub)}</p>
          </div>
          <span class="pill-btn" aria-hidden="true">›</span>
        </div>
      </button>
      <button type="button" class="btn btn-uninstall uninstall-btn">Uninstall</button>
    `;

    wrap.querySelector(".open-btn")?.addEventListener("click", () => {
      window.location.href = `/item/${item.item_id}`;
    });
    wrap.querySelector(".uninstall-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this.uninstall(item, wrap);
    });
    return wrap;
  },

  async uninstall(item, cardEl) {
    const ok = window.confirm(
      `Uninstall "${item.title}"?\nThis deletes tracked package files from your Mods folder.`
    );
    if (!ok) return;
    const btn = cardEl.querySelector(".uninstall-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Removing...";
    }
    try {
      const res = await api(`/api/library/${item.item_id}`, { method: "DELETE" });
      toast(`Uninstalled ${res.title || item.title}`, "success");
      cardEl.remove();
      const grid = document.getElementById("grid");
      const left = grid ? grid.querySelectorAll(".library-card").length : 0;
      const count = document.getElementById("library-count");
      if (count) count.textContent = `${left} installed`;
      if (!left) this.setVisible("empty", true);
    } catch (e) {
      toast(e.message, "error");
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Uninstall";
      }
    }
  },
};

const ItemPage = {
  itemId: null,
  images: [],
  index: 0,
  item: null,
  installed: null,

  init(itemId) {
    this.itemId = itemId;
    Session.refresh();
    document.getElementById("btn-download")?.addEventListener("click", () => this.download());
    document.getElementById("btn-add-basket")?.addEventListener("click", () => {
      if (!this.item) return;
      if (Basket.has(this.itemId)) {
        Basket.remove([this.itemId]);
        toast("Removed from basket", "success");
      } else {
        Basket.add(this.item);
      }
      Basket.render();
    });
    document.getElementById("manage-reveal")?.addEventListener("click", () => this.reveal());
    document.getElementById("manage-uninstall")?.addEventListener("click", () => this.uninstall());
    this.load();
  },

  async load() {
    try {
      const data = await api(`/api/item/${this.itemId}`);
      const item = data.item;
      this.item = item;
      this.installed = data.installed?.installed ? data.installed : null;
      document.getElementById("item-loading").classList.add("hidden");
      document.getElementById("item-content").classList.remove("hidden");
      document.getElementById("item-title").textContent = item.title;
      document.getElementById("detail-title").textContent = item.title;
      this.renderMeta(item);
      document.getElementById("detail-desc").textContent = item.description || "No description";
      document.getElementById("detail-notes").textContent = item.notes || "No notes";
      this.images = item.image_urls || [];
      this.index = 0;
      this.renderGallery();
      this.renderDownloadStatus();
      const addBtn = document.getElementById("btn-add-basket");
      if (addBtn) {
        addBtn.disabled = false;
        addBtn.textContent = Basket.has(this.itemId) ? "In basket" : "Add to basket";
      }
      this.loadSuggestions();
    } catch (e) {
      document.getElementById("item-loading").classList.add("hidden");
      const err = document.getElementById("item-error");
      err.classList.remove("hidden");
      err.textContent = e.message;
    }
  },

  renderMeta(item) {
    const meta = document.getElementById("detail-meta");
    if (!meta) return;
    meta.innerHTML = "";
    const bits = [];
    const name = artistName(item.artist);
    if (name) {
      const wrap = document.createElement("span");
      wrap.appendChild(document.createTextNode("By "));
      if (item.artist_slug) {
        const a = document.createElement("a");
        a.className = "artist-link";
        a.href = artistHref(item.artist_slug);
        a.textContent = name;
        wrap.appendChild(a);
      } else {
        wrap.appendChild(document.createTextNode(name));
      }
      bits.push(wrap);
    }
    for (const part of [
      item.category || null,
      item.downloads ? `${item.downloads} downloads` : null,
      item.size || "-",
    ]) {
      if (!part) continue;
      bits.push(document.createTextNode(part));
    }
    bits.forEach((node, i) => {
      if (i) meta.appendChild(document.createTextNode(" / "));
      meta.appendChild(node);
    });
  },

  renderDownloadStatus(text) {
    const status = document.getElementById("download-status");
    const btn = document.getElementById("btn-download");
    const actions = document.querySelector(".detail-actions");
    if (!status) return;
    status.innerHTML = "";

    if (text) {
      if (btn) {
        btn.hidden = false;
        btn.disabled = true;
      }
      if (actions) actions.hidden = false;
      status.textContent = text;
      return;
    }

    if (this.installed) {
      if (btn) btn.hidden = true;
      if (actions) actions.hidden = true;
      status.appendChild(document.createTextNode("Downloaded"));
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "|";
      status.appendChild(sep);
      const manage = document.createElement("button");
      manage.type = "button";
      manage.className = "manage-link";
      manage.textContent = "Manage";
      manage.addEventListener("click", () => this.openManage());
      status.appendChild(manage);
      return;
    }

    if (btn) {
      btn.hidden = false;
      btn.disabled = false;
      btn.textContent = "Download";
    }
    if (actions) actions.hidden = false;
  },

  openManage() {
    const modal = document.getElementById("manage-modal");
    const title = document.getElementById("manage-title");
    if (title) {
      title.textContent = this.item?.title || `Item ${this.itemId}`;
    }
    modal?.showModal();
  },

  async reveal() {
    try {
      await api(`/api/library/${this.itemId}/reveal`, { method: "POST" });
      document.getElementById("manage-modal")?.close();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async uninstall() {
    const name = this.item?.title || `Item ${this.itemId}`;
    const ok = window.confirm(
      `Uninstall "${name}"?\nThis deletes tracked package files from your Mods folder.`
    );
    if (!ok) return;
    try {
      await api(`/api/library/${this.itemId}`, { method: "DELETE" });
      this.installed = null;
      document.getElementById("manage-modal")?.close();
      this.renderDownloadStatus();
      toast(`Uninstalled ${name}`, "success");
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async loadSuggestions() {
    const section = document.getElementById("suggest-section");
    const grid = document.getElementById("suggest-grid");
    if (!section || !grid) return;
    try {
      await BrowsePage.refreshInstalled();
      const qs = new URLSearchParams();
      if (this.item?.category) qs.set("category", this.item.category);
      if (this.item?.artist_slug) qs.set("artist_slug", this.item.artist_slug);
      if (this.item?.artist) qs.set("artist", this.item.artist);
      const data = await api(`/api/item/${this.itemId}/suggestions?${qs}`);
      const items = data.items || [];
      if (!items.length) {
        section.hidden = true;
        return;
      }
      const heading = document.getElementById("suggest-heading");
      const link = document.getElementById("suggest-all");
      if (data.mode === "artist") {
        const name = data.category_label || artistName(this.item?.artist) || "creator";
        if (heading) heading.textContent = `More by ${name}`;
        if (link) {
          link.textContent = "View all";
          link.href = data.browse_href || artistHref(this.item?.artist_slug);
        }
      } else {
        const label = (data.category_label || "clothing").toLowerCase();
        if (heading) heading.textContent = `More ${label}`;
        if (link) {
          link.textContent = "Browse category";
          link.href = data.browse_href || "/";
        }
      }
      grid.innerHTML = "";
      for (const item of items) {
        grid.appendChild(BrowsePage.card(item));
      }
      section.hidden = false;
    } catch {
      section.hidden = true;
    }
  },

  renderGallery() {
    const img = document.getElementById("gallery-img");
    const thumbs = document.getElementById("thumbs");
    thumbs.innerHTML = "";
    if (!this.images.length) {
      img.removeAttribute("src");
      return;
    }
    img.src = proxied(this.images[this.index]);
    this.images.forEach((url, i) => {
      const b = document.createElement("button");
      b.type = "button";
      if (i === this.index) b.classList.add("active");
      b.innerHTML = `<img src="${proxied(url)}" alt="" />`;
      b.addEventListener("click", () => {
        this.index = i;
        this.renderGallery();
      });
      thumbs.appendChild(b);
    });
  },

  async download() {
    const btn = document.getElementById("btn-download");
    const s = await Session.refresh();
    if (!s.ready) {
      toast("Session not ready yet - try again in a moment", "error");
      return;
    }
    btn.disabled = true;
    this.renderDownloadStatus("Queued...");
    try {
      await api(`/api/download/${this.itemId}`, { method: "POST" });
      const tick = async () => {
        const st = await api(`/api/download/${this.itemId}/status`);
        if (st.status === "Downloaded") {
          try {
            const lib = await api(`/api/library/${this.itemId}`);
            this.installed = lib.installed ? lib : { installed: true, item_id: this.itemId };
          } catch {
            this.installed = { installed: true, item_id: this.itemId };
          }
          this.renderDownloadStatus();
          toast("Downloaded", "success");
          return;
        }
        if (String(st.status).startsWith("Failed")) {
          this.renderDownloadStatus();
          toast(st.status, "error");
          return;
        }
        this.renderDownloadStatus(st.status || "Downloading...");
        setTimeout(tick, 1200);
      };
      tick();
    } catch (e) {
      this.renderDownloadStatus();
      toast(e.message, "error");
    }
  },
};

const ArtistPage = {
  slug: "",
  page: 1,
  cnt: 0,
  q: "",
  loading: false,
  maxPage: null,
  installedIds: null,
  artistName: "",
  hidden: false,

  init(slug) {
    this.slug = slug;
    const params = new URLSearchParams(location.search);
    if (params.get("page")) this.page = Math.max(1, parseInt(params.get("page"), 10) || 1);
    if (params.get("cnt")) this.cnt = Math.max(0, parseInt(params.get("cnt"), 10) || 0);
    if (params.get("q")) {
      this.q = params.get("q");
      const input = document.getElementById("artist-query");
      if (input) input.value = this.q;
    }
    document.getElementById("btn-hide-creator")?.addEventListener("click", () => this.toggleHide());
    document.getElementById("artist-search-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      this.q = document.getElementById("artist-query")?.value?.trim() || "";
      this.page = 1;
      this.cnt = 0;
      this.load();
    });
    this.load();
  },

  setVisible(id, on) {
    document.getElementById(id)?.classList.toggle("hidden", !on);
  },

  syncUrl() {
    const p = new URLSearchParams();
    if (this.q) p.set("q", this.q);
    if (this.page > 1) p.set("page", String(this.page));
    if (this.cnt) p.set("cnt", String(this.cnt));
    const q = p.toString();
    history.replaceState(null, "", q ? `?${q}` : location.pathname);
  },

  async load() {
    if (this.loading) return;
    this.loading = true;
    this.syncUrl();
    const grid = document.getElementById("grid");
    if (!grid) return;
    grid.innerHTML = "";
    this.setVisible("empty", false);
    this.setVisible("loading", true);

    const qs = new URLSearchParams({ page: String(this.page) });
    if (this.cnt) qs.set("cnt", String(this.cnt));
    if (this.q) qs.set("q", this.q);

    try {
      await BrowsePage.refreshInstalled();
      this.installedIds = BrowsePage.installedIds;
      const data = await api(`/api/artist/${encodeURIComponent(this.slug)}?${qs}`);
      this.setVisible("loading", false);
      if (data.cnt) this.cnt = data.cnt;
      if (data.page_count) this.maxPage = data.page_count;
      else this.maxPage = data.count > 0 ? null : this.page;

      const heading = document.getElementById("page-heading");
      const creations = document.getElementById("creations-count");
      if (heading) heading.textContent = data.artist || this.slug;
      this.artistName = data.artist || this.slug;
      this.hidden = !!data.hidden;
      this.syncHideBtn();
      if (creations) {
        creations.textContent = data.total_creations
          ? `${data.total_creations} creations`
          : "";
      }
      const statusBits = [`${data.count} items, page ${data.page}`];
      if (data.page_count) statusBits[0] += ` / ${data.page_count}`;
      if (this.q) statusBits.push(`search: ${this.q}`);
      document.getElementById("status-line").textContent = statusBits.join(" / ");

      if (!data.items.length) {
        this.setVisible("empty", true);
      } else {
        for (const item of data.items) {
          grid.appendChild(BrowsePage.card.call(this, item));
        }
      }
      this.renderPaginator(data.page, data.count);
    } catch (e) {
      this.setVisible("loading", false);
      this.setVisible("empty", true);
      document.getElementById("status-line").textContent = `Failed: ${e.message}`;
      toast(e.message, "error");
    } finally {
      this.loading = false;
    }
  },

  goToPage(target) {
    let page = Math.max(1, parseInt(target, 10) || 1);
    if (this.maxPage != null) page = Math.min(page, this.maxPage);
    this.page = page;
    this.load();
    window.scrollTo({ top: 0, behavior: "smooth" });
  },

  renderPaginator(page, count) {
    BrowsePage.renderPaginator.call(this, page, count);
  },

  syncHideBtn() {
    const btn = document.getElementById("btn-hide-creator");
    if (!btn) return;
    btn.textContent = this.hidden ? "Unhide creator" : "Hide creator";
  },

  async toggleHide() {
    const name = this.artistName || this.slug;
    try {
      if (this.hidden) {
        await api("/api/creators/unhide", {
          method: "POST",
          body: JSON.stringify({ slug: this.slug }),
        });
        this.hidden = false;
        toast(`Unhid ${name}`, "success");
      } else {
        await api("/api/creators/hide", {
          method: "POST",
          body: JSON.stringify({ slug: this.slug, name }),
        });
        this.hidden = true;
        toast(`Hidden ${name}`, "success");
      }
      this.syncHideBtn();
    } catch (e) {
      toast(e.message, "error");
    }
  },
};
