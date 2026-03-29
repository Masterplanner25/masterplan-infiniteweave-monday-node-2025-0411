# A.I.N.D.Y. Client

React + Vite frontend for the A.I.N.D.Y. application shell.

## Rendering Safety

The frontend now treats array-shaped data as untrusted until proven otherwise.

- Shared guards live in `client/src/utils/safe.js`
- `safeArray(value)` returns `value` only when it is an actual array
- `safeMap(value, fn)` logs a development warning and returns `[]` when `value` is not an array

Use `safeMap(...)` for UI list rendering and other array iteration in React components instead of direct `.map(...)` calls.

Example:

```jsx
import { safeMap } from "../utils/safe";

{safeMap(data.items, (item) => (
  <Row key={item.id} item={item} />
))}
```

This is now the required pattern for:

- profile data
- memory results
- dashboard collections
- agent run lists
- RippleTrace graph inputs

Direct member `.map(...)` calls are disallowed by ESLint outside the safe utility implementation.

## Identity Boot Flow

The client now boots the application in two stages:

1. `POST /auth/login` returns a JWT
2. the client immediately calls `GET /identity/boot`

Signup uses the same activation path:

1. `POST /auth/register` creates the user and seeds initial system state
2. the returned JWT is stored immediately
3. the client calls `GET /identity/boot`

The register page lives at `/register` and auto-boots into the authenticated app on success.

`/identity/boot` is the canonical hydration source for:

- `user_id`
- recent memory
- recent agent runs
- current metrics
- active flows
- derived `system_state`

Immediately after signup, boot should include:

- the initial `"User account created"` memory node
- one initialized execution placeholder in recent runs
- baseline metrics with `score = 0.0` and `trajectory = "baseline"`

This state is stored in:

- `AuthContext` for token, login, register, and logout
- `SystemContext` for booted application state

Protected routes require a token. If boot has not completed yet, the app stays behind the boot gate instead of rendering an empty dashboard.

## Token Handling

The client stores the JWT in both:

- `localStorage["token"]`
- `localStorage["aindy_token"]`

The second key is retained for backward compatibility with existing code paths.

All API requests sent through `client/src/api.js` attach:

`Authorization: Bearer <token>`

`client/src/api.js` also normalizes common array response fields before returning parsed JSON to React. If a known array field arrives as `null`, `undefined`, or a non-array value, the client converts it to `[]`.

## Development

Typical commands:

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

Linting enforces the safe mapping rule:

```bash
npm run lint
```
