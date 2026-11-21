(() => {
  const storageKey = "etcs-theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference;
  try {
    preference = localStorage.getItem(storageKey);
  } catch {
    // The toggle still works for the current page if storage is unavailable.
  }
  if (preference !== "dark" && preference !== "light") preference = null;

  function applyTheme() {
    const theme = preference ?? (system.matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    document.querySelector("[data-theme-toggle]")?.setAttribute("aria-pressed", String(theme === "dark"));
  }

  applyTheme();
  system.addEventListener("change", applyTheme);
  document.addEventListener("DOMContentLoaded", () => {
    const button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    applyTheme();
    button.hidden = false;
    button.addEventListener("click", () => {
      preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(storageKey, preference);
      } catch {
        // Keep the selected theme for this page.
      }
      applyTheme();
    });
  });
})();
