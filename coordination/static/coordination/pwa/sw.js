self.addEventListener("install", event => event.waitUntil(self.skipWaiting()));

self.addEventListener("push", event => {
  let data;
  try { data = event.data.json(); } catch { return; }
  event.waitUntil(Promise.all([
    self.registration.showNotification(data.title || "ETCS", {
      body: data.body || "لديك تحديث في نظام التنسيق.",
      tag: data.tag,
      icon: "/static/coordination/pwa/icon-192.png",
      data: {url: data.url},
    }),
    self.clients.matchAll({type: "window", includeUncontrolled: true}).then(windows => {
      for (const client of windows) {
        client.postMessage({type: "etcs-request-changed", url: data.url, recipient: data.recipient});
      }
    }),
  ]));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  let url = new URL("/notifications/", self.location.origin);
  try {
    const target = new URL(event.notification.data.url, self.location.origin);
    if (target.origin === self.location.origin &&
        /^\/(?:requests\/[0-9a-f-]+\/|notifications\/)$/i.test(target.pathname)) url = target;
  } catch {}
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    for (const client of windows) {
      if (client.url === url.href) return client.focus();
    }
    const client = windows.find(item => new URL(item.url).origin === url.origin);
    if (client?.navigate) {
      const navigated = await client.navigate(url.href).catch(() => null);
      if (navigated) return navigated.focus();
    }
    return self.clients.openWindow(url.href);
  })());
});
