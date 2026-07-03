const entryMap = document.querySelector("[data-entry-map]");

if (entryMap) {
  const data = JSON.parse(entryMap.querySelector("[data-entry-map-data]").textContent);
  const nodes = entryMap.querySelector("[data-map-nodes]");
  const mindMap = entryMap.querySelector("[data-mind-map]");
  const title = entryMap.querySelector("[data-map-title]");
  const search = entryMap.querySelector("[data-entry-search]");
  const searchButton = entryMap.querySelector("[data-entry-search-button]");
  const searchResults = entryMap.querySelector("[data-entry-search-results]");
  let selectedCategory = null;
  let selectedSubtheme = null;

  const allSubjects = data.flatMap((category) =>
    category.subthemes.flatMap((subtheme) =>
      subtheme.subjects.map((subject) => ({ category, subtheme, subject })),
    ),
  );

  const getItemKey = (item) => item.id || item.title || item.label;
  const nodeMetrics = {
    current: { width: 180, gap: 58, minRadius: 255 },
    branch: { width: 160, gap: 64, minRadius: 385 },
    previous: { width: 96, gap: 42, minRadius: 190 },
    branchPrevious: { width: 110, gap: 42, minRadius: 315 },
    ancestor: { width: 64, gap: 30, minRadius: 170 },
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

  const getAngle = (index, total, angleOffset = -90) => angleOffset + (360 / total) * index;

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
          if (node.dataset.removing === "true") {
            node.remove();
          }
        }, 520);
      }
    });
    nodes.querySelectorAll("[data-ring-key]").forEach((guide) => {
      if (!activeRingKeys.has(guide.dataset.ringKey)) {
        guide.dataset.removing = "true";
        guide.style.opacity = "0";
        guide.style.setProperty("--ring-size", "0px");
        window.setTimeout(() => {
          if (guide.dataset.removing === "true") {
            guide.remove();
          }
        }, 520);
      }
    });
  };

  const resizeMapFor = (rings) => {
    const outerRadius = Math.max(...rings.map((ring) => ring.radius));
    const size = Math.max(660, outerRadius * 2 + 220);
    mindMap.style.minHeight = `${size}px`;
    mindMap.style.minWidth = `${size}px`;
  };

  const renderNode = ({ item, index, total, radius, angleOffset, className, selectedId, handler }) => {
    const key = getItemKey(item);
    let button = nodes.querySelector(`[data-node-key="${key}"]`);
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
      <strong>${item.label || item.title}</strong>
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
    const categoryIndex = selectedCategory ? data.findIndex((item) => item.id === selectedCategory.id) : -1;
    const subthemeIndex =
      selectedCategory && selectedSubtheme
        ? selectedCategory.subthemes.findIndex((item) => item.id === selectedSubtheme.id)
        : -1;
    const subthemeAngleOffset =
      selectedCategory && selectedCategory.subthemes.length > 0
        ? getChildAngleOffset(categoryIndex, data.length, selectedCategory.subthemes.length)
        : -90;
    const subjectAngleOffset =
      selectedCategory && selectedSubtheme && selectedSubtheme.subjects.length > 0
        ? getChildAngleOffset(subthemeIndex, selectedCategory.subthemes.length, selectedSubtheme.subjects.length, subthemeAngleOffset)
        : -90;

    if (!selectedCategory) {
      title.textContent = "Débat public";
      rings.push({
        items: data,
        radius: 250,
        className: "is-current",
        selectedId: null,
        handler: (category) => {
          selectedCategory = category;
          selectedSubtheme = null;
          renderMap();
        },
      });
    } else if (!selectedSubtheme) {
      title.textContent = selectedCategory.label;
      rings.push(
        {
          items: data,
          radius: fitRadius(190, data.length, "is-previous"),
          className: "is-previous",
          selectedId: selectedCategory.id,
          handler: (category) => {
            selectedCategory = category;
            selectedSubtheme = null;
            renderMap();
          },
        },
        {
          items: selectedCategory.subthemes,
          radius: fitRadius(410, selectedCategory.subthemes.length, "is-current is-branch"),
          angleOffset: subthemeAngleOffset,
          className: "is-current is-branch",
          selectedId: null,
          handler: (subtheme) => {
            selectedSubtheme = subtheme;
            renderMap();
          },
        },
      );
    } else {
      title.textContent = selectedSubtheme.label;
      rings.push(
        {
          items: data,
          radius: fitRadius(170, data.length, "is-ancestor"),
          className: "is-ancestor",
          selectedId: selectedCategory.id,
          handler: (category) => {
            selectedCategory = category;
            selectedSubtheme = null;
            renderMap();
          },
        },
        {
          items: selectedCategory.subthemes,
          radius: fitRadius(315, selectedCategory.subthemes.length, "is-previous is-branch-previous"),
          angleOffset: subthemeAngleOffset,
          className: "is-previous is-branch-previous",
          selectedId: selectedSubtheme.id,
          handler: (subtheme) => {
            selectedSubtheme = subtheme;
            renderMap();
          },
        },
        {
          items: selectedSubtheme.subjects,
          radius: fitRadius(490, selectedSubtheme.subjects.length, "is-current"),
          angleOffset: subjectAngleOffset,
          className: "is-current",
          selectedId: null,
          handler: (subject) => {
            window.location.href = `/sujets/${subject.id}`;
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

  const runSearch = () => {
    const query = search.value.trim().toLocaleLowerCase("fr-FR");
    searchResults.replaceChildren();
    if (query.length < 2) {
      searchResults.textContent = "Saisissez au moins deux caractères.";
      return;
    }

    const matches = allSubjects.filter(({ category, subtheme, subject }) =>
      [
        category.label,
        subtheme.label,
        subject.title,
        subject.summary,
        subject.context,
        ...(subject.legal_texts || []).map((text) => `${text.title} ${text.summary}`),
      ]
        .join(" ")
        .toLocaleLowerCase("fr-FR")
        .includes(query),
    );

    if (matches.length === 0) {
      searchResults.textContent = "Aucun sujet correspondant dans la démonstration.";
      return;
    }

    matches.forEach(({ category, subtheme, subject }) => {
      const link = document.createElement("a");
      link.className = "search-result";
      link.href = `/sujets/${subject.id}`;
      link.innerHTML = `<strong>${subject.title}</strong><span>${category.label} · ${subtheme.label}</span>`;
      searchResults.append(link);
    });
  };

  searchButton.addEventListener("click", runSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });

  renderMap();
}
