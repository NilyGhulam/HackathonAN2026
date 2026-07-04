const timelines = document.querySelectorAll("[data-timeline-paginated]");

timelines.forEach((timeline) => {
  const pageSize = 10;
  const items = Array.from(timeline.querySelectorAll("[data-timeline-item]"));
  const newer = timeline.querySelector("[data-timeline-newer]");
  const older = timeline.querySelector("[data-timeline-older]");
  const status = timeline.querySelector("[data-timeline-page-status]");
  let page = 0;

  const render = () => {
    const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
    const start = page * pageSize;
    const end = start + pageSize;

    items.forEach((item, index) => {
      item.hidden = index < start || index >= end;
    });

    newer.disabled = page === 0;
    older.disabled = page >= pageCount - 1;
    status.textContent = `Page ${page + 1} sur ${pageCount}`;
  };

  newer.addEventListener("click", () => {
    page = Math.max(0, page - 1);
    render();
  });

  older.addEventListener("click", () => {
    page = Math.min(Math.ceil(items.length / pageSize) - 1, page + 1);
    render();
  });

  render();
});

const argumentGraphs = document.querySelectorAll("[data-argument-graph]");

const partyColor = (party = "") => {
  const value = party.toLocaleLowerCase("fr-FR");
  if (value.includes("droite") || value.includes("conservatrice")) return "#009fe3";
  if (value.includes("gauche") || value.includes("écolog") || value.includes("social")) return "#a558a8";
  if (value.includes("majoritaire")) return "#000091";
  if (value.includes("centr")) return "#6a6af4";
  return "#777777";
};

const partySide = (party = "") => {
  const value = party.toLocaleLowerCase("fr-FR");
  if (value.includes("droite") || value.includes("conservatrice")) return 1;
  if (value.includes("gauche") || value.includes("écolog") || value.includes("social")) return -1;
  if (value.includes("centr")) return 0;
  if (value.includes("majoritaire")) return .35;
  return 0;
};

const hasPoliticalPosition = (party = "") => {
  const value = party.toLocaleLowerCase("fr-FR");
  return !(
    value.includes("sans affiliation") ||
    value.includes("non renseigné") ||
    value.includes("association") ||
    value.includes("collectif")
  );
};

