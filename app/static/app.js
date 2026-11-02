// Drag and drop tasks between days and the to-do list.
// The server does the actual move (POST /tasks/{id}/move) and answers with
// out-of-band swaps, so this file only wires browser drag events to htmx.
(() => {
  const zoneOf = (el) => el instanceof Element ? el.closest("[data-drop-day]") : null;

  document.addEventListener("dragstart", (e) => {
    const li = e.target instanceof Element ? e.target.closest(".task[draggable]") : null;
    if (!li) return;
    e.dataTransfer.setData("text/plain", li.id.replace("task-", ""));
    e.dataTransfer.effectAllowed = "move";
    li.classList.add("dragging");
  });

  document.addEventListener("dragend", (e) => {
    if (e.target instanceof Element) e.target.classList.remove("dragging");
    document.querySelectorAll(".drop-over").forEach((z) => z.classList.remove("drop-over"));
  });

  document.addEventListener("dragover", (e) => {
    const zone = zoneOf(e.target);
    if (!zone) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    zone.classList.add("drop-over");
  });

  document.addEventListener("dragleave", (e) => {
    const zone = zoneOf(e.target);
    if (zone && !zone.contains(e.relatedTarget)) zone.classList.remove("drop-over");
  });

  document.addEventListener("drop", (e) => {
    const zone = zoneOf(e.target);
    if (!zone) return;
    e.preventDefault();
    zone.classList.remove("drop-over");

    const id = e.dataTransfer.getData("text/plain");
    const row = document.getElementById(`task-${id}`);
    if (!id || !row || zoneOf(row) === zone) return; // dropped where it already is

    htmx.ajax("POST", `/tasks/${id}/move`, {
      target: `#task-${id}`,
      swap: "outerHTML",
      values: { day: zone.dataset.dropDay },
    });
  });
})();

// Tooltips for chart marks: any element with data-tip, on hover and keyboard focus.
// Text goes in with textContent (labels are user data).
(() => {
  const tip = () => document.getElementById("tip");
  const show = (el, x, y) => {
    const t = tip();
    if (!t) return;
    t.textContent = el.dataset.tip;
    t.hidden = false;
    const w = t.offsetWidth;
    t.style.left = `${Math.min(Math.max(8, x - w / 2), window.innerWidth - w - 8)}px`;
    t.style.top = `${y - t.offsetHeight - 10}px`;
  };
  const hide = () => { const t = tip(); if (t) t.hidden = true; };
  document.addEventListener("pointermove", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-tip]") : null;
    el ? show(el, e.clientX, e.clientY) : hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-tip]") : null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    show(el, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("scroll", hide, true);
})();
