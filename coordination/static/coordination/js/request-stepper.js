(() => {
  const form = document.querySelector("[data-request-stepper]");
  if (!form) return;
  const panels = [...form.querySelectorAll("[data-step-panel]")];
  const markers = [...document.querySelectorAll("[data-step-marker]")];
  const next = form.querySelector("[data-step-next]");
  const back = form.querySelector("[data-step-back]");
  const submit = form.querySelector("[data-step-submit]");
  const status = form.querySelector("[data-request-save-status]");
  const date = form.querySelector("#id_date");
  const weekday = form.querySelector("#weekday");
  const needs = form.querySelector("#needs");
  const total = form.querySelector("#id_needs-TOTAL_FORMS");
  const add = form.querySelector("#add-need");
  const template = form.querySelector("#new-need");
  const touched = new WeakSet();
  let step = panels.findIndex(panel => panel.querySelector(".errorlist"));
  if (step < 0) step = 0;
  let saving = false;

  function show(index, focus = true) {
    step = index;
    panels.forEach((panel, i) => { panel.hidden = i !== step; });
    markers.forEach((marker, i) => {
      if (i === step) marker.setAttribute("aria-current", "step");
      else marker.removeAttribute("aria-current");
      marker.classList.toggle("step-completed", i < step);
    });
    back.hidden = step === 0;
    next.hidden = step === panels.length - 1;
    submit.hidden = !next.hidden;
    if (focus) panels[step].querySelector("h2").focus();
  }

  function updateDate() {
    weekday.value = date.value
      ? new Date(date.value + "T12:00:00").toLocaleDateString("ar-PS", {weekday: "long"})
      : "يُحدد من التاريخ";
  }

  function invalidMessage(field) {
    if (field.required && !field.value.trim()) return "هذا الحقل مطلوب.";
    if (field === date && field.value && field.value < form.dataset.today) return "اختر تاريخًا من اليوم فما بعد.";
    const row = field.closest(".needs-row");
    if (row) {
      const item = row.querySelector("[name$='-item']");
      const quantity = row.querySelector("[name$='-quantity']");
      if (field === item && quantity.value && !item.value.trim()) return "اكتب اسم الصنف.";
      if (field === quantity && item.value.trim() && !quantity.value) return "أدخل العدد.";
    }
    if (field.validity.rangeUnderflow || field.validity.rangeOverflow || field.validity.stepMismatch || field.validity.badInput) {
      return "أدخل عددًا صحيحًا ضمن النطاق المسموح.";
    }
    if (!field.validity.valid) return field.validationMessage;
    return "";
  }

  function validate(field) {
    const message = invalidMessage(field);
    const id = field.id + "-live-error";
    let error = document.getElementById(id);
    if (!error) {
      error = document.createElement("p");
      error.id = id;
      error.className = "request-field-error";
      error.setAttribute("aria-live", "polite");
      field.after(error);
      const describedBy = field.getAttribute("aria-describedby");
      field.setAttribute("aria-describedby", [describedBy, id].filter(Boolean).join(" "));
    }
    error.textContent = message;
    if (message) field.setAttribute("aria-invalid", "true");
    else field.removeAttribute("aria-invalid");
    return !message;
  }

  function validatePanel(panel) {
    let invalid;
    for (const field of panel.querySelectorAll("input:not([type='hidden']):not([type='checkbox']), textarea")) {
      if (field.closest(".needs-row[hidden]")) continue;
      touched.add(field);
      if (!validate(field) && !invalid) invalid = field;
    }
    return invalid;
  }

  form.noValidate = true;
  form.addEventListener("focusout", event => {
    if (!event.target.matches("input:not([type='hidden']):not([type='checkbox']), textarea")) return;
    touched.add(event.target);
    validate(event.target);
  });
  form.addEventListener("input", event => {
    if (touched.has(event.target)) validate(event.target);
    const row = event.target.closest(".needs-row");
    if (row) for (const field of row.querySelectorAll("input")) {
      if (field !== event.target && touched.has(field)) validate(field);
    }
    if (event.target === date) updateDate();
  });

  add.hidden = false;
  add.disabled = Number(total.value) >= 100;
  add.addEventListener("click", () => {
    if (Number(total.value) >= 100) return;
    needs.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", total.value));
    total.value = Number(total.value) + 1;
    add.disabled = Number(total.value) >= 100;
    needs.lastElementChild.querySelector("input").focus();
    updateSaveStatus();
  });

  needs.addEventListener("click", event => {
    if (!event.target.matches(".remove-need")) return;
    const row = event.target.closest(".needs-row");
    row.querySelector("[name$='-DELETE']").checked = true;
    row.hidden = true;
    (add.disabled ? back : add).focus();
    updateSaveStatus();
  });
  for (const checkbox of needs.querySelectorAll("[name$='-DELETE']:checked")) checkbox.closest(".needs-row").hidden = true;

  next.addEventListener("click", () => {
    const invalid = validatePanel(panels[step]);
    if (invalid) invalid.focus();
    else show(step + 1);
  });
  back.addEventListener("click", () => show(step - 1));

  function snapshot() { return new URLSearchParams(new FormData(form)).toString(); }
  const initial = snapshot();
  function warnBeforeLeaving(event) {
    if (saving) return;
    event.preventDefault();
    event.returnValue = "";
  }
  function updateSaveStatus() {
    const dirty = snapshot() !== initial;
    status.textContent = dirty ? "هناك تغييرات غير محفوظة." : "الحفظ يتم عند الضغط على زر الحفظ.";
    if (dirty) window.addEventListener("beforeunload", warnBeforeLeaving);
    else window.removeEventListener("beforeunload", warnBeforeLeaving);
  }
  form.addEventListener("input", updateSaveStatus);
  form.addEventListener("change", updateSaveStatus);
  form.addEventListener("submit", event => {
    if (step < panels.length - 1) {
      event.preventDefault();
      next.click();
      return;
    }
    for (const [index, panel] of panels.entries()) {
      const invalid = validatePanel(panel);
      if (!invalid) continue;
      event.preventDefault();
      show(index, false);
      invalid.focus();
      return;
    }
    saving = true;
    status.textContent = "جارٍ حفظ الطلب…";
  });
  window.addEventListener("pageshow", () => { saving = false; updateSaveStatus(); });
  updateDate();
  show(step, false);
})();
