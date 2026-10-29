(function () {
  "use strict";

  const data = window.ROADMAP_DATA || { domains: [], notes: {}, repositoryUrl: "", branch: "main" };
  const PROGRESS_KEY = "roadmap.progress.v1";
  const UI_STATE_KEY = "roadmap.ui.v1";
  const THEME_KEY = "roadmap.theme";

  const uiState = loadJson(UI_STATE_KEY, { open: {} });
  const repositoryProfiles = Array.isArray(data.profiles) ? data.profiles : [];
  let activeProfile = null;
  let progress = {};
  const domainsBySlug = new Map(data.domains.map((domain) => [domain.slug, domain]));
  const itemElements = new Map();
  const tracks = Array.isArray(data.tracks) ? data.tracks : [];
  let activeTrack = tracks.find((track) => track.slug === uiState.track) || null;
  let trackItemKeys = new Set(activeTrack ? activeTrack.items : []);

  function inTrack(domain, item) {
    return !activeTrack || trackItemKeys.has(domain.slug + ":" + item.id);
  }

  function loadJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function saveJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      /* storage may be unavailable in private windows; the page still works for this session */
    }
  }

  function progressKey(domain, item) {
    return domain.slug + ":" + item.id;
  }

  /* ---------- profiles ---------- */

  function storageKeyFor(profileName) {
    return PROGRESS_KEY + ":" + profileName;
  }

  function knownProfileNames() {
    const names = new Set(repositoryProfiles.map((profile) => profile.name));
    for (const name of uiState.localProfiles || []) {
      names.add(name);
    }
    if (activeProfile) {
      names.add(activeProfile);
    }
    return Array.from(names).sort();
  }

  function repositoryProfile(profileName) {
    return repositoryProfiles.find((profile) => profile.name === profileName) || null;
  }

  function saveProgress() {
    saveJson(storageKeyFor(activeProfile), progress);
  }

  function loadProfile(profileName) {
    activeProfile = profileName;
    uiState.profile = profileName;
    uiState.localProfiles = Array.from(new Set([...(uiState.localProfiles || []), profileName]));
    const local = loadJson(storageKeyFor(profileName), null);
    const fromRepository = repositoryProfile(profileName);
    progress = local ? local : {};
    if (fromRepository) {
      uiState.mergedVersions = uiState.mergedVersions || {};
      const alreadyMerged = uiState.mergedVersions[profileName] === fromRepository.updatedAt;
      if (!local || !alreadyMerged) {
        for (const [key, value] of Object.entries(fromRepository.progress)) {
          if (!progress[key]) {
            progress[key] = value;
          }
        }
        uiState.mergedVersions[profileName] = fromRepository.updatedAt;
      }
    }
    saveProgress();
    saveJson(UI_STATE_KEY, uiState);
  }

  function migrateLegacyProgress() {
    const legacy = loadJson(PROGRESS_KEY, null);
    if (legacy && Object.keys(legacy).length && !loadJson(storageKeyFor("me"), null)) {
      saveJson(storageKeyFor("me"), legacy);
      uiState.localProfiles = Array.from(new Set([...(uiState.localProfiles || []), "me"]));
    }
  }

  function unsavedChangeCount() {
    const fromRepository = repositoryProfile(activeProfile);
    const baseline = fromRepository ? fromRepository.progress : {};
    let count = 0;
    for (const key of Object.keys(progress)) {
      if (!baseline[key]) {
        count += 1;
      }
    }
    for (const key of Object.keys(baseline)) {
      if (!progress[key]) {
        count += 1;
      }
    }
    return count;
  }

  function renderProfileStatus() {
    const status = document.getElementById("profile-status");
    const fromRepository = repositoryProfile(activeProfile);
    const unsaved = unsavedChangeCount();
    let text = "Profile " + activeProfile;
    if (fromRepository) {
      text += " · repository copy " + (fromRepository.updatedAt ? fromRepository.updatedAt.slice(0, 10) : "saved");
    } else {
      text += " · not yet saved in the repository";
    }
    if (unsaved) {
      text += " · " + unsaved + " change" + (unsaved === 1 ? "" : "s") + " not saved to the repository";
    }
    status.textContent = text;
  }

  function setupProfileSelectorValue() {
    const select = document.getElementById("profile-select");
    if (select && Array.from(select.options).some((option) => option.value === activeProfile)) {
      select.value = activeProfile;
    }
  }

  function setupProfileSelector() {
    const select = document.getElementById("profile-select");
    function fill() {
      select.innerHTML = knownProfileNames()
        .map((name) => '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + (repositoryProfile(name) ? " (in repository)" : "") + "</option>")
        .join("") + '<option value="__new__">New profile…</option>';
      select.value = activeProfile;
    }
    fill();
    select.addEventListener("change", () => {
      if (select.value === "__new__") {
        const name = (window.prompt("Profile name (letters, digits, dot, dash or underscore):", "") || "").trim().toLowerCase();
        if (!/^[a-z0-9][a-z0-9._-]{0,39}$/.test(name)) {
          select.value = activeProfile;
          return;
        }
        loadProfile(name);
      } else {
        loadProfile(select.value);
      }
      fill();
      renderDomains();
      refreshCounts();
      applyFilters(document.getElementById("search").value);
    });
  }

  /* ---------- progress in a link ---------- */

  function canonicalItemKeys() {
    const keys = [];
    for (const domain of data.domains) {
      for (const section of domain.sections) {
        for (const item of flattenItems(section.items, [])) {
          keys.push(domain.slug + ":" + item.id);
        }
      }
    }
    return keys;
  }

  function encodeProgressLink() {
    const keys = canonicalItemKeys();
    const bytes = new Uint8Array(Math.ceil(keys.length / 8));
    keys.forEach((key, index) => {
      if (progress[key]) {
        bytes[index >> 3] |= 1 << (index & 7);
      }
    });
    let binary = "";
    bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
    const encoded = btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return location.href.split("#")[0] + "#p=" + encodeURIComponent(activeProfile) + "." + keys.length + "." + encoded;
  }

  function importProgressFromHash(hash) {
    const match = /^p=([^.]+)\.(\d+)\.([A-Za-z0-9_-]+)$/.exec(hash);
    if (!match) {
      return false;
    }
    const profileName = decodeURIComponent(match[1]);
    const count = Number(match[2]);
    const keys = canonicalItemKeys();
    if (count !== keys.length) {
      window.alert("This progress link was made for a different version of the roadmap and cannot be applied safely.");
      return true;
    }
    const binary = atob(match[3].replace(/-/g, "+").replace(/_/g, "/"));
    if (/^[a-z0-9][a-z0-9._-]{0,39}$/.test(profileName) && profileName !== activeProfile) {
      loadProfile(profileName);
    }
    let added = 0;
    keys.forEach((key, index) => {
      const byte = binary.charCodeAt(index >> 3);
      if ((byte >> (index & 7)) & 1 && !progress[key]) {
        progress[key] = new Date().toISOString().slice(0, 10);
        added += 1;
      }
    });
    saveProgress();
    window.alert("Loaded " + added + " completed item" + (added === 1 ? "" : "s") + " from the link into profile " + activeProfile + ".");
    return true;
  }

  function copyProgressLink() {
    const link = encodeProgressLink();
    const done = () => window.alert("Link copied. Open it on any device to load this progress into profile " + activeProfile + ".");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(done, () => window.prompt("Copy this link:", link));
    } else {
      window.prompt("Copy this link:", link);
    }
  }

  function isDone(domain, item) {
    return Boolean(progress[progressKey(domain, item)]);
  }

  function flattenItems(items, accumulator) {
    for (const item of items) {
      accumulator.push(item);
      flattenItems(item.children, accumulator);
    }
    return accumulator;
  }

  function domainItems(domain) {
    const accumulator = [];
    for (const section of domain.sections) {
      flattenItems(section.items, accumulator);
    }
    return accumulator.filter((item) => inTrack(domain, item));
  }

  function countDone(domain, items) {
    return items.reduce((count, item) => count + (isDone(domain, item) ? 1 : 0), 0);
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function githubUrl(path) {
    if (!data.repositoryUrl) {
      return null;
    }
    return data.repositoryUrl.replace(/\/$/, "") + "/blob/" + (data.branch || "main") + "/" + path;
  }

  /* ---------- theme ---------- */

  function applyTheme(theme) {
    if (theme === "dark" || theme === "light") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }

  function currentTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) {
      return stored;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function toggleTheme() {
    const next = currentTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  }

  /* ---------- map ---------- */

  function computeLevels() {
    const levels = new Map();
    const visiting = new Set();
    function levelOf(slug) {
      if (levels.has(slug)) {
        return levels.get(slug);
      }
      if (visiting.has(slug)) {
        return 0;
      }
      visiting.add(slug);
      const domain = domainsBySlug.get(slug);
      let level = 0;
      for (const prerequisite of domain.prerequisites) {
        if (domainsBySlug.has(prerequisite)) {
          level = Math.max(level, levelOf(prerequisite) + 1);
        }
      }
      visiting.delete(slug);
      levels.set(slug, level);
      return level;
    }
    for (const domain of data.domains) {
      levelOf(domain.slug);
    }
    return levels;
  }

  function renderMap() {
    const container = document.getElementById("map");
    if (!data.domains.length) {
      container.innerHTML = '<p class="empty">No domains yet. Add a folder like 01-foundations/README.md and run tools/build.py.</p>';
      return;
    }
    const levels = computeLevels();
    const columns = new Map();
    for (const domain of data.domains) {
      const level = levels.get(domain.slug);
      if (!columns.has(level)) {
        columns.set(level, []);
      }
      columns.get(level).push(domain);
    }
    const nodeWidth = 176;
    const nodeHeight = 58;
    const columnGap = 70;
    const rowGap = 18;
    const padding = 16;
    const columnCount = Math.max(...columns.keys()) + 1;
    const maxRows = Math.max(...Array.from(columns.values()).map((list) => list.length));
    const width = padding * 2 + columnCount * nodeWidth + (columnCount - 1) * columnGap;
    const height = padding * 2 + maxRows * nodeHeight + (maxRows - 1) * rowGap;
    const positions = new Map();
    for (const [level, list] of columns) {
      const columnHeight = list.length * nodeHeight + (list.length - 1) * rowGap;
      const startY = padding + (height - padding * 2 - columnHeight) / 2;
      list.forEach((domain, rowIndex) => {
        positions.set(domain.slug, {
          x: padding + level * (nodeWidth + columnGap),
          y: startY + rowIndex * (nodeHeight + rowGap),
        });
      });
    }

    let edges = "";
    for (const domain of data.domains) {
      const target = positions.get(domain.slug);
      for (const prerequisite of domain.prerequisites) {
        const source = positions.get(prerequisite);
        if (!source) {
          continue;
        }
        const startX = source.x + nodeWidth;
        const startY = source.y + nodeHeight / 2;
        const endX = target.x;
        const endY = target.y + nodeHeight / 2;
        const bend = (endX - startX) / 2;
        edges += '<path class="edge" marker-end="url(#arrow)" d="M' + startX + " " + startY +
          " C" + (startX + bend) + " " + startY + ", " + (endX - bend) + " " + endY + ", " + (endX - 4) + " " + endY + '"/>';
      }
    }

    let nodes = "";
    for (const domain of data.domains) {
      const position = positions.get(domain.slug);
      const items = domainItems(domain);
      const done = countDone(domain, items);
      const percent = items.length ? Math.round((done / items.length) * 100) : 0;
      const trackWidth = nodeWidth - 24;
      nodes += '<g class="node" data-slug="' + domain.slug + '" transform="translate(' + position.x + "," + position.y + ')">' +
        '<rect class="box" width="' + nodeWidth + '" height="' + nodeHeight + '"/>' +
        '<text x="12" y="22">' + escapeHtml(domain.title) + "</text>" +
        '<text class="pct" x="' + (nodeWidth - 12) + '" y="22" text-anchor="end" data-role="pct">' + percent + "%</text>" +
        '<rect class="track" x="12" y="36" width="' + trackWidth + '" height="8" rx="4"/>' +
        '<rect class="progress" x="12" y="36" width="' + (trackWidth * percent / 100) + '" height="8" rx="4" data-role="progress" data-track="' + trackWidth + '"/>' +
        "</g>";
    }

    container.innerHTML =
      '<svg viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="Domain dependency map">' +
      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
      '<path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted)" opacity="0.7"/></marker></defs>' +
      edges + nodes + "</svg>";

    container.querySelectorAll(".node").forEach((node) => {
      node.addEventListener("click", () => {
        openDomain(node.getAttribute("data-slug"), true);
      });
    });
  }

  function updateMapNode(domain) {
    const node = document.querySelector('.map .node[data-slug="' + domain.slug + '"]');
    if (!node) {
      return;
    }
    const items = domainItems(domain);
    const done = countDone(domain, items);
    const percent = items.length ? Math.round((done / items.length) * 100) : 0;
    node.querySelector('[data-role="pct"]').textContent = items.length ? percent + "%" : "–";
    node.classList.toggle("off-track", Boolean(activeTrack) && items.length === 0);
    const progressBar = node.querySelector('[data-role="progress"]');
    progressBar.setAttribute("width", String(Number(progressBar.getAttribute("data-track")) * percent / 100));
  }

  /* ---------- checklist ---------- */

  function renderLinkChips(links) {
    return links.map((link) => {
      if (link.kind === "note" && link.path && data.notes[link.path]) {
        return '<a class="chip note" href="#note=' + encodeURIComponent(link.path) + '" data-note="' + escapeHtml(link.path) + '" title="' + escapeHtml(data.notes[link.path].title) + '">' + escapeHtml(link.label) + "</a>";
      }
      if (link.kind === "note" || link.kind === "file") {
        const url = link.path ? githubUrl(link.path) : link.url;
        return '<a class="chip article" href="' + escapeHtml(url || link.url) + '" target="_blank" rel="noopener">' + escapeHtml(link.label) + "</a>";
      }
      return '<a class="chip ' + link.kind + '" href="' + escapeHtml(link.url) + '" target="_blank" rel="noopener" title="' + escapeHtml(link.url) + '">' + escapeHtml(link.label) + "</a>";
    }).join("");
  }

  function renderItem(domain, item) {
    const listItem = document.createElement("li");
    listItem.className = "item" + (isDone(domain, item) ? " done" : "");
    listItem.id = "item-" + domain.slug + "-" + item.id.replace(/\./g, "-");
    const key = progressKey(domain, item);
    listItem.innerHTML =
      '<div class="item-row">' +
      '<input type="checkbox" id="check-' + key.replace(/[:.]/g, "-") + '" ' + (isDone(domain, item) ? "checked" : "") + ' aria-label="Mark ' + escapeHtml(item.text) + ' as done">' +
      '<label class="item-id" for="check-' + key.replace(/[:.]/g, "-") + '">' + item.id + "</label>" +
      '<div class="item-main"><label class="item-text" for="check-' + key.replace(/[:.]/g, "-") + '">' + escapeHtml(item.text) + "</label>" +
      '<span class="links">' + renderLinkChips(item.links) + "</span></div>" +
      "</div>";
    const checkbox = listItem.querySelector('input[type="checkbox"]');
    checkbox.addEventListener("change", () => {
      setDone(domain, item, checkbox.checked);
    });
    if (item.children.length) {
      const childList = document.createElement("ul");
      childList.className = "items";
      for (const child of item.children) {
        childList.appendChild(renderItem(domain, child));
      }
      listItem.appendChild(childList);
    }
    itemElements.set(key, { element: listItem, domain, item });
    return listItem;
  }

  function renderSection(domain, section) {
    const details = document.createElement("details");
    details.className = "rsection";
    const stateKey = domain.slug + "/" + section.id;
    details.dataset.sectionKey = stateKey;
    details.open = uiState.open[stateKey] !== false;
    const items = flattenItems(section.items, []).filter((item) => inTrack(domain, item));
    details.innerHTML =
      '<summary><span class="chevron">▶</span><h4>' + section.id + ". " + escapeHtml(section.title) + "</h4>" +
      '<span class="count" data-role="count"></span>' +
      '<button class="btn small" data-role="mark-all" title="Mark every item in this section as done">Mark all</button></summary>';
    const list = document.createElement("ul");
    list.className = "items";
    for (const item of section.items) {
      list.appendChild(renderItem(domain, item));
    }
    details.appendChild(list);
    details.addEventListener("toggle", () => {
      uiState.open[stateKey] = details.open;
      saveJson(UI_STATE_KEY, uiState);
    });
    details.querySelector('[data-role="mark-all"]').addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const allDone = items.every((item) => isDone(domain, item));
      for (const item of items) {
        setDone(domain, item, !allDone, true);
      }
      refreshCounts();
    });
    details.updateCount = function () {
      const done = countDone(domain, items);
      details.querySelector('[data-role="count"]').textContent = done + " / " + items.length;
      details.querySelector('[data-role="mark-all"]').textContent = done === items.length && items.length ? "Unmark all" : "Mark all";
    };
    details.updateCount();
    return details;
  }

  function renderDomain(domain) {
    const details = document.createElement("details");
    details.className = "domain";
    details.id = "domain-" + domain.slug;
    details.open = uiState.open[domain.slug] === true;
    const items = domainItems(domain);
    const prerequisites = domain.prerequisites
      .filter((slug) => domainsBySlug.has(slug))
      .map((slug) => '<a href="#' + slug + '" data-domain="' + slug + '">' + escapeHtml(domainsBySlug.get(slug).title) + "</a>")
      .join(", ");
    const readmeUrl = githubUrl(domain.directory + "/README.md");
    details.innerHTML =
      "<summary>" +
      '<span class="chevron">▶</span>' +
      '<div class="domain-title"><h3>' + String(domain.order).padStart(2, "0") + " · " + escapeHtml(domain.title) + "</h3>" +
      '<span class="summary">' + escapeHtml(domain.summary) + "</span></div>" +
      '<div class="domain-progress"><div class="bar"><div class="fill" data-role="fill"></div></div><span class="count" data-role="count"></span></div>' +
      "</summary>" +
      '<div class="domain-body">' +
      '<div class="domain-meta">' +
      "<span>Prerequisites: " + (prerequisites || "none") + "</span>" +
      (readmeUrl ? '<a href="' + readmeUrl + '" target="_blank" rel="noopener">Roadmap on GitHub ↗</a>' : "") +
      "<span>" + domain.noteCount + " notes in this domain</span>" +
      "</div>" +
      (domain.abilities.length
        ? '<div class="abilities"><b>Done when you can</b><ul>' + domain.abilities.map((ability) => "<li>" + escapeHtml(ability) + "</li>").join("") + "</ul></div>"
        : "") +
      renderNotesList(domain) +
      "</div>";
    const body = details.querySelector(".domain-body");
    for (const section of domain.sections) {
      body.appendChild(renderSection(domain, section));
    }
    details.addEventListener("toggle", () => {
      uiState.open[domain.slug] = details.open;
      saveJson(UI_STATE_KEY, uiState);
    });
    details.updateCount = function () {
      const done = countDone(domain, items);
      const percent = items.length ? Math.round((done / items.length) * 100) : 0;
      details.querySelector('[data-role="fill"]').style.width = percent + "%";
      details.querySelector('[data-role="count"]').textContent = done + " / " + items.length + " · " + percent + "%";
      details.querySelectorAll(".rsection").forEach((section) => section.updateCount());
    };
    details.updateCount();
    return details;
  }

  function domainNotes(domain) {
    const prefix = domain.directory + "/";
    return Object.entries(data.notes)
      .filter(([path]) => path.startsWith(prefix))
      .map(([path, note]) => ({ path, title: note.title, summary: note.summary }))
      .sort((left, right) => left.title.localeCompare(right.title));
  }

  function renderNotesList(domain) {
    const notes = domainNotes(domain);
    if (!notes.length) {
      return "";
    }
    return '<details class="notes-list"><summary><span class="chevron">▶</span><h4>Notes in this domain</h4><span class="count">' + notes.length + "</span></summary><ul>" +
      notes.map((note) =>
        '<li><a class="chip note" href="#note=' + encodeURIComponent(note.path) + '" data-note="' + escapeHtml(note.path) + '">' + escapeHtml(note.title) + "</a>" +
        (note.summary ? '<span class="note-summary">' + escapeHtml(note.summary) + "</span>" : "") + "</li>"
      ).join("") + "</ul></details>";
  }

  function renderDomains() {
    const container = document.getElementById("domains");
    container.innerHTML = "";
    itemElements.clear();
    if (!data.domains.length) {
      container.innerHTML = '<p class="empty">Nothing to show yet.</p>';
      return;
    }
    for (const domain of data.domains) {
      container.appendChild(renderDomain(domain));
    }
    container.addEventListener("click", (event) => {
      const noteLink = event.target.closest("[data-note]");
      if (noteLink) {
        event.preventDefault();
        openNote(noteLink.getAttribute("data-note"));
        return;
      }
      const domainLink = event.target.closest("[data-domain]");
      if (domainLink) {
        event.preventDefault();
        openDomain(domainLink.getAttribute("data-domain"), true);
      }
    });
  }

  function setDone(domain, item, done, deferRefresh) {
    const key = progressKey(domain, item);
    if (done) {
      progress[key] = new Date().toISOString().slice(0, 10);
    } else {
      delete progress[key];
    }
    saveProgress();
    const entry = itemElements.get(key);
    if (entry) {
      entry.element.classList.toggle("done", done);
      entry.element.querySelector('input[type="checkbox"]').checked = done;
    }
    if (!deferRefresh) {
      refreshCounts();
    }
  }

  function refreshCounts() {
    let total = 0;
    let done = 0;
    for (const domain of data.domains) {
      const items = domainItems(domain);
      total += items.length;
      done += countDone(domain, items);
      const element = document.getElementById("domain-" + domain.slug);
      if (element) {
        element.updateCount();
      }
      updateMapNode(domain);
    }
    const percent = total ? Math.round((done / total) * 100) : 0;
    document.getElementById("overall-fill").style.width = percent + "%";
    document.getElementById("overall-text").textContent = done + " / " + total + " · " + percent + "%";
    if (activeTrack) {
      renderTrackPanel();
    }
    renderProfileStatus();
  }

  function openDomain(slug, scroll) {
    const element = document.getElementById("domain-" + slug);
    if (!element) {
      return;
    }
    element.open = true;
    if (scroll) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function highlightItem(slug, itemId) {
    const entry = itemElements.get(slug + ":" + itemId);
    if (!entry) {
      return;
    }
    openDomain(slug, false);
    let parent = entry.element.parentElement;
    while (parent) {
      if (parent.tagName === "DETAILS") {
        parent.open = true;
      }
      parent = parent.parentElement;
    }
    entry.element.scrollIntoView({ behavior: "smooth", block: "center" });
    const row = entry.element.querySelector(".item-row");
    row.classList.add("flash");
    setTimeout(() => row.classList.remove("flash"), 2500);
  }

  /* ---------- filters: track and search ---------- */

  let searchTimer = null;

  function restoreOpenStates(domainsContainer) {
    domainsContainer.querySelectorAll("details").forEach((details) => {
      if (details.classList.contains("domain")) {
        details.open = uiState.open[details.id.replace("domain-", "")] === true;
      } else if (details.dataset.sectionKey) {
        details.open = uiState.open[details.dataset.sectionKey] !== false;
      }
    });
  }

  function applyFilters(query) {
    const normalised = (query || "").trim().toLowerCase();
    const domainsContainer = document.getElementById("domains");
    const filtering = Boolean(normalised) || Boolean(activeTrack);
    for (const { element, domain, item } of itemElements.values()) {
      const haystack = (item.id + " " + item.text + " " + item.links.map((link) => link.label).join(" ")).toLowerCase();
      const matches = !normalised || haystack.includes(normalised);
      element.dataset.match = matches && inTrack(domain, item) ? "1" : "0";
      element.classList.add("hidden");
      element.classList.remove("context");
    }
    for (const { element } of itemElements.values()) {
      if (element.dataset.match === "1") {
        let ancestor = element;
        while (ancestor && ancestor.id !== "domains") {
          if (ancestor.classList && ancestor.classList.contains("hidden") && ancestor.tagName === "LI") {
            ancestor.classList.remove("hidden");
            if (ancestor.dataset.match === "0") {
              ancestor.classList.add("context");
            }
          }
          if (ancestor.tagName === "DETAILS" && filtering) {
            ancestor.open = true;
          }
          ancestor = ancestor.parentElement;
        }
      }
    }
    domainsContainer.querySelectorAll(".rsection").forEach((section) => {
      const visible = section.querySelectorAll("li.item:not(.hidden)").length > 0;
      section.classList.toggle("hidden", !visible);
    });
    domainsContainer.querySelectorAll(".domain").forEach((domain) => {
      const visible = domain.querySelectorAll(".rsection:not(.hidden)").length > 0;
      domain.classList.toggle("hidden", !visible);
      if (visible && normalised) {
        domain.open = true;
      }
    });
    if (!filtering) {
      restoreOpenStates(domainsContainer);
    }
  }

  /* ---------- tracks ---------- */

  function trackProgress(track) {
    let done = 0;
    for (const key of track.items) {
      if (progress[key]) {
        done += 1;
      }
    }
    return { done, total: track.items.length };
  }

  function renderTrackPanel() {
    const panel = document.getElementById("track-panel");
    if (!activeTrack) {
      panel.classList.add("hidden");
      return;
    }
    const { done, total } = trackProgress(activeTrack);
    const percent = total ? Math.round((done / total) * 100) : 0;
    const planMarkdown = activeTrack.content.replace(/^## Items[\s\S]*?(?=^## )/m, "");
    panel.innerHTML =
      '<div class="track-head"><div><h2>' + escapeHtml(activeTrack.title) + "</h2>" +
      '<p class="muted">' + escapeHtml(activeTrack.summary) + "</p></div>" +
      '<div class="track-progress"><div class="bar"><div class="fill" style="width:' + percent + '%"></div></div>' +
      '<span class="count">' + done + " / " + total + " items · " + percent + "%" + (activeTrack.hours ? " · " + escapeHtml(activeTrack.hours) : "") + "</span></div></div>" +
      '<details class="track-plan"><summary>Plan and day-by-day schedule</summary><div class="markdown">' +
      (window.marked ? window.marked.parse(planMarkdown) : "<pre>" + escapeHtml(planMarkdown) + "</pre>") +
      "</div></details>";
    panel.classList.remove("hidden");
  }

  function selectTrack(slug) {
    activeTrack = tracks.find((track) => track.slug === slug) || null;
    trackItemKeys = new Set(activeTrack ? activeTrack.items : []);
    uiState.track = activeTrack ? activeTrack.slug : "";
    saveJson(UI_STATE_KEY, uiState);
    renderDomains();
    refreshCounts();
    renderTrackPanel();
    applyFilters(document.getElementById("search").value);
  }

  function setupTrackSelector() {
    const select = document.getElementById("track-select");
    if (!tracks.length) {
      select.classList.add("hidden");
      return;
    }
    select.innerHTML = '<option value="">All items</option>' +
      tracks.map((track) => '<option value="' + escapeHtml(track.slug) + '">Track: ' + escapeHtml(track.title) + "</option>").join("");
    select.value = activeTrack ? activeTrack.slug : "";
    select.addEventListener("change", () => selectTrack(select.value));
  }

  /* ---------- reader ---------- */

  const reader = document.getElementById("reader");
  const readerBackdrop = document.getElementById("reader-backdrop");
  const readerContent = document.getElementById("reader-content");
  const readerPath = document.getElementById("reader-path");
  const readerGithub = document.getElementById("reader-github");

  function resolveRelativePath(basePath, href) {
    try {
      const resolved = new URL(href, "file:///" + basePath);
      return decodeURIComponent(resolved.pathname.replace(/^\//, ""));
    } catch (error) {
      return href;
    }
  }

  function openNote(path) {
    const note = data.notes[path];
    if (!note) {
      return;
    }
    const html = window.marked ? window.marked.parse(note.content) : "<pre>" + escapeHtml(note.content) + "</pre>";
    readerContent.innerHTML = html;
    readerPath.textContent = path;
    const url = githubUrl(path);
    readerGithub.classList.toggle("hidden", !url);
    if (url) {
      readerGithub.href = url;
    }
    readerContent.querySelectorAll("a[href]").forEach((anchor) => {
      const href = anchor.getAttribute("href");
      if (/^https?:\/\//.test(href) || href.startsWith("mailto:")) {
        anchor.target = "_blank";
        anchor.rel = "noopener";
        return;
      }
      if (href.startsWith("#")) {
        return;
      }
      const targetPath = resolveRelativePath(path, href).split("#")[0];
      const domainMatch = data.domains.find((domain) => domain.directory + "/README.md" === targetPath);
      if (domainMatch) {
        anchor.href = "#" + domainMatch.slug;
        anchor.addEventListener("click", (event) => {
          event.preventDefault();
          closeReader();
          openDomain(domainMatch.slug, true);
        });
        return;
      }
      if (data.notes[targetPath]) {
        anchor.href = "#note=" + encodeURIComponent(targetPath);
        anchor.addEventListener("click", (event) => {
          event.preventDefault();
          openNote(targetPath);
        });
        return;
      }
      const external = githubUrl(targetPath);
      if (external) {
        anchor.href = external;
        anchor.target = "_blank";
        anchor.rel = "noopener";
      }
    });
    if (window.hljs) {
      readerContent.querySelectorAll("pre code").forEach((block) => {
        try {
          window.hljs.highlightElement(block);
        } catch (error) {
          /* unsupported language: leave the block as plain text */
        }
      });
    }
    reader.classList.remove("hidden");
    readerBackdrop.classList.remove("hidden");
    reader.setAttribute("aria-hidden", "false");
    readerContent.scrollTop = 0;
    document.body.style.overflow = "hidden";
    if (location.hash !== "#note=" + encodeURIComponent(path)) {
      history.replaceState(null, "", "#note=" + encodeURIComponent(path));
    }
  }

  function closeReader() {
    reader.classList.add("hidden");
    readerBackdrop.classList.add("hidden");
    reader.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (location.hash.startsWith("#note=")) {
      history.replaceState(null, "", location.pathname + location.search);
    }
  }

  /* ---------- export / import / reset ---------- */

  function exportProgress() {
    const payload = {
      format: "software-engineering-roadmap-progress",
      version: 1,
      profile: activeProfile,
      exportedAt: new Date().toISOString(),
      progress,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = activeProfile + ".json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(anchor.href);
  }

  function importProgress(file) {
    const fileReader = new FileReader();
    fileReader.onload = () => {
      try {
        const parsed = JSON.parse(String(fileReader.result));
        const imported = parsed && parsed.progress && typeof parsed.progress === "object" ? parsed.progress : parsed;
        let count = 0;
        for (const [key, value] of Object.entries(imported)) {
          if (value && typeof key === "string" && key.includes(":")) {
            progress[key] = typeof value === "string" ? value : new Date().toISOString().slice(0, 10);
            count += 1;
          }
        }
        saveProgress();
        renderDomains();
        refreshCounts();
        applyFilters(document.getElementById("search").value);
        window.alert("Imported " + count + " completed items into profile " + activeProfile + ".");
      } catch (error) {
        window.alert("That file does not look like an exported progress file.");
      }
    };
    fileReader.readAsText(file);
  }

  function resetProgress() {
    if (!window.confirm("Clear the progress of profile " + activeProfile + " in this browser? Save a file first if you want a backup.")) {
      return;
    }
    for (const key of Object.keys(progress)) {
      delete progress[key];
    }
    saveProgress();
    renderDomains();
    refreshCounts();
  }

  /* ---------- routing ---------- */

  function handleHash() {
    const rawHash = location.hash.replace(/^#/, "");
    if (rawHash.startsWith("p=")) {
      if (importProgressFromHash(rawHash)) {
        history.replaceState(null, "", location.pathname + location.search);
        renderDomains();
        refreshCounts();
        applyFilters(document.getElementById("search").value);
        setupProfileSelectorValue();
      }
      return;
    }
    const hash = decodeURIComponent(rawHash);
    if (!hash) {
      return;
    }
    if (hash.startsWith("note=")) {
      openNote(hash.slice(5));
      return;
    }
    const [slug, itemId] = hash.split("/");
    if (itemId) {
      highlightItem(slug, itemId);
    } else if (domainsBySlug.has(slug)) {
      openDomain(slug, true);
    }
  }

  /* ---------- boot ---------- */

  function boot() {
    applyTheme(localStorage.getItem(THEME_KEY));
    migrateLegacyProgress();
    const initialProfile = uiState.profile || (uiState.localProfiles || [])[0] || (repositoryProfiles[0] ? repositoryProfiles[0].name : "me");
    loadProfile(initialProfile);
    renderMap();
    renderDomains();
    refreshCounts();
    setupProfileSelector();
    setupTrackSelector();
    renderTrackPanel();
    applyFilters("");

    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
    document.getElementById("export-btn").addEventListener("click", exportProgress);
    document.getElementById("link-btn").addEventListener("click", copyProgressLink);
    document.getElementById("reset-btn").addEventListener("click", resetProgress);
    document.getElementById("import-input").addEventListener("change", (event) => {
      const [file] = event.target.files;
      if (file) {
        importProgress(file);
      }
      event.target.value = "";
    });
    document.getElementById("reader-close").addEventListener("click", closeReader);
    readerBackdrop.addEventListener("click", closeReader);

    const searchInput = document.getElementById("search");
    searchInput.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => applyFilters(searchInput.value), 120);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!reader.classList.contains("hidden")) {
          closeReader();
        } else if (document.activeElement === searchInput && searchInput.value) {
          searchInput.value = "";
          applyFilters("");
        }
      }
      if (event.key === "/" && document.activeElement !== searchInput && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        searchInput.focus();
      }
    });

    const footerMeta = document.getElementById("footer-meta");
    const totalNotes = Object.keys(data.notes).length;
    footerMeta.textContent = data.domains.length + " domains · " + totalNotes + " notes · data generated " + (data.generatedAt ? data.generatedAt.slice(0, 10) : "locally");
    const footerRepo = document.getElementById("footer-repo");
    if (data.repositoryUrl) {
      footerRepo.href = data.repositoryUrl;
    } else {
      footerRepo.classList.add("hidden");
    }

    window.addEventListener("hashchange", handleHash);
    handleHash();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
