const CACHE = 'culturebridge-public-v1';
const PUBLIC = ['/pwa/offline', '/pwa/icon-180.png', '/pwa/icon-192.png', '/pwa/icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC)));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('culturebridge-public-') && key !== CACHE)
      .map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname.startsWith('/api/') || url.search) return;
  if (PUBLIC.includes(url.pathname)) {
    event.respondWith(caches.open(CACHE).then(async cache =>
      (await cache.match(request)) || fetch(request)));
  } else if (request.mode === 'navigate') {
    // Never cache personalised HTML, API data, dialogue, history, or POST requests.
    event.respondWith(fetch(request).catch(() =>
      caches.open(CACHE).then(cache => cache.match('/pwa/offline'))));
  }
});
