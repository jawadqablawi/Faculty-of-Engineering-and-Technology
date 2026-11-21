const workspaceNav = document.getElementById("workspace-nav");
const drawer = document.getElementById("workspace-drawer");
if (workspaceNav && drawer) {
  const layout = document.querySelector("[data-workspace-layout]");
  const sidebarSlot = layout.querySelector("[data-sidebar-slot]");
  const drawerSlot = drawer.querySelector("[data-drawer-slot]");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const mobileToggle = document.querySelector(".drawer-toggle");
  const mobile = matchMedia("(max-width: 800px)");
  let collapsed = false;
  try {
    collapsed = localStorage.getItem("etcs-sidebar-collapsed") === "true";
  } catch {
    // Use the expanded layout when storage is unavailable.
  }

  function updateCollapse() {
    layout.classList.toggle("sidebar-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "توسيع القائمة" : "طي القائمة";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
  }

  function placeNavigation() {
    if (mobile.matches) {
      drawerSlot.append(workspaceNav);
      sidebarSlot.hidden = true;
    } else {
      if (drawer.open) drawer.close();
      sidebarSlot.append(workspaceNav);
      sidebarSlot.hidden = false;
    }
  }

  toggle.addEventListener("click", () => {
    collapsed = !collapsed;
    updateCollapse();
    try {
      localStorage.setItem("etcs-sidebar-collapsed", String(collapsed));
    } catch {
      // Keep the layout selection for the current page.
    }
  });
  mobile.addEventListener("change", placeNavigation);
  updateCollapse();
  placeNavigation();
  toggle.hidden = false;
  mobileToggle.hidden = false;
}

const profileMenu = document.querySelector(".workspace-profile");
if (profileMenu) {
  document.addEventListener("click", event => {
    if (!profileMenu.contains(event.target)) profileMenu.open = false;
  });
  profileMenu.addEventListener("keydown", event => {
    if (event.key === "Escape" && profileMenu.open) {
      profileMenu.open = false;
      profileMenu.querySelector("summary").focus();
    }
  });
}
