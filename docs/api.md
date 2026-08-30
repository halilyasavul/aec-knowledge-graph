# REST API Reference

The Flask server (`web_app.py`) exposes the following endpoints. When
`API_SECRET_KEY` is configured, all `/api/*` requests require the
`X-API-Key` header; when `UI_ACCESS_TOKEN` is configured, they also require
`X-Access-Token`. Responses are JSON unless noted.

## Chat

### `POST /api/chat`

Ask the GraphRAG agent a question. Subject to a stricter per-IP rate limit
(`CHAT_RATE_LIMIT_PER_MINUTE`) and a global daily cap (`CHAT_DAILY_CAP`).

```json
{ "message": "What properties does IfcBridge need?", "session_id": "optional" }
```

Response:

```json
{
  "answer": "…",
  "tools_used": [{ "tool": "query_class", "summary": "Queried IfcBridge" }],
  "graph_class": "IfcBridge",
  "ucks_entity_id": null,
  "session_id": "abc123",
  "ids_xml": null,
  "ids_filename": null
}
```

`session_id` keys a server-side conversation history for multi-turn chat.
When the agent generates an IDS specification, `ids_xml` carries the
validated XML.

### `POST /api/chat/reset`

Reset a chat session: `{ "session_id": "abc123" }`.

## IFC graph

### `GET /api/classes?search=term`

Class list (max 50), optionally filtered by code/name substring.

### `GET /api/graph/<class_code>`

vis.js `{nodes, edges}` for one class: property sets, properties,
parent class, EXPRESS attributes, and attribute types.

### `GET /api/graph/overview?limit=100`

High-level Class→PropertySet graph (limit capped at 500).

### `GET /api/node/<node_type>/<code>`

Full properties of a single node. `node_type` is one of `class`, `pset`,
`property`, `attribute`, `type`, `enumeration`, `selecttype`, `enumvalue`.

## UCKS library

### `GET /api/ucks/entities`

List all UCKS entities (id, name, sector, domain, counts).

### `GET /api/ucks/graph/<entity_id>`

vis.js graph for one UCKS entity.

### `GET /api/ucks/yaml/<entity_id>`

The entity's YAML definition (`text/yaml`), from disk or rebuilt from the
graph.

### `POST /api/ucks/clear` (admin)

Deletes **all** UCKS entities and their YAML files. Requires the
`X-Admin-Token` header matching `ADMIN_TOKEN`; the endpoint is disabled
when `ADMIN_TOKEN` is not set.

## Auth

### `POST /api/auth/check`

`{ "token": "…" }` → `{ "valid": true|false }`. Used by the UI's token
gate; exempt from the other security checks.
