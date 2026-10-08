# Tokenization Notes — Gemini vs Groq

## How each provider tokenizes

**Gemini (gemini-2.5-flash)**
- Uses Google's own SentencePiece-based tokenizer, not the same vocabulary as OpenAI/Llama models.
- Text-to-token ratio is roughly 1 token ≈ 4 characters for English, similar ballpark to most modern tokenizers, but exact counts will differ from Groq for the same string.
- `usage_metadata` on the response gives `prompt_token_count`, `candidates_token_count`, and `total_token_count` — this is what `get_query_plan()` needs to read and return.

**Groq (serving Llama 3.3 70B, etc.)**
- Tokenization depends on the *underlying model*, not Groq itself — Llama models use their own SentencePiece/BPE-based tokenizer, different vocabulary from Gemini's.
- Because the vocab differs, the **same prompt will not produce the same token count** on Gemini vs Groq. Don't assume 1:1 parity when comparing quota usage or estimating cost between the two.
- Groq's API is OpenAI-compatible, so usage comes back in the standard `usage.prompt_tokens` / `usage.completion_tokens` / `usage.total_tokens` shape — different field names than Gemini's `usage_metadata`.

## Practical implication for this project
When the fallback logic switches from Gemini to Groq mid-session:
- Token counts per call will not be directly comparable — a Groq call might report a different token count than an equivalent Gemini call for the same question.
- The token accumulator in the backend needs to normalize/label which provider each count came from, or at minimum tag entries so the frontend can show "X tokens (Gemini)" vs "X tokens (Groq)" rather than implying they're the same unit of measurement.

## Response field cheat sheet
| | Gemini | Groq |
|---|---|---|
| Usage field | `usage_metadata` | `usage` |
| Input tokens | `prompt_token_count` | `prompt_tokens` |
| Output tokens | `candidates_token_count` | `completion_tokens` |
| Total | `total_token_count` | `total_tokens` |

---

## Known bug to fix: Token display resets on page refresh

**Issue:** The session token counter (`TokenUsageDisplay.jsx`) currently lives in React state only. On page refresh, that state is wiped, so the running total resets to zero even though the backend has already made those calls against the daily quota.

**Why it matters:** Since Gemini's quota is only 20 requests/day, losing visibility into cumulative usage after a refresh defeats the purpose of tracking it — Ralph won't be able to tell at a glance how close he is to the daily limit.

**Fix direction (to plan out before handing to OpenCode):**
- Persist the running token total in `localStorage` (same pattern already used for dark mode), keyed per day so it naturally resets at midnight instead of on refresh.
- On `App.jsx` mount, read the stored value back in before rendering `TokenUsageDisplay`.
- Update `localStorage` after each successful `/api/ask` response, same point where the in-memory counter currently updates.
