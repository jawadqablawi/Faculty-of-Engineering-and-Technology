(() => {
  const root = document.querySelector("[data-calendar]");
  if (!root) return;
  const events = JSON.parse(document.getElementById("events").textContent);
  const grid = document.getElementById("calendar-grid");
  const agenda = document.getElementById("calendar-agenda");
  const empty = document.getElementById("calendar-empty");
  const title = document.getElementById("month-label");
  const club = document.getElementById("club-filter");
  const kind = document.getElementById("kind-filter");
  const mode = document.getElementById("mode");
  const dialog = document.getElementById("calendar-event-dialog");
  const conflict = dialog.querySelector("[data-calendar-conflict]");
  const clubs = [...new Set(events.map(event => event.club__name))].sort((a, b) => a.localeCompare(b, "ar"));
  const colors = new Map(clubs.map((name, index) => [name, index % 5]));
  const eventDays = new Map();
  const today = root.dataset.today;
  let date = new Date(today + "T12:00:00");
  let check;
  for (const name of clubs) club.add(new Option(name, name));
  for (const event of events) {
    if (!event.date) continue;
    if (!eventDays.has(event.date)) eventDays.set(event.date, []);
    eventDays.get(event.date).push(event);
  }
  for (const list of eventDays.values()) {
    list.sort((a, b) => (a.start ?? "").localeCompare(b.start ?? "") || a.title.localeCompare(b.title, "ar"));
  }

  const format = (day, options) => day.toLocaleDateString("ar-PS", options);
  const longDate = day => format(day, {weekday: "long", day: "numeric", month: "long", year: "numeric"});
  const shortDate = day => format(day, {day: "numeric", month: "short"});
  function dateKey(day) {
    return [day.getFullYear(), String(day.getMonth() + 1).padStart(2, "0"), String(day.getDate()).padStart(2, "0")].join("-");
  }

  function showEvent(event) {
    check?.abort();
    conflict.hidden = true;
    const day = new Date(event.date + "T12:00:00");
    dialog.querySelector("h2").textContent = event.title;
    dialog.querySelector("[data-event-club]").textContent = event.club__name;
    dialog.querySelector("[data-event-date]").textContent = longDate(day);
    dialog.querySelector("[data-event-time]").textContent =
      [event.start?.slice(0, 5), event.end?.slice(0, 5)].filter(Boolean).join(" – ") || "لم يحدد الوقت";
    dialog.querySelector("[data-event-kind]").textContent = event.kind === "event" ? "وجاهي" : "إلكتروني";
    dialog.showModal();
    if (event.kind !== "event") return;
    const request = new AbortController();
    check = request;
    const url = new URL(location.href);
    url.search = new URLSearchParams({event_conflict: event.uid}).toString();
    fetch(url, {signal: request.signal})
      .then(response => response.ok && !response.redirected ? response.json() : null)
      .then(result => {
        if (result?.conflict && !request.signal.aborted && dialog.open) conflict.hidden = false;
      })
      .catch(() => {});
  }
  dialog.addEventListener("close", () => check?.abort());

  function eventButton(event) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "calendar-event";
    button.dataset.clubColor = colors.get(event.club__name);
    button.textContent = event.title;
    const details = document.createElement("small");
    details.textContent = [event.club__name, event.start?.slice(0, 5)].filter(Boolean).join(" · ");
    button.append(details);
    button.addEventListener("click", () => showEvent(event));
    return button;
  }

  function render() {
    grid.replaceChildren();
    agenda.replaceChildren();
    const period = mode.value;
    grid.dataset.period = period;
    const day = new Date(date);
    if (period === "month") day.setDate(1);
    if (period !== "day") day.setDate(day.getDate() - day.getDay());
    const count = {month: 42, week: 7, day: 1}[period];
    const end = new Date(day);
    end.setDate(end.getDate() + count - 1);
    title.textContent = {
      month: () => format(date, {month: "long", year: "numeric"}),
      week: () => shortDate(day) + " – " + shortDate(end),
      day: () => longDate(day),
    }[period]();
    if (period !== "day") {
      const weekday = new Date(day);
      for (let i = 0; i < 7; i++) {
        const item = document.createElement("span");
        item.className = "calendar-weekday";
        item.textContent = format(weekday, {weekday: "short"});
        grid.append(item);
        weekday.setDate(weekday.getDate() + 1);
      }
    }
    let hasEvents = false;
    for (let index = 0; index < count; index++) {
      const key = dateKey(day);
      const outside = period === "month" && day.getMonth() !== date.getMonth();
      const cell = document.createElement("div");
      cell.className = "calendar-cell";
      cell.toggleAttribute("data-today", key === today);
      cell.toggleAttribute("data-outside", outside);
      const label = document.createElement("small");
      label.textContent = format(day, {day: "numeric"});
      cell.append(label);
      const matching = (eventDays.get(key) ?? []).filter(event =>
        (!club.value || club.value === event.club__name) && (!kind.value || kind.value === event.kind));
      for (const event of matching) {
        cell.append(eventButton(event));
        if (!outside) {
          const item = document.createElement("li");
          const heading = document.createElement("strong");
          heading.textContent = longDate(day);
          item.append(heading, eventButton(event));
          agenda.append(item);
          hasEvents = true;
        }
      }
      grid.append(cell);
      day.setDate(day.getDate() + 1);
    }
    empty.hidden = hasEvents;
  }

  function move(amount) {
    if (mode.value === "month") {
      date.setDate(1);
      date.setMonth(date.getMonth() + amount);
    } else date.setDate(date.getDate() + amount * (mode.value === "week" ? 7 : 1));
    render();
  }
  document.getElementById("back").onclick = () => move(-1);
  document.getElementById("forward").onclick = () => move(1);
  document.getElementById("today").onclick = () => { date = new Date(today + "T12:00:00"); render(); };
  for (const field of [mode, club, kind]) field.addEventListener("change", render);
  render();
})();
