const ids = [
  "collection",
  "year_from",
  "year_to",
  "any_term",
  "subject",
  "location",
  "tag",
  "contributor",
  "fts",
  "limit",
  "shuffle",
  "exclude_portraits",
  "autoplay_seconds",
];

const VIEW_GALLERY = "gallery";
const VIEW_MASTER = "master";

let currentItems = [];
let currentView = VIEW_GALLERY;
let masterIndex = 0;
let lightboxLastFocus = null;
let lightboxMetaCollapsed = false;
let lightboxIndex = 0;
let lightboxAutoplayTimer = null;
let lightboxMode = "paused";
let lightboxTimerPopoverOpen = false;

function elem(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function imageReadyItems(items) {
  return (items || []).filter((item) => item && (item.master_image_url || item.thumbnail_url));
}

function sanitizeAutoplaySeconds(value) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  if (!Number.isFinite(parsed)) {
    return 5;
  }
  return Math.max(1, Math.min(parsed, 31536000));
}

function lightboxAutoplayIntervalMs() {
  return sanitizeAutoplaySeconds(elem("autoplay_seconds").value) * 1000;
}

function renderLightboxTimerButton() {
  const button = elem("lightbox_timer");
  const seconds = sanitizeAutoplaySeconds(elem("autoplay_seconds").value);

  button.textContent = `${seconds}s`;
  button.setAttribute("aria-label", `Set autoplay timer (${seconds} seconds)`);
  button.setAttribute("aria-expanded", String(lightboxTimerPopoverOpen));
}

function setLightboxTimerPopover(open) {
  lightboxTimerPopoverOpen = Boolean(open);

  const popover = elem("lightbox_timer_popover");
  const input = elem("autoplay_seconds");
  popover.classList.toggle("is-hidden", !lightboxTimerPopoverOpen);
  renderLightboxTimerButton();

  if (!lightboxTimerPopoverOpen) {
    return;
  }

  input.value = String(sanitizeAutoplaySeconds(input.value));
  input.focus();
  input.select();
}

function setView(view) {
  currentView = view === VIEW_MASTER ? VIEW_MASTER : VIEW_GALLERY;

  elem("gallery_view_btn").classList.toggle("is-active", currentView === VIEW_GALLERY);
  elem("master_view_btn").classList.toggle("is-active", currentView === VIEW_MASTER);

  elem("results_grid").classList.toggle("is-hidden", currentView !== VIEW_GALLERY);
  elem("master_view").classList.toggle("is-hidden", currentView !== VIEW_MASTER);

  if (currentView === VIEW_MASTER) {
    renderMasterView();
  }
}

function masterItemPool() {
  return imageReadyItems(currentItems);
}

function renderMasterView() {
  const pool = masterItemPool();
  const image = elem("master_image");
  const empty = elem("master_empty");

  if (pool.length === 0) {
    image.style.display = "none";
    empty.style.display = "block";
    elem("master_title").textContent = "No image-ready items";
    elem("master_subtitle").textContent = "Current search results do not include thumbnail or master images.";
    elem("master_link").style.visibility = "hidden";
    elem("master_position").textContent = "0 / 0";
    elem("master_prev_btn").disabled = true;
    elem("master_next_btn").disabled = true;
    return;
  }

  masterIndex = Math.max(0, Math.min(masterIndex, pool.length - 1));
  const item = pool[masterIndex];
  const imageUrl = item.master_image_url || item.thumbnail_url;

  image.src = imageUrl;
  image.alt = item.title || "master image";
  image.style.display = "block";
  empty.style.display = "none";

  elem("master_title").textContent = item.title || "(untitled)";
  elem("master_subtitle").textContent = `${item.collection || "unknown"} | ${item.date_raw || "n/a"}`;

  const link = elem("master_link");
  link.href = item.url || "#";
  link.style.visibility = item.url ? "visible" : "hidden";

  elem("master_position").textContent = `${masterIndex + 1} / ${pool.length}`;
  elem("master_prev_btn").disabled = pool.length <= 1;
  elem("master_next_btn").disabled = pool.length <= 1;
}

function stepMaster(delta) {
  const pool = masterItemPool();
  if (pool.length === 0) {
    return;
  }
  masterIndex = (masterIndex + delta + pool.length) % pool.length;
  renderMasterView();
}

function openMasterForItem(itemId) {
  const pool = masterItemPool();
  const wantedId = String(itemId);
  const index = pool.findIndex((item) => String(item.item_id) === wantedId);
  if (index >= 0) {
    masterIndex = index;
  }
  setView(VIEW_MASTER);
}

