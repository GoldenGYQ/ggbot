# User Auth and Transport Split Plan

## Goals

1. Introduce user identity and authentication (login required).
2. Enforce hard isolation across users:
- workspace
- sessions
- transcripts
- runtime state
3. Split responsibilities between HTTP and WebSocket to avoid overlap.

## Current Risks (Why this change is needed)

1. Event stream is globally broadcast from runtime events; no user/session filtering.
2. Runtime/session switching currently mutates a shared runtime object.
3. HTTP and WS are both available for command plane, but no authentication boundary exists yet.
4. Frontend migration to WS-only realtime lifecycle is incomplete.

## Current Implementation Status (2026-04)

- Permission ownership check: **partially done**
  - `request_id` resolution now validates owner connection/session in permission manager.
  - Missing piece: authenticated `user_id` ownership (currently `user_id` is not established by auth).
- Transport split: **in progress**
  - HTTP message streaming endpoint is deprecated in API server comments.
  - WS `send_message` + event push is available and recommended path.
- Auth system: **not implemented**
  - No login/token endpoints in current API.
- Runtime isolation: **not implemented**
  - API mode still uses shared runtime/service state.

## Target Architecture

### 1) Authentication and Identity

- Add auth endpoints:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/logout`
  - `GET /api/v1/auth/me`
- Use short-lived access token + refresh token.
- HTTP passes token via `Authorization: Bearer <token>`.
- WS passes token in one of:
  - query param `?token=...` (for browser compatibility)
  - or first command `auth` before any other command.

### 2) User Isolation Model

Per user root:

- `<global_workspace>/users/<user_id>/workspace`
- `<global_workspace>/users/<user_id>/.ggbot/transcripts`
- `<global_workspace>/users/<user_id>/.ggbot/sessions.json`

No shared transcript/session files across users.

### 3) Runtime Scope

- Keep one runtime per user (lazy initialized):
  - `user_id -> UserRuntimeContext`
- Each context owns:
  - settings
  - registry
  - transcript/session store
  - APIService instance
- Never call `switch_session` on a shared global runtime used by other users.

### 4) HTTP/WS Split (Final Contract)

HTTP is command/query plane:

- Auth endpoints
- Session CRUD endpoints
- Config endpoints
- Optional non-streamed `POST /api/v1/messages` for stateless compatibility

WebSocket is realtime plane:

- `send_message` command
- event push (`assistant_delta`, `tool_call`, `permission_request`, etc.)
- `permission_response` command

Important: once split is complete, frontend message rendering state should be driven by WS events only.

## Migration Plan

### Phase 1: Security Baseline (must-have)

1. Bind `permission_request` to user_id and session_id.
2. Validate `permission_response` ownership before resolving. (connection/session 已实现，user_id 待补齐)
3. Add WS connection context (authenticated user_id).

Acceptance:
- Cross-user permission response is rejected.
- Only owner user can approve/deny own request.

Status:
- `connection_id` / `session_id` owner check: done
- `user_id` owner check with real auth: pending

### Phase 2: User Runtime Isolation

1. Introduce runtime manager for `user_id -> runtime context`.
2. Route every HTTP request using authenticated user context.
3. Route every WS command using connection-bound user context.

Acceptance:
- Two users in parallel do not share sessions/transcripts/workspace state.

### Phase 3: Transport Split

1. Keep HTTP `POST /messages` available but disable stream mode by default.
2. Frontend chat page:
   - send prompt via WS command
   - consume rendering events only from WS
3. Keep HTTP for session/config queries and page bootstrapping.

Acceptance:
- No duplicate rendering caused by dual stream ingestion.

### Phase 4: Login UX and Ops

1. Add frontend login page + token storage + auto refresh.
2. Add logout and token revocation logic.
3. Add audit fields to key events (`user_id`, `session_id`, `connection_id`).

Acceptance:
- User can login/logout reliably.
- Session and data are isolated by account.

## API Contract Draft (WS)

### Client -> Server

- `auth`:
```json
{"type":"command","command":"auth","payload":{"token":"..."}}
```

- `send_message`:
```json
{"type":"command","command":"send_message","payload":{"content":"...","session_id":"..."}}
```

- `permission_response`:
```json
{"type":"command","command":"permission_response","payload":{"request_id":"...","allowed":true,"reason":"..."}}
```

### Server -> Client

- command response:
```json
{"type":"response","command":"...","payload":{"success":true}}
```

- event:
```json
{"type":"event","event_type":"assistant_delta","data":{"delta":"..."}}
```

## Data Model Additions

- `PermissionRequest` must include:
  - `request_id`
  - `user_id`
  - `session_id`
  - `tool_name`
  - `arguments`
  - `created_ms`
- Runtime event envelope should include at least:
  - `user_id`
  - `session_id`
  - `source`

## Backward Compatibility Strategy

1. Keep existing HTTP endpoints for one release cycle.
2. Add warning logs when HTTP stream mode is used in mixed mode.
3. After frontend migration, make WS the only realtime stream path.

## Recommended Immediate Next Step

Implement authentication (token + WS bind user context) first, then complete Phase 1 user-level ownership validation.
