# Gateway Contract

This document defines the contract between the Node/Express gateway and the FastAPI backend. It is based strictly on current implementation and separates current behavior from policy requirements.

## 1. Gateway Role

### Current Behavior
- Gateway implementation: `AINDY/server.js` (Express server).
- Responsibilities:
- Accepts HTTP requests from clients on `/api/users`.
- Reads persisted user records from `/network_bridge/authors` (no in-memory user array).
- Forwards a handshake to the backend via `POST http://localhost:8000/network_bridge/connect`.
- Responds to client with the stored user object.
- Limitations:
- In-memory storage only; no persistence across restarts.
- No authentication or authorization.
- No input validation beyond what Express receives.

### Policy Requirements
- Gateway must remain a thin pass-through and must not mutate backend response schemas.

## 2. Handshake Endpoint

### Current Behavior
- Backend endpoint: `POST /network_bridge/connect` (implemented in `AINDY/routes/network_bridge_router.py`).
- Required fields sent by gateway:
- `author_name` (mapped from `user.name`)
- `platform` (hard-coded to `"InfiniteNetwork"`)
- `connection_type` (hard-coded to `"BridgeHandshake"`)
- `notes` (mapped from `user.tagline` or `null`)
- Backend response shape (current implementation):
```json
{
  "status": "connected",
  "author_id": "<string>",
  "platform": "<string>",
  "timestamp": "<iso8601>"
}
```
- Error behavior: not explicitly handled in `AINDY/server.js` beyond logging an error; gateway still returns `201` with the user payload.

### Policy Requirements
- Any change to handshake payload requires updates to:
- `docs/interfaces/API_CONTRACTS.md`
- `docs/interfaces/GATEWAY_CONTRACT.md`
- Human approval

## 3. Data Flow

### Current Behavior
- Client → Gateway: `POST /api/users` with JSON body.
- Gateway → Backend: `POST /network_bridge/connect` with transformed payload:
- `author_name = user.name`
- `platform = "InfiniteNetwork"`
- `connection_type = "BridgeHandshake"`
- `notes = user.tagline || null`
- Gateway input validation: none.
- Timeout or retry behavior: none implemented (axios default behavior only).

### Policy Requirements
- Gateway must not swallow backend error codes.
- Gateway must not convert JSON backend errors to HTML.
- Gateway must not mutate backend response schemas.

## 4. Security Model (Current State)

### Current Behavior
- No authentication or authorization in `AINDY/server.js`.
- No rate limiting.
- No persistence layer.

### Policy Requirements
- Security model changes require explicit human approval.

## 5. Policy Requirements
- Gateway must not mutate backend response schemas.
- Gateway must not swallow backend error codes.
- Gateway must not convert JSON errors to HTML.
- Any change to handshake payload requires:
- Update to `docs/interfaces/API_CONTRACTS.md`.
- Update to this document.
- Human approval.

## 6. Known Risks
- In-memory state volatility: `users` array is lost on restart.
- No authentication or rate limiting.
- No persistence.
- Potential mismatch if backend handshake fields change without gateway update.
