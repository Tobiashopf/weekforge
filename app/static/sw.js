// Weekforge service worker: shows push notifications and opens the app when one is clicked.
// (Offline caching comes later, see ROADMAP.md.)

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Weekforge", {
      body: data.body || "",
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/badge-72.png",
      tag: data.tag || undefined,
      // Only same-origin paths: a notification never sends you to another site.
      data: { url: typeof data.url === "string" && data.url.startsWith("/") ? data.url : "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url, self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (w.url.startsWith(self.location.origin)) {
          return w.navigate(url).then((nw) => (nw || w).focus());
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