const positionY = (position) => {
  if (position === "for") return 25;
  if (position === "against") return 75;
  return 50;
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const positionSlotY = (position, index, total) => {
  if (total <= 1) return positionY(position);
  const ranges = {
    for: [11, 33],
    neutral: [42, 58],
    against: [67, 89],
  };
  const [start, end] = ranges[position] || ranges.neutral;
  return start + ((end - start) * index) / Math.max(1, total - 1);
};

const sourceSlotY = (position, index, total) => {
  if (total <= 1) return positionY(position);
  const ranges = {
    for: [18, 38],
    neutral: [45, 55],
    against: [64, 84],
  };
  const [start, end] = ranges[position] || ranges.neutral;
  return start + ((end - start) * index) / Math.max(1, total - 1);
};

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const sourceParts = (source = "") => {
  const parts = source.split(",").map((part) => part.trim()).filter(Boolean);
  return {
    place: parts[0] || "Source non renseignée",
    date: parts.slice(1).join(", ") || "Date non renseignée",
  };
};

const sourceUrl = (source = "", explicitUrl = "") => {
  if (explicitUrl) return explicitUrl;
  const value = source.toLocaleLowerCase("fr-FR");
  if (value.includes("sénat") || value.includes("senat")) return "https://www.senat.fr/";
  if (value.includes("assemblée") || value.includes("parlementaire") || value.includes("commission")) {
    return "https://www.assemblee-nationale.fr/";
  }
  return "https://www.vie-publique.fr/";
};

const distributedX = (index, total) => {
  if (total <= 1) return 50;
  const columns = Math.min(4, total);
  const column = index % columns;
  const row = Math.floor(index / columns);
  const step = columns <= 1 ? 0 : 56 / (columns - 1);
  const rowNudge = row % 2 === 0 ? -4 : 4;
  return 22 + column * step + rowNudge;
};

argumentGraphs.forEach((graph) => {
  const root = graph.closest(".argument-map");
  const data = JSON.parse(root.querySelector("[data-argument-map-data]").textContent);
  const positionedNodes = graph.querySelector("[data-positioned-argument-nodes]");
  const unpositionedNodes = graph.querySelector("[data-unpositioned-argument-nodes]");
  const axisById = new Map(data.axes.map((axis, index) => [axis.id, { ...axis, index }]));

  const actors = data.clusters.flatMap((cluster) => {
    const axis = axisById.get(cluster.axis) || { index: 0, label: cluster.axis };
    return cluster.actors.map((actor) => ({
      actor,
      axis,
      cluster,
    }));
  });
  const positionedActors = actors.filter(({ actor }) => hasPoliticalPosition(actor.party));
  const unpositionedActors = actors.filter(({ actor }) => !hasPoliticalPosition(actor.party));
  const positionedTotals = positionedActors.reduce((totals, item) => {
    totals[item.cluster.position] = (totals[item.cluster.position] || 0) + 1;
    return totals;
  }, {});
  const unpositionedTotals = unpositionedActors.reduce((totals, item) => {
    totals[item.cluster.position] = (totals[item.cluster.position] || 0) + 1;
    return totals;
  }, {});
  const positionedGraphIndexes = new Map(positionedActors.map((item, index) => [item, index]));
  const unpositionedGraphIndexes = new Map(unpositionedActors.map((item, index) => [item, index]));
  const positionedIndexes = {};
  const unpositionedIndexes = {};
  const showEmptyState = (target, label) => {
    const empty = document.createElement("p");
    empty.className = "argument-empty";
    empty.textContent = label;
    target.append(empty);
  };

  if (!actors.length) {
    showEmptyState(positionedNodes, "Aucune citation sélectionnée pour ce sujet.");
    showEmptyState(unpositionedNodes, "Aucune source sélectionnée pour ce sujet.");
    return;
  }

  if (!positionedActors.length) {
    showEmptyState(positionedNodes, "Aucune citation située pour ce sujet.");
  }

  if (!unpositionedActors.length) {
    showEmptyState(unpositionedNodes, "Aucune source non située pour ce sujet.");
  }

  actors.forEach((item) => {
    const { actor, axis, cluster } = item;
    const color = partyColor(actor.party);
    const isPositioned = hasPoliticalPosition(actor.party);
    const target = isPositioned ? positionedNodes : unpositionedNodes;
    const indexes = isPositioned ? positionedIndexes : unpositionedIndexes;
    const totals = isPositioned ? positionedTotals : unpositionedTotals;
    const graphIndex = isPositioned ? positionedGraphIndexes.get(item) : unpositionedGraphIndexes.get(item);
    const graphTotal = isPositioned ? positionedActors.length : unpositionedActors.length;
    const side = partySide(actor.party);
    const axisSpread = ((axis.index % 4) - 1.5) * 8;
    const positionIndex = indexes[cluster.position] || 0;
    indexes[cluster.position] = positionIndex + 1;
    const laneOffset = ((graphIndex % 3) - 1) * 7;
    const x = isPositioned
      ? clamp(50 + side * 30 + axisSpread + laneOffset, 12, 88)
      : clamp(distributedX(graphIndex, graphTotal) + axisSpread * .35, 16, 84);
    const y = isPositioned
      ? clamp(positionSlotY(cluster.position, positionIndex, totals[cluster.position]), 8, 94)
      : clamp(sourceSlotY(cluster.position, positionIndex, totals[cluster.position]), 12, 88);

    const source = sourceParts(actor.quote_source);
    const node = document.createElement("article");
    node.className = `argument-node argument-node-${cluster.position}${isPositioned ? "" : " argument-node-unpositioned"}`;
    node.tabIndex = 0;
    node.style.setProperty("--argument-x", `${x}%`);
    node.style.setProperty("--argument-y", `${y}%`);
    node.style.setProperty("--party-color", color);
    node.innerHTML = `
      <span class="argument-avatar">
        ${
          actor.photo
            ? `<img src="${escapeHtml(actor.photo)}" alt="Portrait de ${escapeHtml(actor.name)}">`
            : `<span>${escapeHtml(actor.initials || actor.name.slice(0, 2))}</span>`
        }
        <span class="argument-tooltip argument-author-tooltip">
          <strong>${escapeHtml(actor.name)}</strong>
          <span>${escapeHtml(actor.role)}</span>
          <span>${escapeHtml(actor.party)}</span>
        </span>
      </span>
      <span class="argument-quote">
        “${escapeHtml(actor.quote)}”
        <span class="argument-tooltip argument-source-tooltip">
          <strong>${escapeHtml(source.date)}</strong>
          <span>${escapeHtml(source.place)}</span>
          <a href="${sourceUrl(actor.quote_source, actor.quote_url)}">Voir la source</a>
        </span>
      </span>
    `;

    target.append(node);
  });
});
