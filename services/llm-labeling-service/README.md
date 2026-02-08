# llm-labeling-service

A minimal **labeling helper** that supports keyword-based weak labeling.

It lets teams bootstrap labeled datasets quickly, then refine with human review.

## API

### Create a rule

`POST /api/v1/labeling/rules`

Request:
- `name`: unique per tenant/project
- `label`: label to emit
- `keywords`: string[] (simple substring match)
- optional `is_active`: bool

### List / update rules

- `GET /api/v1/labeling/rules`
- `PATCH /api/v1/labeling/rules/{rule_id}`
- `DELETE /api/v1/labeling/rules/{rule_id}`

### Apply labeling

`POST /api/v1/labeling`

Request:
- `items`: list of `{ id?, text }` (or list of strings)
- optional `rules`: inline rules (if omitted, loads active rules from DB)
- optional `top_n`: max labels to return per item

Response:
- per item: `best_label`, `labels`, and match details.

## Notes

- This is intentionally simple (no UI). You can add a human review UI later.
- For advanced labeling, plug in LLM-assisted suggestions and consensus workflows.
