# Model & API Key Configuration

This directory catalogs **free AI models** and the **API key environment variables** available to the research-and-blog-writer system.

## Files

| File | Purpose |
|---|---|
| `free_models.jsonc` | Detailed declarative registry of providers, free models, IDs, modalities, and notes. |
| `model_list.json` | Machine-friendly flat model list (JSON) for tooling/scripts. |
| `fallback_profiles.jsonc` | Suggested fallback profiles (declarative; not runtime-wired unless code loads it). |
| `api_keys.jsonc.example` | Reference template showing env vars per provider. **Not for secrets.** |

## Source of truth

- **Runtime secrets**: `.env` (copy from `.env.example`). Never commit real keys.
- **Runtime fallback implementation**: `llm_fallback.py` (actual provider order, error handling, backoff, usage stats).
- **This registry**: human/tool-maintainable catalog. Entries marked `verification_needed` must be confirmed against provider catalogs before runtime enablement.

## Providers / keys

| Provider | Env var(s) | Notes |
|---|---|---|
| Groq | `GROQ_API_KEY` | Fast OpenAI-compatible inference; org-level limits. |
| Google Gemini / Gemma | `GEMINI_API_KEY` | AI Studio free tier; model quotas vary. |
| OpenRouter | `OPENROUTER_API_KEY` (`OPEN_ROUTER_API_KEY` alias) | Many `:free` models; `openrouter/free` auto-routes. |
| BeatAPI | `BEATAPI_KEY` (`BEAT_API_KEY` alias) | OpenAI-compatible selected free models. |
| Serper (optional search) | `SERPER_API_KEY` | Not an LLM provider. |

## Suggested agent fallback profile

See `fallback_profiles.jsonc` (`agent_practical_2026_11`, declarative): Groq `gpt-oss-120b` → Gemini `3.8-flash` → OpenRouter `llama-3.3-70b-instruct:free` → OpenRouter `nemotron-3-ultra:free` → OpenRouter `openrouter/free`. This profile is **not active runtime behavior** until wired into `llm_fallback.py`.

## Adding/updating a model

1. Add/update in `free_models.jsonc` and `model_list.json`.
2. If runtime should use it, update `llm_fallback.py` (model IDs, prefixes, key handling) and keep registries consistent.
3. Update `.env.example`/README if keys/providers change.
4. Verify model IDs against provider docs before enabling in production.

## Safety

- Do not store plaintext API keys in repo-tracked files.
- Rotate any key that was committed, logged, or shared.
- Keep model/provider claims factual; free-tier quotas and availability change upstream.
