(() => {
  const menu = document.querySelector("[data-notification-menu]");
  const preview = menu?.querySelector("[data-notification-preview]");
  const search = document.getElementById("workspace-search");
  const shortcut = document.querySelector("[data-search-shortcut]");
  if (shortcut) {
    try { shortcut.checked = localStorage.getItem("etcs-search-shortcut") !== "off"; } catch {}
    function syncShortcut() {
      if (shortcut.checked) search.setAttribute("aria-keyshortcuts", "/");
      else search.removeAttribute("aria-keyshortcuts");
    }
    shortcut.addEventListener("change", () => {
      syncShortcut();
      try { localStorage.setItem("etcs-search-shortcut", shortcut.checked ? "on" : "off"); } catch {}
    });
    syncShortcut();
    shortcut.closest("label").hidden = false;
  }
  const confirmation = document.getElementById("action-confirmation");

  function toast(message, type) {
    const notice = document.createElement("div");
    notice.className = `toast ${type}`;
    const text = document.createElement("div");
    text.setAttribute("role", type === "error" ? "alert" : "status");
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "secondary toast__dismiss";
    dismiss.dataset.toastDismiss = "";
    dismiss.setAttribute("aria-label", "إغلاق التنبيه");
    dismiss.textContent = "×";
    notice.append(text, dismiss);
    document.querySelector("[data-toast-region]").prepend(notice);
    text.textContent = message;
  }

  async function loadPreview() {
    preview.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(preview.dataset.url, {cache: "no-store"});
      if (!response.ok || response.redirected) throw new Error();
      const fragment = new DOMParser().parseFromString(await response.text(), "text/html");
      preview.replaceChildren(...fragment.body.childNodes);
    } catch {
      preview.textContent = "تعذّر تحميل القائمة. افتح صفحة الإشعارات لعرضها.";
    } finally {
      preview.removeAttribute("aria-busy");
    }
  }
  menu?.addEventListener("toggle", () => {
    if (menu.open && !preview.hasAttribute("aria-busy")) loadPreview();
  });
  document.addEventListener("click", event => {
    if (menu?.open && !menu.contains(event.target)) menu.open = false;
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && menu?.open && menu.contains(event.target)) {
      menu.open = false;
      menu.querySelector("summary").focus();
      return;
    }
    if (event.defaultPrevented || event.key !== "/" || event.isComposing || event.repeat ||
        event.ctrlKey || event.altKey || event.metaKey || event.shiftKey ||
        event.target.isContentEditable || event.target.closest("input, textarea, select, [role='textbox']") ||
        document.querySelector("dialog[open]") || !search || !shortcut?.checked) return;
    event.preventDefault();
    search.focus();
    search.select();
  });

  function updateUnread(count, id) {
    const badge = menu?.querySelector("[data-unread-count]");
    if (badge) {
      badge.textContent = count;
      badge.hidden = count === 0;
      menu.querySelector("summary").setAttribute("aria-label", `الإشعارات، ${count} غير مقروء`);
    }
    for (const row of document.querySelectorAll("[data-notification-id][data-unread]")) {
      if (id && row.dataset.notificationId !== id) continue;
      const ownedFocus = row.contains(document.activeElement);
      delete row.dataset.unread;
      row.querySelector("[data-unread-label]")?.remove();
      row.querySelector("[data-mark-one]")?.remove();
      if (ownedFocus) {
        row.tabIndex = -1;
        row.focus();
      }
    }
  }

  let marking = false;
  document.addEventListener("submit", async event => {
    const form = event.target;
    if (!form.matches("[data-notification-form]")) return;
    event.preventDefault();
    if (marking) return;
    marking = true;
    const data = new FormData(form);
    const button = form.querySelector("button");
    button.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: data,
        headers: {Accept: "application/json"},
      });
      if (!response.ok || response.redirected) throw new Error();
      updateUnread((await response.json()).unread, data.get("notification"));
      toast("تم تحديث حالة الإشعارات.", "success");
    } catch {
      toast("تعذّر تحديث الإشعارات. حاول مرة أخرى.", "error");
    } finally {
      marking = false;
      button.removeAttribute("aria-busy");
    }
  });

  if (!confirmation?.showModal) return;
  let pending;
  let replaying;
  document.addEventListener("submit", event => {
    if (event.defaultPrevented || replaying === event.target) return;
    const message = event.submitter?.dataset.confirm ?? event.target.dataset.confirm;
    if (!message) return;
    event.preventDefault();
    if (confirmation.open) return;
    pending = {form: event.target, button: event.submitter};
    confirmation.querySelector("#confirm-message").textContent = message;
    confirmation.returnValue = "cancel";
    confirmation.showModal();
  });
  confirmation.addEventListener("close", () => {
    const action = pending;
    pending = null;
    if (!action || confirmation.returnValue !== "confirm") return;
    replaying = action.form;
    try { action.form.requestSubmit(action.button ?? undefined); }
    finally { replaying = null; }
  });
})();