function itemImageUrl(item) {
  if (!item) {
    return "";
  }
  return item.master_image_url || item.thumbnail_url || "";
}

function lightboxPool() {
  return imageReadyItems(currentItems);
}

function updateLightboxMetaWidth() {
  const meta = elem("lightbox_meta");
  const controls = meta.querySelector(".lightbox-meta-controls");
  if (!controls) {
    return;
  }

  const styles = window.getComputedStyle(meta);
  const padLeft = Number.parseFloat(styles.paddingLeft) || 0;
  const padRight = Number.parseFloat(styles.paddingRight) || 0;
  const controlsWidth = Math.ceil(controls.getBoundingClientRect().width + padLeft + padRight);
  meta.style.setProperty("--meta-controls-width", `${controlsWidth}px`);
}

function renderLightboxModeButton() {
  const modeButton = elem("lightbox_mode");
  const pool = lightboxPool();
  const canCycle = pool.length > 1;

  modeButton.disabled = !canCycle;

  if (lightboxMode === "autoplay") {
    modeButton.setAttribute("aria-pressed", "true");
    modeButton.setAttribute("aria-label", "Autoplay running");
    modeButton.innerHTML = "&#9654;";
    modeButton.classList.add("is-pressed");
    return;
  }

  if (lightboxMode === "shuffle") {
    modeButton.setAttribute("aria-pressed", "false");
    modeButton.setAttribute("aria-label", "Shuffle mode");
    modeButton.innerHTML = "&#8644;";
    modeButton.classList.add("is-pressed");
    return;
  }

  modeButton.setAttribute("aria-pressed", "false");
  modeButton.setAttribute("aria-label", "Autoplay paused");
  modeButton.innerHTML = "&#9654;";
  modeButton.classList.remove("is-pressed");
}

function stopLightboxAutoplay() {
  if (lightboxAutoplayTimer) {
    window.clearInterval(lightboxAutoplayTimer);
    lightboxAutoplayTimer = null;
  }
}

function scheduleLightboxAutoplay(runInitialShuffle) {
  stopLightboxAutoplay();

  const pool = lightboxPool();
  if (pool.length <= 1) {
    lightboxMode = "paused";
    renderLightboxModeButton();
    renderLightboxTimerButton();
    updateLightboxMetaWidth();
    return;
  }

  const intervalMs = lightboxAutoplayIntervalMs();

  if (lightboxMode === "autoplay") {
    lightboxAutoplayTimer = window.setInterval(() => {
      stepLightbox(1);
    }, intervalMs);
  }

  if (lightboxMode === "shuffle") {
    if (runInitialShuffle) {
      runLightboxShuffle();
    }
    lightboxAutoplayTimer = window.setInterval(() => {
      runLightboxShuffle();
    }, intervalMs);
  }

  renderLightboxModeButton();
  renderLightboxTimerButton();
  updateLightboxMetaWidth();
}

function setLightboxMode(mode) {
  lightboxMode = mode;
  scheduleLightboxAutoplay(true);
}

function refreshLightboxTimer() {
  if (lightboxMode === "paused") {
    renderLightboxTimerButton();
    return;
  }

  scheduleLightboxAutoplay(false);
}

function cycleLightboxMode() {
  if (lightboxMode === "paused") {
    setLightboxMode("autoplay");
    return;
  }
  if (lightboxMode === "autoplay") {
    setLightboxMode("shuffle");
    return;
  }
  setLightboxMode("paused");
}

function runLightboxShuffle() {
  const pool = lightboxPool();
  if (pool.length <= 1) {
    return;
  }

  // Uniformly sample from the returned image query pool.
  let candidate = lightboxIndex;
  while (candidate === lightboxIndex) {
    candidate = Math.floor(Math.random() * pool.length);
  }
  setLightboxItem(candidate);
}

function renderLightboxControls(poolLength) {
  const hasItems = poolLength > 0;
  const prev = elem("lightbox_prev");
  const next = elem("lightbox_next");

  prev.hidden = !hasItems || lightboxIndex <= 0;
  prev.disabled = !hasItems || lightboxIndex <= 0;

  next.hidden = !hasItems || lightboxIndex >= poolLength - 1;
  next.disabled = !hasItems || lightboxIndex >= poolLength - 1;

  renderLightboxModeButton();
  renderLightboxTimerButton();
  updateLightboxMetaWidth();
}

