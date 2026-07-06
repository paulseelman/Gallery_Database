const config = window.VIEWER_CONFIG || {};

const pollMs = Math.max(5000, Number(config.pollSeconds || 20) * 1000);
const slideMs = Math.max(2000, Number(config.slideSeconds || 8) * 1000);

let playlist = [];
let cursor = 0;
let rotationTimer = null;
let lastUpdatedAt = null;

function elem(id) {
  return document.getElementById(id);
}

function normalizeItems(items) {
  return (items || []).filter((item) => item && (item.master_image_url || item.thumbnail_url));
}

function humanFilterSummary(activeFilter) {
  const entries = Object.entries(activeFilter || {}).filter(([, value]) => {
    if (value === null || value === "" || value === false) {
      return false;
    }
    return true;
  });
  if (entries.length === 0) {
    return "active filter: none";
  }
  return `active filter: ${entries.map(([k, v]) => `${k}=${v}`).join(" | ")}`;
}

function renderEmpty(message) {
  elem("slide_image").style.display = "none";
  elem("empty_state").style.display = "grid";
  elem("empty_state").textContent = message;
  elem("item_title").textContent = "No image-ready items";
  elem("item_subtitle").textContent = "Current active selection does not include thumbnail URLs.";
  elem("item_link").style.visibility = "hidden";
}

function renderItem(item) {
  const image = elem("slide_image");
  const imageUrl = item.master_image_url || item.thumbnail_url;
  image.style.display = "block";
  elem("empty_state").style.display = "none";

  image.classList.remove("visible");
  image.src = imageUrl;
  image.onload = () => image.classList.add("visible");

  elem("item_title").textContent = item.title || "Untitled";
  elem("item_subtitle").textContent = `${item.collection || "unknown"} | ${item.date_raw || "n/a"}`;

  const link = elem("item_link");
  link.href = item.url || "#";
  link.style.visibility = item.url ? "visible" : "hidden";
}

function nextSlide() {
  if (playlist.length === 0) {
    renderEmpty("No images available from active selection.");
    return;
  }
  if (cursor >= playlist.length) {
    cursor = 0;
  }
  renderItem(playlist[cursor]);
  cursor += 1;
}

function restartRotation() {
  if (rotationTimer) {
    clearInterval(rotationTimer);
  }
  nextSlide();
  rotationTimer = setInterval(nextSlide, slideMs);
}

async function pollSelection() {
  try {
    const res = await fetch("/api/selection", { cache: "no-store" });
    const data = await res.json();

    const fetchedAt = data.fetched_at || "unknown";
    const count = Number(data.count || 0);
    const source = data.source || "local";
    elem("sync_status").textContent = `sync: ${source} @ ${fetchedAt}`;
    elem("selection_meta").textContent = `selection: ${count} items`;
    elem("filter_summary").textContent = humanFilterSummary(data.active_filter || {});

    if (data.error) {
      elem("sync_status").textContent += ` | warning: ${data.error}`;
    }

    const shouldRefreshPlaylist = data.updated_at !== lastUpdatedAt;
    if (shouldRefreshPlaylist) {
      lastUpdatedAt = data.updated_at || null;
      playlist = normalizeItems(data.items || []);
      cursor = 0;
      restartRotation();
    } else if (!rotationTimer) {
      restartRotation();
    }
  } catch (err) {
    elem("sync_status").textContent = `sync error: ${err}`;
  }
}

async function boot() {
  await pollSelection();
  setInterval(pollSelection, pollMs);
}

boot().catch((err) => {
  elem("sync_status").textContent = `boot error: ${err}`;
});
