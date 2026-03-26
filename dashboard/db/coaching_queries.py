"""Database queries for the AI coaching feature.

Queries both the litellm and openwebui databases to extract
usage profiles for the two-stage coaching pipeline.
"""

import json
from datetime import datetime, timedelta

import asyncpg

from db.queries import get_billing_period_dates


# ---------------------------------------------------------------------------
# LiteLLM database queries (spend / token data)
# ---------------------------------------------------------------------------

async def get_spend_profile(
    pool: asyncpg.Pool, user_email: str,
) -> list[dict]:
    """Aggregated spend by model for the 7-day billing window."""
    start, end = get_billing_period_dates()
    query = """
        SELECT
            model,
            COUNT(*)                                     AS request_count,
            COALESCE(SUM(spend), 0)                      AS total_spend,
            COALESCE(SUM(prompt_tokens), 0)              AS prompt_tokens,
            COALESCE(SUM(completion_tokens), 0)          AS completion_tokens,
            ROUND(COALESCE(AVG(prompt_tokens), 0))       AS avg_prompt_tokens,
            ROUND(COALESCE(AVG(completion_tokens), 0))   AS avg_completion_tokens,
            MAX(prompt_tokens)                           AS max_prompt_tokens
        FROM "LiteLLM_SpendLogs"
        WHERE end_user = $1
          AND "startTime" >= $2 AND "startTime" < $3
        GROUP BY model
        ORDER BY total_spend DESC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_email, start, end)
    return [dict(r) for r in rows]


async def get_request_timeline(
    pool: asyncpg.Pool, user_email: str,
) -> list[dict]:
    """Per-request timeline for session / context-escalation detection."""
    start, end = get_billing_period_dates()
    query = """
        SELECT "startTime", model, prompt_tokens, completion_tokens, spend
        FROM "LiteLLM_SpendLogs"
        WHERE end_user = $1
          AND "startTime" >= $2 AND "startTime" < $3
        ORDER BY "startTime"
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_email, start, end)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# OpenWebUI database queries (chat messages, file uploads)
# ---------------------------------------------------------------------------

def _epoch_seven_days_ago() -> int:
    """Return Unix epoch (seconds) for 7 days ago."""
    return int((datetime.utcnow() - timedelta(days=7)).timestamp())


async def get_chat_conversations(
    pool: asyncpg.Pool | None, user_id: str,
) -> list[dict] | None:
    """Get recent chats with all user messages for summarization.

    Uses the normalized chat + chat_message tables (not the chat JSON blob).
    Returns a list of chat dicts with title, message_count, models, and
    user message texts (truncated to 300 chars each).
    """
    if pool is None:
        return None

    since = _epoch_seven_days_ago()

    # Step 1: Get recent chat metadata
    chats_query = """
        SELECT c.id, c.title, c.created_at, c.updated_at
        FROM chat c
        WHERE c.user_id = $1
          AND c.updated_at >= $2
        ORDER BY c.updated_at DESC
        LIMIT 30
    """
    async with pool.acquire() as conn:
        chat_rows = await conn.fetch(chats_query, user_id, since)

    if not chat_rows:
        return []

    chat_ids = [r["id"] for r in chat_rows]

    # Step 2: Get message counts + models per chat
    counts_query = """
        SELECT
            chat_id,
            COUNT(*) AS total_messages,
            COUNT(*) FILTER (WHERE role = 'user') AS user_messages,
            COUNT(*) FILTER (WHERE role = 'assistant') AS assistant_messages,
            array_agg(DISTINCT model_id) FILTER (WHERE model_id IS NOT NULL) AS models_used
        FROM chat_message
        WHERE chat_id = ANY($1)
        GROUP BY chat_id
    """

    # Step 3: Get user message texts (truncated)
    messages_query = """
        SELECT
            chat_id,
            LEFT(content #>> '{}', 300) AS text
        FROM chat_message
        WHERE chat_id = ANY($1)
          AND role = 'user'
          AND content IS NOT NULL
        ORDER BY created_at
    """

    async with pool.acquire() as conn:
        count_rows = await conn.fetch(counts_query, chat_ids)
        msg_rows = await conn.fetch(messages_query, chat_ids)

    # Index counts by chat_id
    counts_by_chat: dict[str, dict] = {}
    for r in count_rows:
        counts_by_chat[r["chat_id"]] = dict(r)

    # Group user messages by chat_id
    msgs_by_chat: dict[str, list[str]] = {}
    for r in msg_rows:
        msgs_by_chat.setdefault(r["chat_id"], []).append(r["text"] or "")

    # Assemble results
    results = []
    for cr in chat_rows:
        cid = cr["id"]
        counts = counts_by_chat.get(cid, {})
        results.append({
            "id": cid,
            "title": cr["title"] or "Untitled",
            "created_at": cr["created_at"],
            "updated_at": cr["updated_at"],
            "total_messages": counts.get("total_messages", 0),
            "user_messages": counts.get("user_messages", 0),
            "assistant_messages": counts.get("assistant_messages", 0),
            "models_used": counts.get("models_used") or [],
            "user_message_texts": msgs_by_chat.get(cid, []),
        })
    return results


