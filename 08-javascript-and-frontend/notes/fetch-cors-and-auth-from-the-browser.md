# fetch, CORS and authentication from the browser

> **In one sentence:** `fetch` only rejects on network failure (so you must check `response.ok` yourself), the browser blocks cross-origin responses unless the server opts in through CORS headers (or you avoid the problem by serving frontend and API from one origin), and a SPA authenticates most safely with an `HttpOnly` session cookie plus CSRF protection, with OAuth2 tokens kept on a backend-for-frontend rather than in the browser.

**Why it matters:** The first afternoon of every Spring-plus-React project is spent on the same three errors: a 500 that the frontend treated as success, a red "blocked by CORS policy" console message, and a login that works in Postman but not in the browser. All three are the browser's security model doing its job, and each has a one-paragraph explanation.

## The idea

**`fetch` essentials.** `fetch(url, options)` returns a promise of a `Response`. It rejects only when no response arrived: DNS failure, connection refused, a CORS block, or an abort. A 404 or 500 *fulfils* the promise with `response.ok === false`, so every call needs an explicit status check. The body is read once, asynchronously, with `response.json()` or `response.text()`. JSON bodies are not special: set `Content-Type: application/json` and `JSON.stringify` yourself. `AbortController` cancels an in-flight request (`signal: controller.signal`, then `controller.abort()`), and `AbortSignal.timeout(milliseconds)` gives a ready-made timeout signal. The `credentials` option decides whether cookies travel: `"same-origin"` (the default) sends them only to your own origin; `"include"` sends them cross-origin, which the server must also allow.

**CORS in one paragraph.** An origin is scheme + host + port, so `http://localhost:5173` (Vite) and `http://localhost:8080` (Spring Boot) are different origins. The browser lets your script *send* most cross-origin requests but refuses to let it *read* the response unless the response carries `Access-Control-Allow-Origin` matching the page's origin. Requests that are not "simple" (any method other than GET, HEAD or POST, or a header outside the safelist, which includes `Content-Type: application/json`, `Authorization` and `X-XSRF-TOKEN`) are preceded by a **preflight**: an `OPTIONS` request the server must answer with `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` and, if cookies are involved, `Access-Control-Allow-Credentials: true` plus an exact origin (never `*`). CORS is enforced by the browser only; `curl` and Postman never see it. When it fails, Chrome logs `Access to fetch at 'http://localhost:8080/api/customers' from origin 'http://localhost:5173' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.` and the promise rejects with `TypeError: Failed to fetch`.

**Two ways to make it work with Spring.**

1. Allow it on the server. Define a `CorsConfigurationSource` bean listing the frontend origin, the methods and the headers, with `setAllowCredentials(true)` if you use cookies, and enable it with `http.cors(Customizer.withDefaults())` in the security configuration so that Spring Security answers the preflight *before* authentication. A preflight that reaches an authenticated endpoint gets a 401 and the browser reports it as a CORS failure.
2. Avoid it. In development, let Vite proxy `/api` to Spring so the browser only ever talks to `localhost:5173`. In production, serve the built frontend from Spring Boot's static resources or put both behind one reverse proxy. Same origin means no CORS, no preflights and cookies that simply work. Cookies have no notion of port, so a cookie set by `localhost:8080` is also sent to `localhost:5173`, which is why the dev proxy preserves sessions.


**Authentication from a SPA.** Two sound patterns:

