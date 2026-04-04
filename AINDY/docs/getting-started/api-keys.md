# Platform API Keys

Platform API keys authenticate machine clients on `/platform/*`.

## Create a key

Use a JWT for key management. The raw key is returned once.

```bash
curl -X POST http://localhost:8000/platform/keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"local-cli","scopes":["memory.read","memory.write"]}'
```

Response fields:
- `id`
- `key`
- `key_prefix`
- `scopes`
- `is_active`

Store `key` immediately. Later list/detail calls never return it again.

## Use a key

Send the raw key in `X-Platform-Key`.

```bash
curl -X POST http://localhost:8000/platform/syscall \
  -H "X-Platform-Key: aindy_your_key" \
  -H "Content-Type: application/json" \
  -d '{"name":"sys.v1.memory.write","payload":{"content":"api key test","tags":["quickstart"]}}'
```

## Supported scopes

- `flow.read`
- `flow.execute`
- `memory.read`
- `memory.write`
- `agent.run`
- `webhook.manage`
- `platform.admin`

`platform.admin` implies full platform access.

## Revoke and list

```bash
curl http://localhost:8000/platform/keys \
  -H "Authorization: Bearer $JWT"
```

```bash
curl -X DELETE http://localhost:8000/platform/keys/$KEY_ID \
  -H "Authorization: Bearer $JWT"
```

Observed contract:
- a valid key can call `POST /platform/syscall`
- a revoked key is rejected with `401`
- an authenticated but under-scoped key is rejected with `403`
- keys are stored hashed at rest and exposed in plaintext only on creation
