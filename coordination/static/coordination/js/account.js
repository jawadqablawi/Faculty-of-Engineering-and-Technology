for (const form of document.querySelectorAll("[data-account-form]")) {
  for (const toggle of form.querySelectorAll("[data-password-toggle]")) {
    const field = document.getElementById(toggle.getAttribute("aria-controls"));
    if (!field) continue;
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const show = field.type === "password";
      field.type = show ? "text" : "password";
      toggle.querySelector("span").textContent = show ? "إخفاء" : "إظهار";
      toggle.setAttribute("aria-pressed", String(show));
    });
  }

  const submit = form.querySelector("button[type='submit']");
  const spinner = submit.querySelector(".submit-spinner");
  const status = form.querySelector("[data-submit-status]");
  form.addEventListener("submit", event => {
    if (submit.disabled) {
      event.preventDefault();
      return;
    }
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    spinner.hidden = false;
    status.textContent = "جارٍ الإرسال…";
  });
  window.addEventListener("pageshow", () => {
    submit.disabled = false;
    submit.removeAttribute("aria-busy");
    spinner.hidden = true;
    status.textContent = "";
  });
}
