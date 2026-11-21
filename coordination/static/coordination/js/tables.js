(() => {
  const collator = new Intl.Collator("ar", {numeric: true, sensitivity: "base"});
  const number = new Intl.NumberFormat("ar-PS");
  const pageSize = 15;

  function headersFor(table) {
    return [...(table.rows[0]?.cells ?? [])];
  }

  function labelRows(table) {
    const headers = headersFor(table);
    if (!headers.length || !headers.every(cell => cell.tagName === "TH")) return;
    if (!table.tHead) table.createTHead().append(table.rows[0]);
    table.classList.add("responsive-table");
    table.setAttribute("role", "table");
    for (const group of [...table.tBodies, table.tHead].filter(Boolean)) group.setAttribute("role", "rowgroup");
    const labels = headers.map(cell => cell.querySelector("a")?.childNodes[0].textContent.trim() ?? cell.textContent.trim());
    for (const row of table.rows) {
      row.setAttribute("role", "row");
      for (const [index, cell] of [...row.cells].entries()) {
        cell.setAttribute("role", cell.tagName === "TH" ? "columnheader" : "cell");
        if (cell.tagName === "TD" && row.cells.length === headers.length && labels[index]) {
          cell.dataset.label = labels[index];
          const label = text("span", labels[index], "mobile-cell-label");
          label.setAttribute("aria-hidden", "true");
          cell.prepend(label);
        }
      }
    }
  }

  function text(tag, content, className) {
    const element = document.createElement(tag);
    element.textContent = content;
    if (className) element.className = className;
    return element;
  }

  function selectField(label, first, options) {
    const field = text("label", label);
    const select = document.createElement("select");
    select.add(new Option(first, ""));
    for (const [value, caption] of options) select.add(new Option(caption, value));
    field.append(select);
    return [field, select];
  }

  function localGrid(table) {
    const headers = headersFor(table);
    if (!headers.length || !headers.every(cell => cell.tagName === "TH")) return;
    const rows = [...table.rows].slice(1).filter(row =>
      !row.hasAttribute("data-empty-row") && row.cells.length === headers.length &&
      [...row.cells].every(cell => cell.tagName === "TD"));
    const labels = headers.map(cell => cell.textContent.trim());
    const values = rows.map(row => [...row.cells].map(cell => cell.textContent.trim()));
    const sortable = labels.flatMap((label, index) =>
      label && !rows.every(row => row.cells[index].querySelector("a, button, form")) ? [[String(index), label]] : []);
    labelRows(table);
    if (!rows.length) return;

    const tools = document.createElement("div");
    tools.className = "grid-filters local-grid-filters";
    const searchLabel = text("label", "بحث في الجدول");
    const search = document.createElement("input");
    search.type = "search";
    searchLabel.append(search);
    const [sortLabel, sort] = selectField("الفرز حسب", "الترتيب الافتراضي", sortable);
    const [directionLabel, direction] = selectField("اتجاه الفرز", "تصاعدي", [["desc", "تنازلي"]]);
    const [filterLabel, filter] = selectField("تصفية حسب", "كل الأعمدة", sortable);
    const [valueLabel, value] = selectField("قيمة الفلتر", "كل القيم", []);
    valueLabel.hidden = true;
    tools.append(searchLabel, filterLabel, valueLabel, sortLabel, directionLabel);

    const controls = document.createElement("div");
    controls.className = "table-pager";
    const previous = text("button", "السابق", "secondary");
    const next = text("button", "التالي", "secondary");
    previous.type = next.type = "button";
    const pageLabel = text("span", "");
    pageLabel.setAttribute("role", "status");
    controls.append(previous, pageLabel, next);
    const empty = text("p", "لا توجد نتائج. جرّب تغيير البحث أو الفلتر.", "empty");
    empty.setAttribute("role", "status");

    const wrapper = table.closest(".table-wrap") ?? table;
    wrapper.before(tools);
    wrapper.after(empty, controls);
    let page = 0;
    function update() {
      const query = search.value.trim().toLocaleLowerCase("ar");
      const matched = rows.map((row, index) => ({row, index})).filter(({index}) =>
        (!query || values[index].some(cell => cell.toLocaleLowerCase("ar").includes(query))) &&
        (!value.value || values[index][Number(filter.value)] === value.value));
      const column = Number(sort.value);
      if (sort.value !== "") {
        matched.sort((a, b) => {
          const key = ({row, index}) => row.cells[column].dataset.sort ?? values[index][column];
          return collator.compare(key(a), key(b)) * (direction.value === "desc" ? -1 : 1);
        });
      }
      const pages = Math.ceil(matched.length / pageSize);
      page = Math.max(0, Math.min(page, pages - 1));
      for (const row of rows) {
        row.hidden = true;
        row.removeAttribute("data-print-match");
      }
      for (const {row} of matched) row.dataset.printMatch = "";
      for (const {row} of matched.slice(page * pageSize, (page + 1) * pageSize)) {
        row.parentElement.append(row);
        row.hidden = false;
      }
      empty.hidden = matched.length !== 0;
      controls.hidden = pages <= 1;
      previous.disabled = page === 0;
      next.disabled = page >= pages - 1;
      pageLabel.textContent = `الصفحة ${number.format(page + 1)} من ${number.format(pages)}`;
      for (const header of headers) header.removeAttribute("aria-sort");
      if (sort.value !== "") headers[column].setAttribute("aria-sort", direction.value === "desc" ? "descending" : "ascending");
    }
    function resetPage() { page = 0; update(); }
    for (const [index, label] of sortable) {
      const header = headers[Number(index)];
      const button = text("button", label, "grid-sort-button");
      button.type = "button";
      header.replaceChildren(button);
      button.addEventListener("click", () => {
        direction.value = sort.value === index && direction.value !== "desc" ? "desc" : "";
        sort.value = index;
        resetPage();
      });
    }
    filter.addEventListener("change", () => {
      value.replaceChildren(new Option("كل القيم", ""));
      valueLabel.hidden = filter.value === "";
      if (filter.value !== "") {
        const options = [...new Set(values.map(row => row[Number(filter.value)]).filter(Boolean))].sort(collator.compare);
        for (const option of options) value.add(new Option(option, option));
      }
      resetPage();
    });
    search.addEventListener("input", resetPage);
    for (const field of [sort, direction, value]) field.addEventListener("change", resetPage);
    previous.addEventListener("click", () => { page--; update(); });
    next.addEventListener("click", () => { page++; update(); });
    update();
  }

  function serverGrid(grid) {
    let form = grid.querySelector("[data-grid-form]");
    let results = grid.querySelector("[data-grid-results]");
    const status = text("p", "", "visually-hidden");
    status.setAttribute("role", "status");
    const skeleton = document.createElement("div");
    skeleton.className = "card table-skeleton";
    skeleton.hidden = true;
    skeleton.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 5; i++) skeleton.append(document.createElement("span"));
    grid.append(skeleton, status);
    labelRows(results.querySelector("table"));

    let controller;
    let debounce;
    async function load(url, {focusResults = false, keepForm = false} = {}) {
      clearTimeout(debounce);
      controller?.abort();
      const current = new AbortController();
      controller = current;
      skeleton.hidden = false;
      results.hidden = true;
      grid.setAttribute("aria-busy", "true");
      try {
        const response = await fetch(url, {signal: current.signal});
        if (!response.ok || response.redirected) throw new Error("Grid response unavailable");
        const documentFragment = new DOMParser().parseFromString(await response.text(), "text/html");
        const updated = documentFragment.querySelector("[data-grid-results]");
        const newForm = documentFragment.querySelector("[data-grid-form]");
        if (!updated || !newForm) throw new Error("Grid markup unavailable");
        if (current.signal.aborted) return;
        results.replaceWith(updated);
        results = updated;
        if (!keepForm) {
          form.replaceWith(newForm);
          form = newForm;
        }
        labelRows(results.querySelector("table"));
        history.replaceState(null, "", url);
        if (focusResults) {
          results.tabIndex = -1;
          results.focus();
        }
        status.textContent = "تم تحديث النتائج.";
      } catch (error) {
        if (error.name !== "AbortError") {
          results.hidden = false;
          status.textContent = "لم تُحمّل النتائج الجديدة.";
          const retry = grid.querySelector("[data-grid-retry]");
          if (retry) retry.remove();
          const notice = text("p", "تعذر تحديث النتائج. ", "message error");
          notice.dataset.gridRetry = "";
          const link = text("a", "إعادة المحاولة");
          link.href = url;
          notice.append(link);
          results.before(notice);
        }
      } finally {
        if (current === controller) {
          grid.removeAttribute("aria-busy");
          skeleton.hidden = true;
        }
      }
    }

    function formUrl() {
      const url = new URL(form.action);
      url.search = new URLSearchParams(new FormData(form)).toString();
      return url;
    }

    function loadFilters() {
      grid.querySelector("[data-grid-retry]")?.remove();
      load(formUrl(), {keepForm: true});
    }

    grid.addEventListener("submit", event => {
      if (event.target !== form) return;
      event.preventDefault();
      loadFilters();
    });
    grid.addEventListener("input", event => {
      if (event.target !== form.elements.q) return;
      controller?.abort();
      clearTimeout(debounce);
      debounce = setTimeout(loadFilters, 260);
    });
    grid.addEventListener("change", event => {
      if (form.contains(event.target) && event.target.matches("select")) loadFilters();
    });
    results.parentElement.addEventListener("click", event => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      const link = event.target.closest("[data-grid-results] th a, .table-pager a");
      if (!link) return;
      event.preventDefault();
      grid.querySelector("[data-grid-retry]")?.remove();
      load(link.href, {focusResults: true});
    });
  }

  for (const grid of document.querySelectorAll("[data-server-grid]")) serverGrid(grid);
  for (const table of document.querySelectorAll("main table")) {
    if (!table.closest("[data-server-grid]")) localGrid(table);
  }
})();
