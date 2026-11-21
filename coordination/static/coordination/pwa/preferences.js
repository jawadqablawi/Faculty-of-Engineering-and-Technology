(async () => {
  const panel = document.querySelector("[data-push-settings]");
  const status = panel.querySelector("[data-push-status]");
  const enable = panel.querySelector("[data-push-enable]");
  const disable = panel.querySelector("[data-push-disable]");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (ios && !standalone) {
    panel.querySelector("[data-ios-hint]").hidden = false;
    status.textContent = "ثبّت التطبيق أولًا لتفعيل الإشعارات.";
    return;
  }
  if (!window.etcsWorker || !("PushManager" in window) || !("Notification" in window)) {
    status.textContent = "المتصفح لا يدعم إشعارات الجوال هنا.";
    return;
  }
  if (Notification.permission === "denied") {
    status.textContent = "الإشعارات محظورة من المتصفح. غيّر الإذن من إعدادات الجهاز.";
    return;
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": panel.querySelector("[name=csrfmiddlewaretoken]").value},
      body: JSON.stringify(body),
    });
    if (!response.ok || response.redirected) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || "unavailable");
    }
  }

  try {
    const response = await fetch(panel.dataset.key);
    const config = await response.json();
    if (!config.public_key) {
      status.textContent = "إشعارات الجوال غير مهيّأة على الخادم.";
      return;
    }
    const key = config.public_key.replace(/-/g, "+").replace(/_/g, "/");
    const applicationServerKey = Uint8Array.from(atob(key.padEnd(Math.ceil(key.length / 4) * 4, "=")), char => char.charCodeAt(0));
    const registered = await window.etcsWorker;
    if (!registered) throw new Error();
    const worker = await navigator.serviceWorker.ready;
    let subscription = await worker.pushManager.getSubscription();

    function update(active) {
      status.textContent = active ? "إشعارات الجوال مفعّلة لهذا الحساب على هذا الجهاز." : "إشعارات الجوال غير مفعّلة لهذا الحساب على هذا الجهاز.";
      enable.hidden = active;
      enable.disabled = false;
      disable.hidden = !active;
    }
    // The server checks ownership before declaring this browser active for the current account.
    const active = subscription && config.endpoints?.includes(subscription.endpoint);
    update(Boolean(active));

    enable.addEventListener("click", async () => {
      enable.disabled = true;
      try {
        if (await Notification.requestPermission() !== "granted") {
          status.textContent = Notification.permission === "denied"
            ? "الإشعارات محظورة من المتصفح." : "لم يتم السماح بالإشعارات.";
          return;
        }
        subscription ??= await worker.pushManager.subscribe({userVisibleOnly: true, applicationServerKey});
        await post(panel.dataset.subscribe, subscription.toJSON());
        update(true);
      } catch (error) {
        status.textContent = error.message === "device_limit"
          ? "وصلت للحد الأقصى للأجهزة. أزل جهازًا ثم حاول مرة أخرى."
          : "تعذّر تفعيل الإشعارات. حاول مرة أخرى.";
      } finally {
        enable.disabled = false;
      }
    });

    disable.addEventListener("click", async () => {
      disable.disabled = true;
      try {
        await post(panel.dataset.unsubscribe, {endpoint: subscription.endpoint});
        // The browser subscription can still serve another signed-in account.
        update(false);
      } catch {
        status.textContent = "تعذّر إيقاف الإشعارات. حدّث الصفحة وتحقق من حالة الجهاز.";
      } finally {
        disable.disabled = false;
      }
    });
  } catch {
    status.textContent = "تعذّر تجهيز إشعارات الجوال.";
  }
})();
