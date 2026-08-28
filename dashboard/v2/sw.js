'use strict';

const SHELL_CACHE = 'sabi-shell-v2.3.0.0';
const APP_SHELL = [
  '/',
  '/manifest.json?v=2.3.0.0',
  '/favicon.ico?v=2.3.0.0',
  '/icon.svg?v=2.3.0.0',
  '/assets/app.css?v=2.3.0.0',
  '/assets/app.js?v=2.3.0.0',
  '/assets/history_insights.js?v=2.3.0.0',
  '/assets/icon-192.png?v=2.3.0.0',
  '/assets/icon-512.png?v=2.3.0.0',
  '/assets/icon-maskable-192.png?v=2.3.0.0',
  '/assets/icon-maskable-512.png?v=2.3.0.0',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== SHELL_CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/')),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => cached || fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then(cache => cache.put(request, copy));
      }
      return response;
    })),
  );
});

self.addEventListener('push', event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = {body: event.data ? event.data.text() : 'Sabi Boy has an update.'};
  }
  const title = String(payload.title || 'Sabi Boy');
  const options = {
    body: String(payload.body || 'A result has changed.'),
    icon: '/assets/icon-192.png?v=2.3.0.0',
    badge: '/assets/icon-192.png?v=2.3.0.0',
    tag: String(payload.tag || 'sabi-boy-update'),
    renotify: Boolean(payload.renotify),
    data: {url: String(payload.url || '/')},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(clients => {
      const existing = clients.find(client => client.url.startsWith(self.location.origin));
      if (existing) {
        existing.navigate(target);
        return existing.focus();
      }
      return self.clients.openWindow(target);
    }),
  );
});
