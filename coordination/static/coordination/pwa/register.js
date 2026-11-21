if ("serviceWorker" in navigator && window.isSecureContext) {
  window.etcsWorker = navigator.serviceWorker.register("/sw.js", {scope: "/"})
    .catch(() => null);
}