1. **Session cookie with CSRF token.** The SPA posts credentials to Spring Security, which creates a server-side session and sets a cookie with `HttpOnly`, `Secure` and `SameSite=Lax`. JavaScript cannot read the cookie, so an XSS cannot steal it, but the browser attaches it automatically, so a cross-site form post could ride on it. `SameSite=Lax` blocks most of that; the CSRF token closes the rest: Spring writes a readable `XSRF-TOKEN` cookie, the SPA copies its value into an `X-XSRF-TOKEN` header, and Spring Security compares them. The Spring Security reference has the complete SPA configuration; copy it rather than assembling it.
2. **OAuth2 Authorization Code with PKCE, through a backend-for-frontend (BFF).** Rather than making the browser an OAuth2 client that stores tokens, the Spring application is the client (`spring-boot-starter-oauth2-client` with `oauth2Login()`). It redirects the user to the identity provider, exchanges the code for tokens, keeps them server-side, and gives the browser nothing but a session cookie. Calls to downstream APIs attach the access token on the server (Spring Cloud Gateway's token relay does exactly this). From the browser's point of view this is pattern 1 again, including CSRF. The IETF's current guidance for browser-based apps recommends this architecture over tokens in the browser.

**Where tokens live, and what that costs.** An `HttpOnly` cookie is invisible to scripts, so XSS cannot read it, but it needs CSRF protection. JavaScript memory is readable by XSS only while the page is open and is lost on reload, so it needs silent refresh. `localStorage` is readable by any script on the page, forever, and is the wrong place for anything that grants access.

## Example: a typed `fetch` wrapper for a Spring API

Spring Boot 3 returns errors as RFC 9457 Problem Details (`application/problem+json`) when `spring.mvc.problemdetails.enabled=true` or when controllers return `ProblemDetail`. The wrapper turns those into a typed exception and sends the CSRF header.

```typescript
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  [extension: string]: unknown;
}

export class ApiError extends Error {
  constructor(readonly problem: ProblemDetails, readonly response: Response) {
    super(problem.title ?? `HTTP ${response.status}`);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json, application/problem+json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const csrfToken = readCookie("XSRF-TOKEN");
  if (csrfToken !== undefined) {
    headers.set("X-XSRF-TOKEN", csrfToken);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "same-origin",
    signal: init.signal ?? AbortSignal.timeout(10_000),
  });

  if (!response.ok) {
    throw new ApiError(await readProblem(response), response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readProblem(response: Response): Promise<ProblemDetails> {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("json")) {
    try {
      return (await response.json()) as ProblemDetails;
    } catch {
      // the body claimed to be JSON and was not; fall back to the status line
    }
  }
  return { title: response.statusText, status: response.status };
}

function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((candidate) => candidate.startsWith(prefix));
  return cookie === undefined ? undefined : decodeURIComponent(cookie.slice(prefix.length));
}
```

Using it:

```typescript
try {
  const customer = await apiFetch<Customer>(`/api/customers/${customerId}`);
} catch (error) {
  if (error instanceof ApiError && error.problem.status === 404) {
    showNotFound();
  } else {
    throw error;
  }
}
```

The `as T` casts are the trust boundary; see item 2.4 for validating them. If the API lives on another origin, switch `credentials` to `"include"` and configure CORS with credentials on the server.

The Vite side of the proxy approach:

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
```

Requests from the page to `/api/...` go to Vite, which forwards them to Spring and relays the response, cookies included; `changeOrigin` rewrites the `Host` header to the target.

## Pitfalls

- Treating a fulfilled `fetch` as success. The symptom is a UI that renders `undefined` fields after a 500. Check `response.ok` in one place, the wrapper.
- `Access-Control-Allow-Origin: *` together with `credentials: "include"`. The browser rejects that combination; the server must echo the exact origin.
- CORS configured in Spring MVC but not in Spring Security. The preflight hits the security filter chain first, gets a 401, and the console shows a CORS error that has nothing to do with CORS configuration.
- Storing a JWT in `localStorage` because "cookies are old". Any XSS now has a durable credential. Use the cookie-plus-CSRF pattern or a BFF.
- Disabling CSRF protection to make the first POST work. With cookie authentication that is the vulnerability itself. Send the token instead.
- Forgetting that `AbortSignal.timeout` aborts the whole request including body reading. A slow download of a legitimate large response fails with an `AbortError`; give uploads and downloads their own budget.

## Check yourself

1. Why does the same request succeed in Postman and fail in the browser with a CORS error, and what does that tell you about where CORS is enforced?
2. A preflight `OPTIONS /api/orders` returns 401. Which Spring component answered it, and in what order should CORS and authentication run?
3. Your SPA keeps the access token in memory and sends it as `Authorization: Bearer`. What attack does `HttpOnly` protect against that this design does not, and what new attack does switching to cookies introduce?
4. In the BFF pattern, which component holds the refresh token, what does the browser hold, and why does the browser still need CSRF protection?

## Go deeper

- [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch) · the options, response handling, and why errors are not thrown for HTTP status codes.
- [MDN: Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) · simple requests, preflights and every header, with diagrams.
- [Spring Framework: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) and [Vite: server.proxy](https://vite.dev/config/server-options.html#server-proxy) · the two sides of the development setup.
- [Spring Security: CSRF with JavaScript SPAs](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html#csrf-integration-javascript-spa) · the complete cookie-plus-header configuration to copy.
- [IETF: OAuth 2.0 for Browser-Based Apps](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps) · the current best practice; read the architecture comparison and the BFF section.

---

Part of [JavaScript & Frontend](../README.md) · items 4.4, 8.2, 8.3
