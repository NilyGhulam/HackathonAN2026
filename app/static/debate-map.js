const explorers = document.querySelectorAll("[data-debate-explorer]");

const textIncludes = (value, query) =>
  value.toLocaleLowerCase("fr-FR").includes(query.toLocaleLowerCase("fr-FR"));

const argumentCard = (argument) => {
  const card = document.createElement("article");
  card.className = "argument-card";

  const text = document.createElement("p");
  text.textContent = argument.text;

  const meta = document.createElement("span");
  meta.textContent = `${argument.carrier} · ${argument.source}`;

  card.append(text, meta);
  return card;
};

explorers.forEach((explorer) => {
  const dataNode = explorer.querySelector("[data-debate-data]");
  const categoryButtons = Array.from(explorer.querySelectorAll("[data-category-id]"));
  const categoryHelp = explorer.querySelector("[data-category-help]");
  const selectedCategoryTitle = explorer.querySelector("[data-selected-category-title]");
  const selectedCategorySummary = explorer.querySelector("[data-selected-category-summary]");
  const subtopicMap = explorer.querySelector("[data-subtopic-map]");
  const sheet = explorer.querySelector("[data-subject-sheet]");
  const template = document.querySelector("#subject-sheet-template");
  const searchInput = explorer.querySelector("[data-topic-search]");
  const searchButton = explorer.querySelector("[data-topic-search-button]");
  const searchResults = explorer.querySelector("[data-search-results]");
  const categories = JSON.parse(dataNode.textContent);

  const allSubjects = categories.flatMap((category) =>
    category.subthemes.flatMap((subtheme) =>
      subtheme.subjects.map((subject) => ({ category, subtheme, subject })),
    ),
  );

  const selectSubject = ({ category, subtheme, subject }) => {
    const fragment = template.content.cloneNode(true);
    fragment.querySelector("[data-subject-title]").textContent = subject.title;
    fragment.querySelector("[data-subject-status]").textContent = subject.status;
    fragment.querySelector("[data-subject-context]").textContent = subject.context;
    fragment.querySelector("[data-subject-summary]").textContent = subject.summary;

    const votes = subject.votes;
    const total = votes.for + votes.against + votes.neutral;
    const forEnd = (votes.for / total) * 100;
    const againstEnd = forEnd + (votes.against / total) * 100;
    const pie = fragment.querySelector("[data-vote-pie]");
    pie.style.background = `conic-gradient(#18753c 0 ${forEnd}%, #e1000f ${forEnd}% ${againstEnd}%, #929292 ${againstEnd}% 100%)`;
    fragment.querySelector("[data-vote-for]").textContent = `${votes.for}%`;
    fragment.querySelector("[data-vote-against]").textContent = `${votes.against}%`;
    fragment.querySelector("[data-vote-neutral]").textContent = `${votes.neutral}%`;

    const timeline = fragment.querySelector("[data-subject-timeline]");
    subject.timeline.forEach((event) => {
      const item = document.createElement("li");
      item.innerHTML = `
        <time>${event.date}</time>
        <strong>${event.type} · ${event.title}</strong>
        <p>${event.summary}</p>
        <a href="${event.url}">Voir le texte officiel</a>
      `;
      timeline.append(item);
    });

    ["favorable", "unfavorable", "neutral"].forEach((kind) => {
      const container = fragment.querySelector(`[data-arguments-${kind}]`);
      subject.arguments[kind].forEach((argument) => {
        container.append(argumentCard(argument));
      });
    });

    sheet.replaceChildren(fragment);
    sheet.dataset.category = category.id;
    sheet.dataset.subtheme = subtheme.id;
    if (window.innerWidth < 1080) {
      sheet.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const renderSubthemes = (category, shouldScroll = true) => {
    selectedCategoryTitle.textContent = category.label;
    selectedCategorySummary.textContent = category.summary;
    subtopicMap.replaceChildren();

    category.subthemes.forEach((subtheme) => {
      const group = document.createElement("section");
      group.className = "subtheme-card";

      const header = document.createElement("header");
      const title = document.createElement("h4");
      title.textContent = subtheme.label;
      const summary = document.createElement("p");
      summary.textContent = subtheme.summary;
      header.append(title, summary);

      const subjects = document.createElement("div");
      subjects.className = "subject-list";
      subtheme.subjects.forEach((subject) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "subject-button";
        button.innerHTML = `<strong>${subject.title}</strong><span>${subject.status}</span>`;
        button.addEventListener("click", () => selectSubject({ category, subtheme, subject }));
        subjects.append(button);
      });

      group.append(header, subjects);
      subtopicMap.append(group);
    });

    if (shouldScroll && window.innerWidth < 1080) {
      document.querySelector("#niveau-2").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const selectCategory = (categoryId, shouldScroll = true) => {
    const category = categories.find((item) => item.id === categoryId);
    if (!category) return;

    categoryButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.categoryId === categoryId);
    });
    renderSubthemes(category, shouldScroll);
  };

  const runSearch = () => {
    const query = searchInput.value.trim();
    searchResults.replaceChildren();
    if (query.length < 2) {
      searchResults.textContent = "Saisissez au moins deux caractères.";
      return;
    }

    const matches = allSubjects.filter(({ category, subtheme, subject }) =>
      [category.label, subtheme.label, subject.title, subject.summary, subject.context].some((value) =>
        textIncludes(value, query),
      ),
    );

    if (matches.length === 0) {
      searchResults.textContent = "Aucun sujet correspondant dans la démonstration.";
      return;
    }

    matches.forEach((match) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "search-result";
      button.innerHTML = `<strong>${match.subject.title}</strong><span>${match.category.label} · ${match.subtheme.label}</span>`;
      button.addEventListener("click", () => {
        selectCategory(match.category.id, false);
        selectSubject(match);
      });
      searchResults.append(button);
    });
  };

  categoryButtons.forEach((button) => {
    button.addEventListener("mouseenter", () => {
      categoryHelp.textContent = button.dataset.categorySummary;
    });
    button.addEventListener("focus", () => {
      categoryHelp.textContent = button.dataset.categorySummary;
    });
    button.addEventListener("click", () => selectCategory(button.dataset.categoryId));
  });

  searchButton.addEventListener("click", runSearch);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });

  if (categories.length > 0) {
    selectCategory(categories[0].id, false);
  }
});