function setLightboxItem(index) {
  const pool = lightboxPool();
  if (pool.length === 0) {
    return;
  }

  lightboxIndex = Math.max(0, Math.min(index, pool.length - 1));
  const item = pool[lightboxIndex];
  const imageUrl = itemImageUrl(item);

  elem("lightbox_image").src = imageUrl;
  elem("lightbox_image").alt = item.title || "selected image";

  elem("lightbox_title").textContent = item.title || "(untitled)";
  elem("lightbox_subtitle").textContent = `${item.collection || "unknown"} | ${item.date_raw || "n/a"}`;
  elem("lightbox_collection").textContent = item.collection || "n/a";
  elem("lightbox_date").textContent = item.date_raw || "n/a";
  elem("lightbox_item_id").textContent = item.item_id || "n/a";

  const yearStart = item.year_start == null ? "?" : String(item.year_start);
  const yearEnd = item.year_end == null ? "?" : String(item.year_end);
  elem("lightbox_years").textContent = `${yearStart} - ${yearEnd}`;

  const link = elem("lightbox_link");
  link.href = item.url || "#";
  link.style.visibility = item.url ? "visible" : "hidden";

  renderLightboxControls(pool.length);
}

function stepLightbox(delta) {
  const pool = lightboxPool();
  if (pool.length === 0) {
    return;
  }

  const nextIndex = Math.max(0, Math.min(lightboxIndex + delta, pool.length - 1));
  if (nextIndex === lightboxIndex) {
    if (lightboxAutoplayTimer && lightboxIndex === pool.length - 1) {
      setLightboxMode("paused");
    }
    return;
  }
  setLightboxItem(nextIndex);
}

function setLightboxMetaCollapsed(collapsed) {
  lightboxMetaCollapsed = Boolean(collapsed);
  if (lightboxMetaCollapsed) {
    setLightboxTimerPopover(false);
  }

  const meta = elem("lightbox_meta");
  const dialog = elem("lightbox_dialog");
  const toggle = elem("lightbox_meta_toggle");

  meta.classList.toggle("is-collapsed", lightboxMetaCollapsed);
  dialog.classList.toggle("meta-collapsed", lightboxMetaCollapsed);

  toggle.textContent = lightboxMetaCollapsed ? "+" : "-";
  toggle.setAttribute("aria-label", lightboxMetaCollapsed ? "Expand metadata" : "Collapse metadata");
  toggle.setAttribute("aria-expanded", String(!lightboxMetaCollapsed));
  updateLightboxMetaWidth();
}

function openLightboxForItem(itemId) {
  const pool = lightboxPool();
  const wantedId = String(itemId || "");
  const index = pool.findIndex((item) => String(item.item_id) === wantedId);
  if (index < 0) {
    return;
  }

  lightboxLastFocus = document.activeElement;

  const panel = elem("lightbox");
  panel.classList.remove("is-hidden");
  panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("no-scroll");
  setLightboxTimerPopover(false);
  setLightboxMode("paused");
  setLightboxItem(index);
  setLightboxMetaCollapsed(false);
  updateLightboxMetaWidth();
  elem("lightbox_close").focus();
}

function closeLightbox() {
  const panel = elem("lightbox");
  panel.classList.add("is-hidden");
  panel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("no-scroll");
  elem("lightbox_image").removeAttribute("src");
  setLightboxTimerPopover(false);
  setLightboxMode("paused");

  if (lightboxLastFocus && typeof lightboxLastFocus.focus === "function") {
    lightboxLastFocus.focus();
  }
  lightboxLastFocus = null;
}

function currentFilterFromForm() {
  return {
    collection: elem("collection").value.trim(),
    year_from: elem("year_from").value ? Number(elem("year_from").value) : null,
    year_to: elem("year_to").value ? Number(elem("year_to").value) : null,
    any_term: elem("any_term").value.trim(),
    subject: elem("subject").value.trim(),
    location: elem("location").value.trim(),
    tag: elem("tag").value.trim(),
    contributor: elem("contributor").value.trim(),
    fts: elem("fts").value.trim(),
    limit: Number(elem("limit").value || 60),
    shuffle: elem("shuffle").checked,
    exclude_portraits: elem("exclude_portraits").checked,
    autoplay_seconds: sanitizeAutoplaySeconds(elem("autoplay_seconds").value),
  };
}