async def get_file_uploads(
    pool: asyncpg.Pool | None, user_id: str,
) -> list[dict] | None:
    """Get file upload details for recent chats.

    Returns file info with chat context: which chat, which message position,
    and how many messages came after (indicating repeated context re-sends).
    """
    if pool is None:
        return None

    since = _epoch_seven_days_ago()

    query = """
        SELECT
            cf.chat_id,
            c.title AS chat_title,
            f.filename,
            cf.created_at AS upload_time,
            -- Count total messages in this chat
            (SELECT COUNT(*) FROM chat_message cm WHERE cm.chat_id = cf.chat_id) AS chat_total_messages,
            -- Count messages created after this file was uploaded
            (SELECT COUNT(*) FROM chat_message cm
             WHERE cm.chat_id = cf.chat_id AND cm.created_at > cf.created_at) AS messages_after_upload
        FROM chat_file cf
        JOIN file f ON cf.file_id = f.id
        JOIN chat c ON cf.chat_id = c.id
        WHERE cf.user_id = $1
          AND cf.created_at >= $2
        ORDER BY cf.created_at
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id, since)

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Coaching cache (litellm database)
# ---------------------------------------------------------------------------

async def get_cached_coaching(
    pool: asyncpg.Pool, user_email: str, cache_date: str,
) -> dict | None:
    """Retrieve cached coaching for today. Returns None on cache miss."""
    query = """
        SELECT profile, coaching, generated_at
        FROM dashboard_coaching_cache
        WHERE user_email = $1 AND cache_date = $2
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_email, cache_date)

    if row and row["coaching"]:
        return {
            "profile": json.loads(row["profile"]) if isinstance(row["profile"], str) else row["profile"],
            "coaching": json.loads(row["coaching"]) if isinstance(row["coaching"], str) else row["coaching"],
            "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        }
    return None


async def save_coaching(
    pool: asyncpg.Pool,
    user_email: str,
    cache_date: str,
    profile: dict,
    coaching: dict | None,
) -> None:
    """Save coaching result to cache. Upserts on conflict."""
    query = """
        INSERT INTO dashboard_coaching_cache (user_email, cache_date, profile, coaching)
        VALUES ($1, $2, $3::json, $4::json)
        ON CONFLICT (user_email, cache_date) DO UPDATE
        SET profile = EXCLUDED.profile,
            coaching = EXCLUDED.coaching,
            generated_at = NOW()
    """
    async with pool.acquire() as conn:
        await conn.execute(
            query,
            user_email,
            cache_date,
            json.dumps(profile),
            json.dumps(coaching) if coaching else None,
        )
