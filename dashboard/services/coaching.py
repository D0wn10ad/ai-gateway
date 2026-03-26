"""Two-stage AI coaching pipeline.

Stage 1: Summarize user conversations using a cheap model (chatgpt-5-nano).
Stage 2: Generate coaching tips using a thinking model (chatgpt-5.4-thinking).

Results are cached daily per user.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, date

import asyncpg
import httpx

from auth.models import CurrentUser
from config import Settings
from db.coaching_queries import (
    get_cached_coaching,
    get_chat_conversations,
    get_file_uploads,
    get_request_timeline,
    get_spend_profile,
    save_coaching,
)
from db.queries import get_billing_period_dates, get_user_budget
from models.responses import CoachingResponse, CoachingStats, CoachingTip

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SUMMARIZE_SYSTEM_PROMPT = """\
Summarize each conversation briefly. For each, provide:
- topic: What the user was working on (1 sentence)
- task_type: one of: simple_question, email_draft, data_analysis, coding, \
creative_writing, research, document_review, brainstorming, other
- complexity: low, medium, or high
- observations: Notable patterns (e.g., "many follow-up refinements", \
"questions grew increasingly specific", "simple task completed quickly")

Return JSON: {"summaries": [{"title": "...", "topic": "...", "task_type": "...", \
"complexity": "...", "observations": "..."}]}"""

COACHING_SYSTEM_PROMPT = """\
You are an AI usage coach for employees using the AI Gateway.
You are given AI-generated summaries of the user's conversations, along with their \
file upload patterns, model choices, and spending data. Provide specific, actionable \
coaching tips to help them get more value from their weekly budget.

CONTEXT:
- Users have a weekly budget (typically $5) shared across all AI models
- Every message in a chat includes the FULL conversation history as context (input tokens)
- Uploaded files are re-sent as context with EVERY subsequent message in the same chat
- Longer chats = exponentially more input tokens = faster budget drain
- "Thinking" model variants use step-by-step reasoning for complex problems

COACHING FOCUS AREAS (prioritize by budget impact):

1. FILE UPLOAD EFFICIENCY: If a file was uploaded early in a long chat \
(high messages_after count), the file content was re-sent dozens of times. \
Suggest: extract key data points into the prompt instead, or start a fresh \
chat when switching to new questions about the same file.

2. CONVERSATION LENGTH: Chats with 20+ messages have massive context growth. \
Each new message re-sends everything before it. Suggest starting fresh chats \
for new topics, and including only the relevant context the AI needs.

3. MODEL SELECTION: Match model capability to task complexity. \
Simple tasks (drafts, formatting, quick questions) -> chatgpt-5-nano. \
Standard tasks -> chatgpt-5-mini or claude-haiku-4-5. \
Complex analysis, coding, reasoning -> chatgpt-5.4 or claude-sonnet-4-6. \
Step-by-step reasoning -> thinking model variants.

4. CROSS-CHAT FILE REUSE: If the same file appears in multiple chats, \
suggest keeping file-related analysis in one dedicated chat.

5. GENERAL EFFICIENCY: Any other patterns that waste budget or reduce quality.

RULES:
- Provide 3-5 tips, ranked by estimated budget impact
- Reference specific conversations by title and specific files by name
- Include estimated savings where possible (e.g., "$0.50/week")
- Be encouraging — frame as opportunities, not criticism
- Keep each tip to 2-3 sentences max
- Only mention patterns you actually observe in the data
- If usage already looks efficient, say so and offer advanced tips

