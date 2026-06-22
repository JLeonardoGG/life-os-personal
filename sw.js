const CACHE_NAME = 'lifeos-personal-v27';
const HTML_CACHE_KEY = './lifeos_dashboard.html';
const APP_SHELL = [
  './lifeos_dashboard.html?v=v27-local-backend',
  './manifest.webmanifest',
  './lifeos-icon.svg',
  './frontend/assets/app.css',
  './frontend/assets/vendor/chart.js',
  './frontend/assets/vendor/jszip.min.js',
  './frontend/assets/vendor/pdf.min.js',
  './frontend/assets/vendor/pdf.worker.min.js',
  './frontend/assets/vendor/xlsx.full.min.js',
  './frontend/assets/vendor/fontawesome/css/all.min.css',
  './frontend/assets/vendor/fontawesome/webfonts/fa-brands-400.woff2',
  './frontend/assets/vendor/fontawesome/webfonts/fa-regular-400.woff2',
  './frontend/assets/vendor/fontawesome/webfonts/fa-solid-900.woff2',
  './frontend/assets/vendor/fontawesome/webfonts/fa-v4compatibility.woff2',
  './frontend/js/core/api.js',
  './frontend/js/core/bootstrap.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith('lifeos-personal') && key !== CACHE_NAME).map(key => caches.delete(key))
    ))
  );
  self.clients.claim();
});

self.addEventListener('message', event => {
  if (event.data?.type !== 'CLEAR_LIFEOS_CACHE') return;
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith('lifeos-personal')).map(key => caches.delete(key))
    ))
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  const isHtml = event.request.mode === 'navigate' || url.pathname.endsWith('/lifeos_dashboard.html');

  if (isHtml) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' })
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(HTML_CACHE_KEY, copy));
          return response;
        })
        .catch(() => caches.match(HTML_CACHE_KEY).then(cached => cached || caches.match('./lifeos_dashboard.html?v=v27-local-backend')))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
      return response;
    }))
  );
});
