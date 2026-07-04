const entryMap = document.querySelector("[data-entry-map]");

if (entryMap) {
  const nodes = entryMap.querySelector("[data-map-nodes]");
  const mindMap = entryMap.querySelector("[data-mind-map]");
  const title = entryMap.querySelector("[data-map-title]");
  const search = entryMap.querySelector("[data-entry-search]");
  const searchButton = entryMap.querySelector("[data-entry-search-button]");
  const searchResults = entryMap.querySelector("[data-entry-search-results]");
  const cache = new Map();
  const state = {
    rootGroups: [],
    categoryGroup: null,
    categories: [],
    category: null,
    subthemes: [],
    subthemeGroup: null,
    subtheme: null,
    groups: [],
    group: null,
    subjects: [],
  };

  const nodeMetrics = {
    current: { width: 150, gap: 34, minRadius: 235 },
    branch: { width: 145, gap: 36, minRadius: 320 },
    previous: { width: 96, gap: 42, minRadius: 190 },
    branchPrevious: { width: 110, gap: 42, minRadius: 315 },
    ancestor: { width: 64, gap: 30, minRadius: 170 },
  };

  const labelFor = (item) => item.label || item.title || "Sujet";
  const getItemKey = (item) => `${item.kind || "item"}:${item.category_id || ""}:${item.subtheme_id || ""}:${item.id || labelFor(item)}`;
  const endpoint = (path) => `/api/entry-map${path}`;

  const fetchJson = async (path) => {
    const url = endpoint(path);
    if (!cache.has(url)) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Chargement impossible (${response.status})`);
      cache.set(url, await response.json());
    }
    return cache.get(url);
  };

  const getNodeMetrics = (className) => {
    if (className.includes("is-branch-previous")) return nodeMetrics.branchPrevious;
    if (className.includes("is-branch")) return nodeMetrics.branch;
    if (className.includes("is-ancestor")) return nodeMetrics.ancestor;
    if (className.includes("is-previous")) return nodeMetrics.previous;
    return nodeMetrics.current;
  };

  const fitRadius = (baseRadius, itemCount, className) => {
    const { width, gap, minRadius } = getNodeMetrics(className);
    const radiusForSpacing = (itemCount * (width + gap)) / (Math.PI * 2);
    return Math.ceil(Math.max(baseRadius, minRadius, radiusForSpacing));
  };

  const getAngle = (index, total, angleOffset = -90) => angleOffset + (360 / Math.max(1, total)) * index;

  const getChildAngleOffset = (parentIndex, parentTotal, childTotal, parentAngleOffset = -90) => {
    const parentAngle = getAngle(parentIndex, parentTotal, parentAngleOffset);
    return parentAngle + (childTotal === 1 ? 0 : 90);
  };

  const placeNode = (button, index, total, radius, angleOffset = -90) => {
    const angle = getAngle(index, total, angleOffset);
    button.style.setProperty("--node-angle", `${angle}deg`);
    button.style.setProperty("--node-radius", `${radius}px`);
  };

  const renderRingGuide = (radius, className) => {
    let guide = nodes.querySelector(`[data-ring-key="${className}"]`);
    if (!guide) {
      guide = document.createElement("div");
      guide.className = "mind-ring-guide";
      guide.dataset.ringKey = className;
      guide.style.opacity = "0";
      guide.style.setProperty("--ring-size", "0px");
      nodes.append(guide);
    }
    guide.className = `mind-ring-guide ${className}`;
    delete guide.dataset.removing;
    requestAnimationFrame(() => {
      guide.style.opacity = "1";
      guide.style.setProperty("--ring-size", `${radius * 2}px`);
    });
    return guide;
  };

  const removeStaleElements = (activeNodeKeys, activeRingKeys) => {
    nodes.querySelectorAll("[data-node-key]").forEach((node) => {
      if (!activeNodeKeys.has(node.dataset.nodeKey)) {
        node.dataset.removing = "true";
        node.style.opacity = "0";
        node.style.setProperty("--node-radius", "0px");
        window.setTimeout(() => {
          if (node.dataset.removing === "true") node.remove();
        }, 520);
      }
    });
    nodes.querySelectorAll("[data-ring-key]").forEach((guide) => {
      if (!activeRingKeys.has(guide.dataset.ringKey)) {
        guide.dataset.removing = "true";
        guide.style.opacity = "0";
        guide.style.setProperty("--ring-size", "0px");
        window.setTimeout(() => {
          if (guide.dataset.removing === "true") guide.remove();
        }, 520);
      }
    });
  };

  const resizeMapFor = (rings) => {
    const outerRadius = Math.max(...rings.map((ring) => ring.radius), 250);
    const size = Math.max(660, outerRadius * 2 + 220);
    mindMap.style.minHeight = `${size}px`;
    mindMap.style.minWidth = `${size}px`;
  };

  const renderNode = ({ item, index, total, radius, angleOffset, className, selectedId, handler }) => {
    const key = getItemKey(item);
    let button = nodes.querySelector(`[data-node-key="${CSS.escape(key)}"]`);
    const isSelected = selectedId === item.id;

    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.dataset.nodeKey = key;
      button.style.opacity = "0";
      button.style.setProperty("--node-radius", "0px");
      nodes.append(button);
    }

    button.className = `mind-node ${className}${isSelected ? " is-selected" : ""}`;
    delete button.dataset.removing;
    button.innerHTML = `
      <span>${String(index + 1).padStart(2, "0")}</span>
      <strong>${labelFor(item)}</strong>
    `;
    button.onclick = () => handler(item);

    requestAnimationFrame(() => {
      placeNode(button, index, total, radius, angleOffset);
      button.style.opacity = "1";
    });
  };

  const renderRing = ({ items, radius, angleOffset = -90, className, selectedId, handler }, activeNodeKeys, activeRingKeys) => {
    const guide = renderRingGuide(radius, className);
    activeRingKeys.add(guide.dataset.ringKey);
    items.forEach((item, index) => {
      activeNodeKeys.add(getItemKey(item));
      renderNode({ item, index, total: items.length, radius, angleOffset, className, selectedId, handler });
    });
  };

  const renderMap = () => {
    const rings = [];
    const rootItems = state.categories.length > 0 ? state.categories : state.rootGroups;
    const categoryIndex = state.category ? state.categories.findIndex((item) => item.id === state.category.id) : -1;
    const subthemeIndex = state.subtheme ? state.subthemes.findIndex((item) => item.id === state.subtheme.id) : -1;
    const subthemeAngleOffset =
      state.category && state.subthemes.length > 0
        ? getChildAngleOffset(categoryIndex, state.categories.length, state.subthemes.length)
        : -90;
    const detailItems = state.group ? state.subjects : state.groups.length > 0 ? state.groups : state.subjects;
    const detailAngleOffset =
      state.subtheme && detailItems.length > 0
        ? getChildAngleOffset(subthemeIndex, state.subthemes.length, detailItems.length, subthemeAngleOffset)
        : -90;

    if (!state.category && !state.categoryGroup) {
      title.textContent = "Débat public";
      rings.push({
        items: rootItems,
        radius: fitRadius(250, rootItems.length, "is-current"),
        className: "is-current",
        selectedId: null,
        handler: (item) => {
          if (item.kind === "category_group") {
            selectCategoryGroup(item);
          } else {
            selectCategory(item);
          }
        },
      });
    } else if (!state.category) {
      title.textContent = state.categoryGroup.label;
      rings.push({
        items: rootItems,
        radius: fitRadius(250, rootItems.length, "is-current"),
        className: "is-current",
        selectedId: null,
        handler: (item) => {
          if (item.kind === "category_group") {
            selectCategoryGroup(item);
          } else {
            selectCategory(item);
          }
        },
      });
    } else if (!state.subtheme) {
      title.textContent = state.category.label;
      rings.push(
        {
          items: rootItems,
          radius: fitRadius(190, rootItems.length, "is-previous"),
          className: "is-previous",
          selectedId: state.categoryGroup?.id || state.category.id,
          handler: (item) => {
            if (item.kind === "category_group") {
              selectCategoryGroup(item);
            } else {
              selectCategory(item);
            }
          },
        },
        {
          items: state.subthemes,
          radius: fitRadius(410, state.subthemes.length, "is-current is-branch"),
          angleOffset: subthemeAngleOffset,
          className: "is-current is-branch",
          selectedId: null,
          handler: (item) => {
            if (item.kind === "subtheme_group") {
              selectSubthemeGroup(item);
            } else {
              selectSubtheme(item);
            }
          },
        },
      );
    } else {
      title.textContent = state.group ? state.group.label : state.subtheme.label;
      rings.push(
        {
          items: rootItems,
          radius: fitRadius(170, rootItems.length, "is-ancestor"),
          className: "is-ancestor",
          selectedId: state.categoryGroup?.id || state.category.id,
          handler: (item) => {
            if (item.kind === "category_group") {
              selectCategoryGroup(item);
            } else {
              selectCategory(item);
            }
          },
        },
        {
          items: state.subthemes,
          radius: fitRadius(315, state.subthemes.length, "is-previous is-branch-previous"),
          angleOffset: subthemeAngleOffset,
          className: "is-previous is-branch-previous",
          selectedId: state.subtheme.id,
          handler: (item) => {
            if (item.kind === "subtheme_group") {
              selectSubthemeGroup(item);
            } else {
              selectSubtheme(item);
            }
          },
        },
        {
          items: detailItems,
          radius: fitRadius(490, detailItems.length, "is-current"),
          angleOffset: detailAngleOffset,
          className: "is-current",
          selectedId: state.group?.id,
          handler: (item) => {
            if (item.kind === "group") {
              selectGroup(item);
            } else {
              window.location.href = `/sujets/${item.id}`;
            }
          },
        },
      );
    }

    resizeMapFor(rings);
    const activeNodeKeys = new Set();
    const activeRingKeys = new Set();
    rings.forEach((ring) => renderRing(ring, activeNodeKeys, activeRingKeys));
    removeStaleElements(activeNodeKeys, activeRingKeys);
  };

  const selectCategoryGroup = async (group) => {
    state.categoryGroup = group;
    state.category = null;
    state.subtheme = null;
    state.group = null;
    state.subthemes = [];
    state.groups = [];
    state.subjects = [];
    title.textContent = group.label;
    const payload = await fetchJson(`/category-groups/${encodeURIComponent(group.id)}`);
    if (payload.mode === "groups") {
      state.rootGroups = payload.items;
      state.categories = [];
    } else {
      state.categories = payload.items;
    }
    renderMap();
  };

  const selectCategory = async (category) => {
    state.category = category;
    state.subtheme = null;
    state.subthemeGroup = null;
    state.group = null;
    state.groups = [];
    state.subjects = [];
    title.textContent = category.label;
    const payload = await fetchJson(`/categories/${encodeURIComponent(category.id)}`);
    state.subthemes = payload.items;
    renderMap();
  };

  const selectSubthemeGroup = async (group) => {
    state.subthemeGroup = group;
    state.subtheme = null;
    state.group = null;
    state.groups = [];
    state.subjects = [];
    title.textContent = group.label;
    const payload = await fetchJson(`/categories/${encodeURIComponent(state.category.id)}/subtheme-groups/${encodeURIComponent(group.id)}`);
    state.subthemes = payload.items;
    renderMap();
  };

  const selectSubtheme = async (subtheme) => {
    state.subtheme = subtheme;
    state.subthemeGroup = null;
    state.group = null;
    state.groups = [];
    state.subjects = [];
    title.textContent = subtheme.label;
    const payload = await fetchJson(`/categories/${encodeURIComponent(state.category.id)}/subthemes/${encodeURIComponent(subtheme.id)}`);
    if (payload.mode === "groups") {
      state.groups = payload.items;
    } else {
      state.subjects = payload.items;
    }
    renderMap();
  };

  const selectGroup = async (group) => {
    state.group = group;
    title.textContent = group.label;
    const payload = await fetchJson(
      `/categories/${encodeURIComponent(state.category.id)}/subthemes/${encodeURIComponent(state.subtheme.id)}/groups/${encodeURIComponent(group.id)}`,
    );
    if (payload.mode === "groups") {
      state.groups = payload.items;
      state.subjects = [];
    } else {
      state.groups = [];
      state.subjects = payload.items;
    }
    renderMap();
  };

  const runSearch = async () => {
    const query = search.value.trim();
    searchResults.replaceChildren();
    if (query.length < 2) {
      searchResults.textContent = "Saisissez au moins deux caractères.";
      return;
    }

    const payload = await fetchJson(`/search?q=${encodeURIComponent(query)}`);
    if (payload.items.length === 0) {
      searchResults.textContent = "Aucun sujet correspondant.";
      return;
    }

    payload.items.forEach(({ category, subtheme, subject }) => {
      const link = document.createElement("a");
      link.className = "search-result";
      link.href = `/sujets/${subject.id}`;
      link.innerHTML = `<strong>${subject.title}</strong><span>${category.label} · ${subtheme.label}</span>`;
      searchResults.append(link);
    });
    if (payload.total > payload.limit) {
      const notice = document.createElement("p");
      notice.className = "search-result-note";
      notice.textContent = `${payload.total - payload.limit} résultats supplémentaires. Précisez la recherche.`;
      searchResults.append(notice);
    }
  };

  searchButton.addEventListener("click", runSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });

  fetchJson("")
    .then((payload) => {
      if (payload.mode === "groups") {
        state.rootGroups = payload.items;
      } else {
        state.categories = payload.items;
      }
      renderMap();
    })
    .catch(() => {
      title.textContent = "Chargement impossible";
    });
}
