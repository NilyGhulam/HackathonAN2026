const timelines = document.querySelectorAll("[data-timeline-paginated]");

timelines.forEach((timeline) => {
  const pageSize = 10;
  const items = Array.from(timeline.querySelectorAll("[data-timeline-item]"));
  const newer = timeline.querySelector("[data-timeline-newer]");
  const older = timeline.querySelector("[data-timeline-older]");
  const status = timeline.querySelector("[data-timeline-page-status]");
  if (!newer || !older || !status) {
    return;
  }
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
