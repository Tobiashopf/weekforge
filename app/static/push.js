// Notifications page: subscribe this device to Web Push, unsubscribe, send a test.
(() => {
  const $ = (id) => document.getElementById(id);
  const status = (text) => { $("push-status").textContent = text; };
  const post = (url, body) =>
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

  const b64ToBytes = (b64) => {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  };

  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (!window.isSecureContext) {
    status("Este endereço não é seguro: notificações só funcionam em http://localhost ou em HTTPS.");
    return;
  }
  if (!supported) {
    status("Este navegador não suporta notificações push. No iPhone, adicione o app à Tela de Início primeiro.");
    return;
  }

  async function refresh() {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    $("push-enable").hidden = !!sub;
    $("push-disable").hidden = !sub;
    $("push-test").disabled = !sub;
    if (Notification.permission === "denied") {
      status("Notificações bloqueadas para este site. Libere nas configurações do navegador.");
    } else {
      status(sub ? "Ativadas neste dispositivo." : "Desativadas neste dispositivo.");
    }
  }

  $("push-enable").addEventListener("click", async () => {
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return refresh();
      const { publicKey } = await (await fetch("/push/public-key")).json();
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(publicKey) });
      const res = await post("/push/subscribe", sub.toJSON());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      location.reload(); // shows this device in the list
    } catch (e) {
      status(`Não foi possível ativar: ${e.message}`);
    }
  });

  $("push-disable").addEventListener("click", async () => {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await post("/push/unsubscribe", { endpoint: sub.endpoint });
      await sub.unsubscribe();
    }
    location.reload();
  });

  $("push-test").addEventListener("click", async () => {
    const r = await (await post("/push/test")).json();
    status(r.sent ? `Teste enviado para ${r.sent} dispositivo(s).` : "Nenhum dispositivo recebeu o teste.");
  });

  refresh();
})();
