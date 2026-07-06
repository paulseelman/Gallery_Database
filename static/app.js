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
];

function elem(id) {
  return document.getElementById(id);
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
  };
}

function applyFilterToForm(filter) {
  ids.forEach((id) => {
    if (!(id in filter)) {
      return;
    }
    if (id === "shuffle") {
      elem(id).checked = Boolean(filter[id]);
      return;
    }
    elem(id).value = filter[id] ?? "";
  });
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
  };

  Object.entries(filter).forEach(([key, value]) => {
    if (value === "" || value === null || value === false) {
      return;
    }
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = `${labels[key] || key}: ${String(value)}`;
    chips.appendChild(chip);
  });
}

function resultCard(item) {
  const imageTag = item.thumbnail_url
    ? `<img class="thumb" loading="lazy" src="${item.thumbnail_url}" alt="${item.title}">`
    : `<div class="thumb"></div>`;

  return `
    <article class="card">
      ${imageTag}
      <div class="meta">
        <h3>${item.title || "(untitled)"}</h3>
        <p>${item.collection || "unknown"} | ${item.date_raw || "n/a"}</p>
        <a href="${item.url}" target="_blank" rel="noreferrer">open record</a>
      </div>
    </article>
  `;
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

  const grid = elem("results_grid");
  if (!data.items || data.items.length === 0) {
    grid.innerHTML = `<p>No results for current filter.</p>`;
    return;
  }

  grid.innerHTML = data.items.map(resultCard).join("\n");
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
}

boot().catch((err) => {
  console.error(err);
  elem("results_grid").innerHTML = `<p>Failed to load app. Check server logs.</p>`;
});
