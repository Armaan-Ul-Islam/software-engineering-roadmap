# Serving and deploying a SPA with Spring Boot

> **In one sentence:** A built SPA is a folder of static files, one unfingerprinted `index.html` plus fingerprinted assets, and deploying it means choosing who serves that folder (Spring Boot itself for one origin and one deployable, or a CDN or reverse proxy in front of the API), telling caches that the assets never change and `index.html` must always be revalidated, returning `index.html` for every unknown non-API path so deep links work, and keeping environment-specific values out of the bundle.

**Why it matters:** The frontend "works on my machine" with the Vite dev server and breaks in production in four predictable ways: a refresh on `/orders/42` returns 404, users see last week's JavaScript because `index.html` was cached, a new release fails because the old `index.html` references chunks that no longer exist, and the staging bundle points at the production API because the URL was baked in at build time. All four are deployment decisions, and they are the backend developer's to make.

## The idea

**What the build produces.** `vite build` writes `dist/index.html` and `dist/assets/index-C3xYz9ab.js`, `dist/assets/index-B8dKq2.css` and one chunk per lazy route (see item 7.1). The file names carry a content hash, so a changed file has a new name and an unchanged one keeps its name. `index.html` has no hash and is the only entry point; it references the hashed files by their current names.

**Two serving options.**

1. Same origin from Spring Boot. Copy `dist/` into `src/main/resources/static/` during the Maven or Gradle build (the `frontend-maven-plugin` runs `npm ci` and `npm run build`, then `maven-resources-plugin` copies). One jar, one origin, no CORS, cookies work unchanged, one thing to deploy and version. Spring Boot serves `classpath:/static/` (and `/public/`, `/resources/`, `/META-INF/resources/`) through its resource handler, and `index.html` at the root is the welcome page. The cost: a frontend-only change needs a backend deploy, and Spring (Tomcat) is serving bytes a CDN would serve closer to the user.
2. Separate hosting. The folder goes to an object store or CDN, or to an nginx container, and a reverse proxy routes `/api/**` to Spring so the browser still sees one origin. Independent deploys and edge caching, at the price of a second artifact and a proxy configuration. If the frontend is on a different origin from the API, item 8.2 (CORS) and item 8.3 (cookies versus tokens) apply in full.

For an internal application, option 1 is hard to beat. For a public site with real traffic, option 2.

**Cache headers.** The fingerprinted assets can be cached forever: `Cache-Control: max-age=31536000, immutable` (one year, and `immutable` tells browsers not to revalidate even on reload). `index.html` must not be: `Cache-Control: no-cache` means "store it, but revalidate before use", so every navigation sends a conditional request and gets a 304 when nothing changed and the new file after a deploy. Without this split, either users keep old HTML pointing at deleted chunks (a cached `index.html`) or every visit re-downloads the whole bundle (no caching at all). Spring Boot's global `spring.web.resources.cache.cachecontrol.*` properties apply one policy to everything, so the two policies need two resource handlers.

**SPA fallback.** The router in the browser owns `/orders/42`, but on a full page load the request reaches the server, which has no such file. The server must return `index.html` (with status 200) for any path that is not a file and not an API route; the router then reads the URL and renders the right page. The fallback must not apply to `/api/**`, which should keep returning a JSON 404, and not to missing assets, where a 404 is the correct answer and `index.html` would be parsed as JavaScript. In nginx this is `try_files $uri /index.html;` under a `location /` block with a separate `location /api/` that proxies; in Spring it is a custom `PathResourceResolver`.

**Environment-specific configuration.** `import.meta.env.VITE_API_URL` is replaced at build time; a bundle built for staging is a different artifact from one built for production, which breaks "build once, deploy everywhere". Three ways out, best first: use relative URLs (`/api/orders`) and let the origin or the proxy decide, so nothing is environment-specific; serve a small `/config.json` (or inject `window.appConfig` into `index.html` from the server) that the app fetches at startup; or build per environment and accept the cost. Secrets never belong in the bundle; anything in `dist/` is public.

**Release ordering.** A user who loaded `index.html` before a deploy will request `index-OLD.js` after it. With same-origin serving the old chunk is gone and the import fails. Options: keep the previous release's assets around for a while (a CDN does this naturally), or catch the chunk-load error and reload the page once. Both are easier than explaining the blank screen.

## Example: Spring Boot serving a Vite build

`src/main/resources/static/` contains `index.html` and `assets/index-C3xYz9ab.js`. The configuration (Spring Boot 3.5):

```java
package com.example.spa;

import java.io.IOException;
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

@Configuration
public class SinglePageAppConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/assets/")
                .setCacheControl(CacheControl.maxAge(Duration.ofDays(365)).immutable());

        registry.addResourceHandler("/**")
                .addResourceLocations("classpath:/static/")
                .setCacheControl(CacheControl.noCache())
                .resourceChain(true)
                .addResolver(new SinglePageAppResourceResolver());
    }

    private static final class SinglePageAppResourceResolver extends PathResourceResolver {

        @Override
        protected Resource getResource(String resourcePath, Resource location) throws IOException {
            if (resourcePath.startsWith("api/")) {
                return null;
            }
            Resource requested = location.createRelative(resourcePath);
            if (requested.isReadable()) {
                return requested;
            }
            return location.createRelative("index.html");
        }
    }
}
```