function applyFilterToForm(filter) {
  ids.forEach((id) => {
    if (!(id in filter)) {
      return;
    }
    if (id === "shuffle" || id === "exclude_portraits") {
      elem(id).checked = Boolean(filter[id]);
      return;
    }
    if (id === "autoplay_seconds") {
      elem(id).value = String(sanitizeAutoplaySeconds(filter[id] ?? 5));
      return;
    }
    elem(id).value = filter[id] ?? "";
  });

  renderLightboxTimerButton();
}

function renderChips(filter) {
  const chips = elem("active_chips");
  chips.innerHTML = "";

  const labels = {
    collection: "collection",
    year_from: "year>=",
    year_to: "year<=",
    any_term: "any",
    subject: "subject",
    location: "location",
    tag: "tag",
    contributor: "contributor",
    fts: "fts",
    limit: "limit",
    shuffle: "shuffle",
    exclude_portraits: "exclude portraits",
    autoplay_seconds: "timer",
  };

  Object.entries(filter).forEach(([key, value]) => {
    if (value === "" || value === null || value === false) {
      return;
    }
    const displayValue = key === "autoplay_seconds" ? `${sanitizeAutoplaySeconds(value)}s` : String(value);
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = `${labels[key] || key}: ${displayValue}`;
    chips.appendChild(chip);
  });
}

function resultCard(item) {
  const safeTitle = escapeHtml(item.title || "(untitled)");
  const safeCollection = escapeHtml(item.collection || "unknown");
  const safeDate = escapeHtml(item.date_raw || "n/a");
  const safeUrl = escapeHtml(item.url || "#");
  const previewUrl = item.master_image_url || item.thumbnail_url || "";
  const imageSrc = escapeHtml(previewUrl);
  const imageAlt = previewUrl ? safeTitle : "No preview available";

  const imageTag = previewUrl
    ? `
      <button class="card-image-hit" type="button" aria-label="Open image preview for ${safeTitle}">
        <img class="thumb" loading="lazy" src="${imageSrc}" alt="${imageAlt}">
      </button>
    `
    : `<div class="thumb thumb--placeholder" aria-hidden="true"></div>`;

  return `
    <article class="card" data-item-id="${escapeHtml(item.item_id)}">
      ${imageTag}
      <div class="meta">
        <div class="meta-kicker">${safeCollection}</div>
        <h3>${safeTitle}</h3>
        <p>${safeDate}</p>
        <div class="meta-actions">
          <a href="${safeUrl}" target="_blank" rel="noreferrer">Open record</a>
        </div>
      </div>
    </article>
  `;
}

function wireGridEvents() {
  const cards = elem("results_grid").querySelectorAll(".card");
  cards.forEach((card) => {
    const itemId = card.getAttribute("data-item-id");
    const imageHit = card.querySelector(".card-image-hit");
    if (!imageHit || !itemId) {
      return;
    }
    imageHit.addEventListener("click", () => {
      openLightboxForItem(itemId);
    });
  });
}

async function loadFacets() {
  const res = await fetch("/api/facets?limit=120");
  const data = await res.json();
  const facets = data.facets || {};

  function fillDatalist(id, values) {
    const list = elem(id);
    list.innerHTML = "";
    values.forEach((entry) => {
      const opt = document.createElement("option");
      opt.value = entry.value;
      list.appendChild(opt);
    });
  }

  fillDatalist("subjects_list", facets.subjects || []);
  fillDatalist("locations_list", facets.locations || []);
  fillDatalist("tags_list", facets.tags || []);
  fillDatalist("contributors_list", facets.contributors || []);
}

async function loadCollections() {
  const res = await fetch("/api/collections?limit=120");
  const data = await res.json();
  const collections = data.collections || [];

  const collectionSelect = elem("collection");
  const selected = collectionSelect.value;
  collectionSelect.innerHTML = `<option value="">(any collection)</option>`;

  collections.forEach((entry) => {
    const opt = document.createElement("option");
    opt.value = entry.value;
    opt.textContent = `${entry.value} (${entry.count})`;
    collectionSelect.appendChild(opt);
  });

  if (selected) {
    collectionSelect.value = selected;
  }
}

async function applyAndRender(filter) {
  const res = await fetch("/api/results", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filter),
  });
  const data = await res.json();

  renderChips(data.applied_filter || filter);
  elem("result_count").textContent = `${data.count || 0} results shown`;
  currentItems = data.items || [];

  const grid = elem("results_grid");
  if (!data.items || data.items.length === 0) {
    grid.innerHTML = `<p>No results for current filter.</p>`;
    masterIndex = 0;
    renderMasterView();
    return;
  }

  grid.innerHTML = data.items.map(resultCard).join("\n");
  wireGridEvents();
  masterIndex = 0;
  renderMasterView();
}

