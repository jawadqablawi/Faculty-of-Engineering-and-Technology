(() => {
  const tracking = document.querySelector("[data-live-request]");
  if (!tracking) return;

  const warning = tracking.querySelector("[data-live-warning]");
  const main = tracking.closest("main");
  const touched = new Set();
  let checking = false;
  let submitting = false;

  function remember(event) {
    const form = event.target.form;
    if (form?.method.toLowerCase() === "post" && !form.matches("[data-notification-form]")) {
      touched.add(form);
    }
  }
  main.addEventListener("input", remember);
  main.addEventListener("change", remember);
  document.addEventListener("submit", event => {
    // Confirmation dialogs prevent the original submit and replay it after approval.
    if (event.defaultPrevented || event.target.method.toLowerCase() !== "post" ||
        event.target.matches("[data-notification-form]")) return;
    submitting = true;
  });
  window.addEventListener("pageshow", () => { submitting = false; });
  tracking.querySelector("[data-live-reload]").addEventListener("click", () => location.reload());

  async function check() {
    if (document.hidden || checking || submitting || !warning.hidden) return;
    checking = true;
    try {
      const url = new URL(location.pathname, location.origin);
      url.searchParams.set("live", "1");
      const response = await fetch(url, {cache: "no-store"});
      if (!response.ok || response.redirected) return;
      const result = await response.json();
      if (!result.revision || result.revision === tracking.dataset.revision ||
          submitting || document.hidden) return;
      if (touched.size) warning.hidden = false;
      else location.reload();
    } catch {
      // The next visible poll can recover from temporary connection loss.
    } finally {
      checking = false;
    }
  }

  navigator.serviceWorker?.addEventListener("message", event => {
    const data = event.data;
    if (data?.type === "etcs-request-changed" && data.url === location.pathname &&
        String(data.recipient) === tracking.dataset.recipient) check();
  });
  document.addEventListener("visibilitychange", check);
  // Covers delayed pushes and requests open on devices without a push subscription.
  window.setInterval(check, 25000);
})();