The `/assets/**` handler is more specific, so it wins for hashed files and never falls back. The `/**` handler serves real files when they exist and `index.html` otherwise, except under `api/`, where returning `null` lets Spring produce its normal 404. Controllers are matched before resource handlers, so `/api/orders/42` reaches `OrderController` regardless. With `server.compression.enabled=true` in `application.properties`, Tomcat gzips the responses.

```bash
for path in / /orders/42 /assets/index-C3xYz9ab.js /api/orders/42 /api/missing; do
  echo "### GET $path"; curl -s -i "http://localhost:8085$path" | grep -E '^HTTP|^Cache-Control|^Content-Type|^\{|^<|^console'
done
```

```text
### GET /
HTTP/1.1 200
Cache-Control: no-cache
Content-Type: text/html;charset=UTF-8
<!doctype html><html><head><script type="module" src="/assets/index-C3xYz9ab.js"></script></head><body><div id="root"></div></body></html>
### GET /orders/42
HTTP/1.1 200
Cache-Control: no-cache
Content-Type: text/html
<!doctype html><html><head><script type="module" src="/assets/index-C3xYz9ab.js"></script></head><body><div id="root"></div></body></html>
### GET /assets/index-C3xYz9ab.js
HTTP/1.1 200
Cache-Control: max-age=31536000, immutable
Content-Type: text/javascript
console.log("app");
### GET /api/orders/42
HTTP/1.1 200
Content-Type: application/json
{"id":"42"}
### GET /api/missing
HTTP/1.1 404
Content-Type: application/json
{"timestamp":"2026-10-29T05:51:23.719+00:00","status":404,"error":"Not Found","path":"/api/missing"}
```

Spring also sends `Last-Modified`, so a conditional request for the asset (`If-Modified-Since`) gets `HTTP/1.1 304`; with `no-cache` on `index.html` that is the request every navigation makes.

The same rules as nginx, when the frontend is hosted separately:

```text
location /api/ {
    proxy_pass http://spring:8080;
}
location /assets/ {
    add_header Cache-Control "max-age=31536000, immutable";
}
location / {
    add_header Cache-Control "no-cache";
    try_files $uri /index.html;
}
```

## Pitfalls

- `spring.web.resources.cache.cachecontrol.max-age=365d` as the only cache setting. `index.html` is now cached for a year and users never see a deploy. Split the policies as above.
- A fallback that also catches `/api/**`. A typo in an API path returns `index.html` with 200, the client parses HTML as JSON and the error message is `Unexpected token '<'`. Exclude the API prefix.
- A fallback that also catches missing assets. A deleted chunk returns `index.html` as `text/html` to a `<script type="module">`, and the console shows a MIME type error instead of a 404. Let `/assets/**` 404.
- Spring Security blocking the static files. Permit `/`, `/index.html` and `/assets/**` explicitly; otherwise the first request redirects to a login page that is itself the SPA, which cannot load.
- `VITE_API_URL=https://api.example.com` baked into one build promoted through environments. Prefer relative paths; if a value really differs per environment, load it at runtime.
- Serving `index.html` with `Cache-Control: no-store`. It works but discards the file on every navigation; `no-cache` plus `Last-Modified` or `ETag` gives a 304 and no transfer.
- Forgetting that a hashed file name is only safe if the hash covers the content. Vite's does; a manual copy step that renames files without hashing, or a bundler with hashing disabled, turns `immutable` into "stale forever".
- Deploying the frontend without the backend contract check from item 8.4, so a same-origin deploy ships a frontend that calls a field the API no longer returns.

## Check yourself

1. A user reports a blank page right after a release and a reload fixes it. Walk through the sequence of cached and uncached files that produces this, and name two ways to prevent it.
2. Why must `index.html` be served with `no-cache` rather than a long `max-age`, and why is a long `max-age` safe for `index-C3xYz9ab.js`?
3. `GET /api/orders/999` returns 200 with an HTML body. Which part of the serving configuration is wrong?
4. Your team wants "build once, deploy to test, staging and production". What has to change about how the frontend learns the API's address, and which option needs no extra request?

## Go deeper

- [Spring Boot: Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.static-content) · the resource locations, the welcome page and the cache properties.
- [web.dev: HTTP cache](https://web.dev/articles/http-cache) · the `Cache-Control` directives and the fingerprint-plus-`no-cache` pattern explained from the browser's side.
- [Vite Guide](https://vite.dev/guide/) · the build section describes the output layout and the environment variable handling.
- [Vite: server.proxy](https://vite.dev/config/server-options.html#server-proxy) · the development-time equivalent of the reverse proxy.

---

Part of [JavaScript & Frontend](../README.md) · items 8.1, 8.5