async function loadActiveFilter() {
  const res = await fetch("/api/filter");
  const data = await res.json();
  const filter = data.filter || {};
  applyFilterToForm(filter);
  elem("active-meta").textContent = data.updated_at
    ? `Active filter last saved: ${data.updated_at}`
    : "No saved active filter yet.";
  return filter;
}

async function saveActiveFilter() {
  const payload = currentFilterFromForm();
  const res = await fetch("/api/filter", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  renderChips(data.filter || payload);
  renderLightboxTimerButton();
  elem("active-meta").textContent = `Active filter last saved: ${data.updated_at}`;
}

function clearForm() {
  applyFilterToForm({
    collection: "",
    year_from: null,
    year_to: null,
    any_term: "",
    subject: "",
    location: "",
    tag: "",
    contributor: "",
    fts: "",
    limit: 60,
    shuffle: false,
    exclude_portraits: false,
    autoplay_seconds: 5,
  });
}

async function boot() {
  // Load collections first so the dropdown is ready quickly.
  const collectionsPromise = loadCollections();

  // Facets can be expensive to compute on large datasets. Load them in the
  // background so active filter/results appear immediately.
  const facetsPromise = loadFacets();

  const activeFilter = await loadActiveFilter();
  await applyAndRender(activeFilter);

  collectionsPromise.catch((err) => {
    console.error(err);
  });

  facetsPromise.catch((err) => {
    console.error(err);
  });

  elem("apply_btn").addEventListener("click", async () => {
    await applyAndRender(currentFilterFromForm());
  });

  elem("gallery_view_btn").addEventListener("click", () => {
    setView(VIEW_GALLERY);
  });

  elem("master_view_btn").addEventListener("click", () => {
    setView(VIEW_MASTER);
  });

  elem("master_prev_btn").addEventListener("click", () => {
    stepMaster(-1);
  });

  elem("master_next_btn").addEventListener("click", () => {
    stepMaster(1);
  });

  elem("lightbox_backdrop").addEventListener("click", () => {
    closeLightbox();
  });

  elem("lightbox_timer").addEventListener("click", (event) => {
    event.stopPropagation();
    setLightboxTimerPopover(!lightboxTimerPopoverOpen);
  });

  elem("autoplay_seconds").addEventListener("change", async () => {
    elem("autoplay_seconds").value = String(sanitizeAutoplaySeconds(elem("autoplay_seconds").value));
    setLightboxTimerPopover(false);
    refreshLightboxTimer();
    await saveActiveFilter();
  });

  elem("autoplay_seconds").addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      elem("autoplay_seconds").dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setLightboxTimerPopover(false);
    }
  });

  elem("lightbox_close").addEventListener("click", () => {
    closeLightbox();
  });

  elem("lightbox_meta_toggle").addEventListener("click", () => {
    setLightboxMetaCollapsed(!lightboxMetaCollapsed);
  });

  elem("lightbox_prev").addEventListener("click", () => {
    stepLightbox(-1);
  });

  elem("lightbox_next").addEventListener("click", () => {
    stepLightbox(1);
  });

  elem("lightbox_mode").addEventListener("click", () => {
    cycleLightboxMode();
  });

  document.addEventListener("click", (event) => {
    if (elem("lightbox").classList.contains("is-hidden")) {
      return;
    }
    if (!lightboxTimerPopoverOpen) {
      return;
    }
    if (event.target.closest("#lightbox_timer_wrap")) {
      return;
    }
    setLightboxTimerPopover(false);
  });

  window.addEventListener("resize", () => {
    if (elem("lightbox").classList.contains("is-hidden")) {
      return;
    }
    updateLightboxMetaWidth();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (elem("lightbox").classList.contains("is-hidden")) {
      return;
    }
    closeLightbox();
  });

  elem("save_btn").addEventListener("click", async () => {
    await saveActiveFilter();
  });

  elem("load_btn").addEventListener("click", async () => {
    const f = await loadActiveFilter();
    await applyAndRender(f);
  });

  elem("clear_btn").addEventListener("click", async () => {
    clearForm();
    await applyAndRender(currentFilterFromForm());
  });

  setView(VIEW_GALLERY);
}

boot().catch((err) => {
  console.error(err);
  elem("results_grid").innerHTML = `<p>Failed to load app. Check server logs.</p>`;
});
