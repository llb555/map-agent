Use this skill when runtime state includes `context_payload.directory`, `context_payload.search_catalog`, or `context_payload.knowledge_hits`.

Interpretation rules:
- Read `directory` first to identify the available blocks and reading order.
- `search_catalog.total` means matched shop count, not machine count.
- `search_catalog.top_shops` is only a ranked preview of current results; do not claim it is the full result set unless counts match.
- Prefer mentioning 1 to 3 shops by `name` plus `city_name` or `county_name`.
- Use `query.sort_by`, `query.sort_order`, and `query.sort_title_name` to explain why the ranking is ordered that way.
- Treat `query.rewrite_*` fields as auxiliary normalization hints for interpreting the user's original wording, not as proof that the downstream query actually executed with those values.
- When both non-rewrite fields and `rewrite_*` fields exist, describe the actual current result set from the non-rewrite fields first, and use `rewrite_*` only to explain aliases, abbreviations, or inferred intent.
- When `query.sort_by=distance`, `top_shops[].distance_m` is straight-line distance from the provided origin in meters; mention it as an estimate rather than a route distance.
- If a top shop exposes `detail_sections`, read the matching item in `shop_details` only when those sections are needed for the answer.
- `transport`, `arcades`, and `comment` belong to `shop_details`; treat them as supporting detail, not the main search summary.
- If `knowledge_hits` exists, treat it as textual evidence. Quote or paraphrase only what is present in the hit snippet; do not extend it into unsupported claims.
- Prefer `knowledge_hits.hits[0..2]` as support when the user asks for comments, FAQ, rules, or long-form guidance.
- If `knowledge_hits.query` or `query.rewrite_knowledge_query` exists, treat it as the normalized retrieval topic when summarizing what the knowledge lookup was about.
- If `search_catalog.total=0`, clearly say no matching shop was found and suggest another keyword or region.
