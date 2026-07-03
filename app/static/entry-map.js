const entryMap = document.querySelector("[data-entry-map]");

if (entryMap) {
  const data = JSON.parse(entryMap.querySelector("[data-entry-map-data]").textContent);
  const nodes = entryMap.querySelector("[data-map-nodes]");
  const mindMap = entryMap.querySelector("[data-mind-map]");
  const title = entryMap.querySelector("[data-map-title]");
  const summary = entryMap.querySelector("[data-map-summary]");
  const kicker = entryMap.querySelector("[data-map-kicker]");
  const sideTitle = entryMap.querySelector("[data-map-side-title]");
  const sideSummary = entryMap.querySelector("[data-map-side-summary]");
  const level = entryMap.querySelector("[data-map-level]");
  const breadcrumb = entryMap.querySelector("[data-map-breadcrumb]");
  const reset = entryMap.querySelector("[data-map-reset]");
  const search = entryMap.querySelector("[data-entry-search]");
  const searchButton = entryMap.querySelector("[data-entry-search-button]");
  const searchResults = entryMap.querySelector("[data-entry-search-results]");

  const allSubjects = data.flatMap((category) =>
    category.subthemes.flatMap((subtheme) =>
      subtheme.subjects.map((subject) => ({ category, subtheme, subject })),
    ),
  );

  const setBreadcrumb = (items) => {
    breadcrumb.querySelectorAll("[data-crumb]").forEach((item) => item.remove());
    items.forEach((item) => {
      const span = document.createElement("span");
      span.dataset.crumb = "true";
      span.textContent = item;
      breadcrumb.append(span);
    });
  };

  const placeNode = (button, index, total) => {
    const maxPerRing = 8;
    const ring = Math.floor(index / maxPerRing);
    const indexInRing = index % maxPerRing;
    const itemsInRing = Math.min(maxPerRing, total - ring * maxPerRing);
    const angle = -90 + (360 / itemsInRing) * indexInRing;
    const radius = 250 + ring * 175;
    button.style.setProperty("--node-angle", `${angle}deg`);
    button.style.setProperty("--node-radius", `${radius}px`);
    return radius;
  };

  const resizeMapFor = (items) => {
    const rings = Math.max(1, Math.ceil(items.length / 8));
    const outerRadius = 250 + (rings - 1) * 175;
    const size = Math.max(660, outerRadius * 2 + 340);
    mindMap.style.minHeight = `${size}px`;
    mindMap.style.minWidth = `${size}px`;
  };

  const renderNodes = (items, kind, handler) => {
    nodes.replaceChildren();
    resizeMapFor(items);
    items.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "mind-node";
      placeNode(button, index, items.length);
      button.innerHTML = `
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${item.label || item.title}</strong>
        <small>${kind}</small>
        ${item.has_official_traces ? '<small class="mind-node-badge">✓ Données réelles</small>' : ""}
      `;
      button.addEventListener("click", () => handler(item));
      nodes.append(button);
    });
  };

  const renderCategories = () => {
    kicker.textContent = "Départ";
    title.textContent = "Débat public";
    summary.textContent = "Sélectionnez une grande catégorie pour afficher sa carte mentale.";
    level.textContent = "Étape 1";
    sideTitle.textContent = "Grandes catégories";
    sideSummary.textContent = "Chaque nœud ouvre une nouvelle carte centrée sur votre choix.";
    setBreadcrumb([]);
    renderNodes(data, "Grande catégorie", renderSubthemes);
  };

  const renderSubthemes = (category) => {
    kicker.textContent = "Catégorie";
    title.textContent = category.label;
    summary.textContent = category.summary;
    level.textContent = "Étape 2";
    sideTitle.textContent = "Sous-catégories";
    sideSummary.textContent = "Choisissez une sous-catégorie pour afficher les sujets précis qu'elle contient.";
    setBreadcrumb([category.label]);
    renderNodes(category.subthemes, "Sous-catégorie", (subtheme) => renderSubjects(category, subtheme));
  };

  const renderSubjects = (category, subtheme) => {
    kicker.textContent = "Sous-catégorie";
    title.textContent = subtheme.label;
    summary.textContent = subtheme.summary;
    level.textContent = "Étape 3";
    sideTitle.textContent = "Sujets précis";
    sideSummary.textContent = "Cliquez sur un sujet pour ouvrir sa fiche complète.";
    setBreadcrumb([category.label, subtheme.label]);
    renderNodes(subtheme.subjects, "Sujet précis", (subject) => {
      window.location.href = `/sujets/${subject.id}`;
    });
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
      link.innerHTML = `<strong>${subject.title}</strong><span>${category.label} · ${subtheme.label}</span>${subject.has_official_traces ? '<small class="mind-node-badge">✓ Données réelles</small>' : ""}`;
      searchResults.append(link);
    });
  };

  reset.addEventListener("click", renderCategories);
  searchButton.addEventListener("click", runSearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });

  renderCategories();
}