OUTPUT FORMAT (JSON):
{
  "summary": "One sentence overall assessment of their week",
  "tips": [
    {
      "title": "Short actionable headline",
      "detail": "Specific explanation referencing their conversations/files/models",
      "category": "FILES|CONTEXT|MODEL|GENERAL",
      "estimated_savings": "$X.XX/week" or null
    }
  ]
}"""


# ---------------------------------------------------------------------------
# Session detection
# ---------------------------------------------------------------------------

def detect_sessions(timeline: list[dict]) -> dict:
    """Group requests into sessions by 30-minute gaps.

    Detects "context escalation" — sessions where prompt_tokens grows >3x
    from first to last request, indicating a long chat with ballooning context.
    """
    if not timeline:
        return {"total": 0, "with_context_escalation": 0,
                "longest_session_requests": 0,
                "max_prompt_tokens_in_single_request": 0}

    sessions: list[list[dict]] = []
    current: list[dict] = [timeline[0]]

    for req in timeline[1:]:
        prev_time = current[-1].get("startTime")
        curr_time = req.get("startTime")
        if prev_time and curr_time:
            gap = (curr_time - prev_time).total_seconds()
            if gap > 1800:  # 30 minute gap = new session
                sessions.append(current)
                current = []
        current.append(req)
    if current:
        sessions.append(current)

    escalation_count = 0
    longest = 0
    max_prompt = 0

    for session in sessions:
        longest = max(longest, len(session))
        for req in session:
            pt = req.get("prompt_tokens") or 0
            max_prompt = max(max_prompt, pt)

        first_pt = (session[0].get("prompt_tokens") or 0)
        last_pt = (session[-1].get("prompt_tokens") or 0)
        if first_pt > 0 and last_pt > first_pt * 3 and len(session) >= 3:
            escalation_count += 1

    return {
        "total": len(sessions),
        "with_context_escalation": escalation_count,
        "longest_session_requests": longest,
        "max_prompt_tokens_in_single_request": max_prompt,
    }


# ---------------------------------------------------------------------------
# File analysis
# ---------------------------------------------------------------------------

def analyze_files(file_rows: list[dict] | None) -> dict:
    """Build file analysis summary from raw file upload query results."""
    if not file_rows:
        return {
            "total_uploads": 0, "unique_files": 0,
            "files_by_chat": [], "cross_chat_files": {},
            "highest_impact": None,
        }

    # Group by chat
    by_chat: dict[str, list[dict]] = {}
    for r in file_rows:
        cid = r["chat_id"]
        by_chat.setdefault(cid, []).append(r)

    files_by_chat = []
    all_filenames: dict[str, list[str]] = {}  # filename -> [chat_title, ...]
    highest_impact = None

    for cid, rows in by_chat.items():
        chat_entry = {
            "chat_title": rows[0].get("chat_title", "Untitled"),
            "total_messages": rows[0].get("chat_total_messages", 0),
            "files": [],
        }
        for r in rows:
            fname = r.get("filename", "unknown")
            msgs_after = r.get("messages_after_upload", 0)
            chat_entry["files"].append({
                "name": fname,
                "messages_after": msgs_after,
            })
            all_filenames.setdefault(fname, []).append(
                r.get("chat_title", "Untitled")
            )
            if highest_impact is None or msgs_after > highest_impact["messages_after"]:
                highest_impact = {"name": fname, "messages_after": msgs_after}
        files_by_chat.append(chat_entry)

    # Detect files used across multiple chats
    cross_chat = {}
    for fname, chat_titles in all_filenames.items():
        unique_chats = list(set(chat_titles))
        if len(unique_chats) > 1:
            cross_chat[fname] = {"chats": unique_chats, "upload_count": len(chat_titles)}

    unique_names = set()
    for r in file_rows:
        unique_names.add(r.get("filename", "unknown"))

    return {
        "total_uploads": len(file_rows),
        "unique_files": len(unique_names),
        "files_by_chat": files_by_chat,
        "cross_chat_files": cross_chat,
        "highest_impact": highest_impact,
    }


# ---------------------------------------------------------------------------
# Stage 1: Summarize conversations (cheap model)
# ---------------------------------------------------------------------------

async def _call_llm(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    reasoning_effort: str | None = None,
) -> dict | None:
    """Call LiteLLM chat completions and parse JSON response."""
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "user": "system-dashboard-coaching",
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    try:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not content:
            usage = data.get("usage", {})
            print(f"LLM empty content ({model}): usage={usage}")
            return None
        return json.loads(content)
    except httpx.HTTPStatusError as e:
        print(f"LLM HTTP error ({model}): {e.response.status_code} {e.response.text[:300]}")
        return None
    except (httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError) as e:
        log.error("LLM call failed (%s): %s", model, e)
        return None


async def summarize_conversations(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    chat_data: list[dict] | None,
) -> list[dict] | None:
    """Stage 1: Send user messages to a cheap model for summarization."""
    if not chat_data:
        return None

    # Build the input: conversations with user messages grouped by chat
    conversations = []
    for chat in chat_data:
        texts = chat.get("user_message_texts", [])
        if not texts:
            continue
        conversations.append({
            "title": chat.get("title", "Untitled"),
            "message_count": chat.get("total_messages", 0),
            "models_used": chat.get("models_used", []),
            "user_messages": texts,
        })

    if not conversations:
        return None

    payload = json.dumps({"conversations": conversations})
    result = await _call_llm(
        client, api_key, model,
        SUMMARIZE_SYSTEM_PROMPT, payload,
        max_tokens=8000, temperature=0.3,
        reasoning_effort="low",
    )

    if result and "summaries" in result:
        return result["summaries"]
    return None


# ---------------------------------------------------------------------------
# Stage 2: Generate coaching (thinking model)
# ---------------------------------------------------------------------------

def build_coaching_profile(
    user: CurrentUser,
    budget: float,
    budget_spent: float,
    spend_data: list[dict],
    sessions: dict,
    summaries: list[dict] | None,
    chat_data: list[dict] | None,
    file_analysis: dict,
) -> dict:
    """Assemble the structured profile sent to the coaching model."""
    # Merge summaries with chat metadata
    conv_summaries = []
    summary_by_title: dict[str, dict] = {}
    if summaries:
        for s in summaries:
            summary_by_title[s.get("title", "")] = s

    if chat_data:
        for chat in chat_data:
            title = chat.get("title", "Untitled")
            summary = summary_by_title.get(title, {})
            entry: dict = {
                "title": title,
                "message_count": chat.get("total_messages", 0),
                "user_messages": chat.get("user_messages", 0),
                "models_used": chat.get("models_used", []),
            }
            if summary:
                entry["topic"] = summary.get("topic", "")
                entry["task_type"] = summary.get("task_type", "")
                entry["complexity"] = summary.get("complexity", "")
                entry["observations"] = summary.get("observations", "")
            # Attach file info from file_analysis
            chat_files = []
            for fc in file_analysis.get("files_by_chat", []):
                if fc.get("chat_title") == title:
                    chat_files = fc.get("files", [])
                    break
            if chat_files:
                entry["files"] = chat_files
            conv_summaries.append(entry)

    # Build spend_by_model (serialize Decimal values)
    spend_by_model = []
    for s in spend_data:
        spend_by_model.append({
            "model": s.get("model", "unknown"),
            "requests": int(s.get("request_count", 0)),
            "spend": round(float(s.get("total_spend", 0)), 4),
            "avg_prompt_tokens": int(s.get("avg_prompt_tokens", 0)),
            "avg_completion_tokens": int(s.get("avg_completion_tokens", 0)),
            "max_prompt_tokens": int(s.get("max_prompt_tokens", 0)),
        })

    start, end = get_billing_period_dates()

    return {
        "user": {
            "name": user.name or "User",
            "budget_limit_weekly": budget,
            "budget_spent": round(budget_spent, 4),
            "percent_used": round((budget_spent / budget * 100) if budget > 0 else 0, 1),
            "period": f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}",
        },
        "spend_by_model": spend_by_model,
        "sessions": sessions,
        "conversation_summaries": conv_summaries,
        "file_analysis": {
            "total_uploads": file_analysis.get("total_uploads", 0),
            "unique_files": file_analysis.get("unique_files", 0),
            "highest_impact": file_analysis.get("highest_impact"),
            "cross_chat_files": file_analysis.get("cross_chat_files", {}),
        },
        "model_pricing_reference": {
            "chatgpt-5-nano": "cheapest — great for simple questions, email drafts, formatting",
            "chatgpt-5-mini": "moderate — good for most tasks",
            "chatgpt-5.4": "premium — best for complex analysis, coding, reasoning",
            "claude-sonnet-4-6": "premium — best for nuanced writing, detailed analysis",
            "claude-haiku-4-5": "moderate — fast, good for straightforward tasks",
            "thinking variants": "add '-thinking' suffix for step-by-step reasoning on complex problems",
        },
    }


async def generate_coaching(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    profile: dict,
) -> dict | None:
    """Stage 2: Send profile to thinking model for coaching analysis."""
    payload = json.dumps(profile)
    return await _call_llm(
        client, api_key, model,
        COACHING_SYSTEM_PROMPT, payload,
        max_tokens=8000, temperature=0.7,
        reasoning_effort="medium",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def get_or_generate_coaching(
    pool: asyncpg.Pool,
    openwebui_pool: asyncpg.Pool | None,
    litellm_client: httpx.AsyncClient | None,
    user: CurrentUser,
    settings: Settings,
) -> CoachingResponse:
    """Main entry point: check cache or generate coaching via two-stage pipeline."""
    start, end = get_billing_period_dates()
    today = date.today()

    # 1. Check daily cache
    cached = await get_cached_coaching(pool, user.email, today)
    if cached:
        coaching = cached["coaching"]
        profile = cached["profile"]
        stats = _build_stats(profile)
        return CoachingResponse(
            period_start=start.strftime("%b %d"),
            period_end=end.strftime("%b %d, %Y"),
            summary=coaching.get("summary"),
            tips=[CoachingTip(**t) for t in coaching.get("tips", [])],
            stats=stats,
            status="ready",
            cached=True,
            generated_at=cached.get("generated_at"),
        )

    # 2. Data extraction: parallel queries
    spend_task = get_spend_profile(pool, user.email)
    timeline_task = get_request_timeline(pool, user.email)
    budget_task = get_user_budget(pool, user.email)

    # OpenWebUI queries (may be None if pool unavailable)
    chat_task = get_chat_conversations(openwebui_pool, user.user_id)
    file_task = get_file_uploads(openwebui_pool, user.user_id)

    spend_data, timeline, budget_val, chat_data, file_rows = await asyncio.gather(
        spend_task, timeline_task, budget_task, chat_task, file_task,
    )

    budget = budget_val if budget_val else settings.DEFAULT_WEEKLY_BUDGET
    budget_spent = sum(float(s.get("total_spend", 0)) for s in spend_data)

    # Process raw data
    sessions = detect_sessions(timeline)
    file_analysis = analyze_files(file_rows)

    # Build basic stats (always available, even if AI fails)
    total_requests = sum(int(s.get("request_count", 0)) for s in spend_data)
    total_chats = len(chat_data) if chat_data else 0
    avg_msgs = 0.0
    longest_chat = 0
    if chat_data:
        msg_counts = [c.get("total_messages", 0) for c in chat_data]
        avg_msgs = round(sum(msg_counts) / len(msg_counts), 1) if msg_counts else 0.0
        longest_chat = max(msg_counts) if msg_counts else 0

    stats = CoachingStats(
        total_requests=total_requests,
        total_chats=total_chats,
        avg_messages_per_chat=avg_msgs,
        longest_chat_messages=longest_chat,
        total_file_uploads=file_analysis.get("total_uploads", 0),
        unique_files=file_analysis.get("unique_files", 0),
    )

    period_start = start.strftime("%b %d")
    period_end = end.strftime("%b %d, %Y")

    # If no LiteLLM client or API key, return stats only
    if not litellm_client or not settings.COACHING_API_KEY:
        return CoachingResponse(
            period_start=period_start, period_end=period_end,
            stats=stats, status="unavailable",
        )

    # 3. Stage 1: Summarize conversations (cheap model)
    summaries = None
    if chat_data:
        try:
            summaries = await summarize_conversations(
                litellm_client, settings.COACHING_API_KEY,
                settings.COACHING_SUMMARIZE_MODEL, chat_data,
            )
        except Exception as e:
            log.error("Stage 1 summarization failed: %s", e)

    # 4. Stage 2: Generate coaching (thinking model)
    profile = build_coaching_profile(
        user, budget, budget_spent, spend_data, sessions,
        summaries, chat_data, file_analysis,
    )

    coaching = None
    try:
        coaching = await generate_coaching(
            litellm_client, settings.COACHING_API_KEY,
            settings.COACHING_ANALYSIS_MODEL, profile,
        )
    except Exception as e:
        log.error("Stage 2 coaching generation failed: %s", e)

    # 5. Cache and return (only cache successful results)
    if coaching:
        await save_coaching(pool, user.email, today, profile, coaching)

    if coaching:
        return CoachingResponse(
            period_start=period_start, period_end=period_end,
            summary=coaching.get("summary"),
            tips=[CoachingTip(**t) for t in coaching.get("tips", [])],
            stats=stats,
            status="ready",
            cached=False,
            generated_at=datetime.utcnow().isoformat(),
        )

    return CoachingResponse(
        period_start=period_start, period_end=period_end,
        stats=stats, status="unavailable",
    )


def _build_stats(profile: dict) -> CoachingStats:
    """Extract CoachingStats from a cached profile dict."""
    convs = profile.get("conversation_summaries", [])
    msg_counts = [c.get("message_count", 0) for c in convs]
    fa = profile.get("file_analysis", {})
    total_reqs = sum(m.get("requests", 0) for m in profile.get("spend_by_model", []))
    return CoachingStats(
        total_requests=total_reqs,
        total_chats=len(convs),
        avg_messages_per_chat=round(sum(msg_counts) / len(msg_counts), 1) if msg_counts else 0.0,
        longest_chat_messages=max(msg_counts) if msg_counts else 0,
        total_file_uploads=fa.get("total_uploads", 0),
        unique_files=fa.get("unique_files", 0),
    )
