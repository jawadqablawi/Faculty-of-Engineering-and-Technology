document.addEventListener("click", event => {
  const trigger = event.target.closest("[data-dialog-open]");
  if (trigger) {
    const dialog = document.getElementById(trigger.dataset.dialogOpen);
    if (dialog instanceof HTMLDialogElement && !dialog.open) dialog.showModal();
  }

  const dismiss = event.target.closest("[data-toast-dismiss]");
  if (dismiss) {
    const toast = dismiss.closest(".toast");
    if (!toast) return;
    const next = toast.nextElementSibling?.querySelector("[data-toast-dismiss]");
    toast.remove();
    (next ?? document.querySelector("main"))?.focus({ preventScroll: true });
  }
});

for (const button of document.querySelectorAll("[data-toast-dismiss]")) {
  button.hidden = false;
}

for (const tablist of document.querySelectorAll("[data-tabs][role='tablist']")) {
  const tabs = [...tablist.querySelectorAll("[role='tab'][aria-controls]")]
    .filter(tab => tab.closest("[role='tablist']") === tablist && !tab.disabled);
  if (!tabs.length) continue;

  function selectTab(selected) {
    for (const tab of tabs) {
      const active = tab === selected;
      tab.tabIndex = active ? 0 : -1;
      tab.setAttribute("aria-selected", String(active));
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !active;
    }
  }

  selectTab(tabs.find(tab => tab.getAttribute("aria-selected") === "true") ?? tabs[0]);
  tablist.addEventListener("click", event => {
    const tab = event.target.closest("[role='tab']");
    if (tabs.includes(tab)) selectTab(tab);
  });
  tablist.addEventListener("keydown", event => {
    const index = tabs.indexOf(event.target);
    if (index < 0) return;
    const rtl = getComputedStyle(tablist).direction === "rtl";
    const destinations = {
      Home: 0,
      End: tabs.length - 1,
      ArrowLeft: (index + (rtl ? 1 : -1) + tabs.length) % tabs.length,
      ArrowRight: (index + (rtl ? -1 : 1) + tabs.length) % tabs.length,
    };
    if (!Object.hasOwn(destinations, event.key)) return;
    event.preventDefault();
    const selected = tabs[destinations[event.key]];
    selectTab(selected);
    selected.focus();
  });
}
