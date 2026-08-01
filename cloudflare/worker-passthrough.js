// Passthrough worker: forwards all requests to the origin (Cloudflare Tunnel).
addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
