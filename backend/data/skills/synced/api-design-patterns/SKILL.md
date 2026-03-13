---
name: api-design-patterns
description: Best Practices für REST-API-Design mit Naming, HTTP-Methoden, Response-Codes und Versionierung.
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# API Design Patterns

Best Practices für REST-API-Design.

## Instructions

Beim Entwerfen oder Reviewen von APIs:

### Naming
- Plural-Nomen für Ressourcen: `/users`, nicht `/user`
- Kebab-Case für mehrteilige Pfade: `/user-profiles`
- Keine Verben in URLs (HTTP-Methoden drücken Aktionen aus)

### HTTP-Methoden
- `GET` → Lesen (idempotent)
- `POST` → Erstellen
- `PUT` → Vollständiger Replace (idempotent)
- `PATCH` → Partielles Update
- `DELETE` → Löschen (idempotent)

### Response-Codes
- `200` OK, `201` Created, `204` No Content
- `400` Bad Request, `401` Unauthorized, `403` Forbidden, `404` Not Found
- `409` Conflict, `422` Unprocessable Entity
- `500` Internal Server Error

### Pagination
- Cursor-basiert bevorzugen (nicht Offset-basiert)
- Response: `{ "data": [...], "next_cursor": "...", "has_more": true }`

### Versionierung
- URL-Prefix: `/api/v1/...`
- Keine Breaking Changes in Minor-Versionen

### Beispiel

Input: "Entwirf eine API für User-Management"
Output:
```
GET    /api/v1/users          → Liste aller User (paginated)
POST   /api/v1/users          → Neuen User erstellen
GET    /api/v1/users/{id}     → Einzelnen User abrufen
PATCH  /api/v1/users/{id}     → User aktualisieren
DELETE /api/v1/users/{id}     → User löschen
```
