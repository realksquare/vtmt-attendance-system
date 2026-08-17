const CACHE_NAME = 'smart-attendance-v13';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(keys.map((key) => caches.delete(key)));
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        fetch(event.request).catch(async () => {
            const cached = await caches.match(event.request);
            if (cached) return cached;
            return new Response('', { status: 503, statusText: 'Service Unavailable' });
        })
    );
});
