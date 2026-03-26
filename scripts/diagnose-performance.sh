#!/usr/bin/env bash
# diagnose-performance.sh — Performance diagnostics for AI Gateway
# Queries LiteLLM's spend log for response time metrics and tests provider latency.
#
# Usage: ./scripts/diagnose-performance.sh [hours]
#   hours: lookback window (default: 24)
#
# Requires: docker, psql access via chat-postgres container

set -euo pipefail

LOOKBACK_HOURS="${1:-24}"
CONTAINER="chat-postgres"
DB="litellm"

# Load credentials from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [[ -f "$ENV_FILE" ]]; then
    POSTGRES_USER=$(grep -oP '^POSTGRES_USER=\K.*' "$ENV_FILE" || echo "postgres")
    LITELLM_MASTER_KEY=$(grep -oP '^LITELLM_MASTER_KEY=\K.*' "$ENV_FILE" || echo "")
else
    echo "WARNING: .env not found, using defaults"
    POSTGRES_USER="postgres"
    LITELLM_MASTER_KEY=""
fi

run_sql() {
    docker exec "$CONTAINER" psql -U "$POSTGRES_USER" -d "$DB" -t -A -c "$1" 2>/dev/null
}

echo "=============================================="
echo " AI Gateway Performance Report"
echo " Lookback: ${LOOKBACK_HOURS}h | $(date '+%Y-%m-%d %H:%M %Z')"
echo "=============================================="

# ---------- 1. Request volume and response times by model ----------
# response_time = total elapsed; ttft = time to first token (completionStartTime)
echo ""
echo "--- Response Time by Model (last ${LOOKBACK_HOURS}h) ---"
echo ""
printf "%-32s %6s %8s %8s %8s %8s %8s\n" "MODEL" "COUNT" "AVG(s)" "P50(s)" "P95(s)" "P99(s)" "TTFT(s)"
printf "%-32s %6s %8s %8s %8s %8s %8s\n" "-----" "-----" "------" "------" "------" "------" "-------"

run_sql "
SELECT
    model_group,
    COUNT(*) AS cnt,
    ROUND(AVG(EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")))::numeric, 2) AS avg_rt,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")))::numeric, 2) AS p50,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")))::numeric, 2) AS p95,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")))::numeric, 2) AS p99,
    ROUND(AVG(EXTRACT(EPOCH FROM (\"completionStartTime\" - \"startTime\"))) FILTER (WHERE \"completionStartTime\" IS NOT NULL)::numeric, 2) AS avg_ttft
FROM \"LiteLLM_SpendLogs\"
WHERE \"startTime\" > NOW() - INTERVAL '${LOOKBACK_HOURS} hours'
  AND status = 'success'
  AND \"endTime\" > \"startTime\"
GROUP BY model_group
ORDER BY cnt DESC;
" | while IFS='|' read -r model cnt avg p50 p95 p99 ttft; do
    printf "%-32s %6s %8s %8s %8s %8s %8s\n" "$model" "$cnt" "$avg" "$p50" "$p95" "$p99" "${ttft:--}"
done

# ---------- 2. Slowest individual requests ----------
echo ""
echo "--- Top 10 Slowest Requests (last ${LOOKBACK_HOURS}h) ---"
echo ""
printf "%-32s %8s %8s %10s %-18s\n" "MODEL" "TOTAL(s)" "TTFT(s)" "TOKENS" "TIMESTAMP"
printf "%-32s %8s %8s %10s %-18s\n" "-----" "--------" "-------" "------" "---------"

run_sql "
SELECT
    model_group,
    ROUND(EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\"))::numeric, 2) AS total_s,
    ROUND(EXTRACT(EPOCH FROM (\"completionStartTime\" - \"startTime\"))::numeric, 2) AS ttft_s,
    COALESCE(total_tokens, 0),
    TO_CHAR(\"startTime\", 'MM-DD HH24:MI:SS')
FROM \"LiteLLM_SpendLogs\"
WHERE \"startTime\" > NOW() - INTERVAL '${LOOKBACK_HOURS} hours'
  AND status = 'success'
  AND \"endTime\" > \"startTime\"
ORDER BY EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")) DESC
LIMIT 10;
" | while IFS='|' read -r model total ttft tokens ts; do
    printf "%-32s %8s %8s %10s %-18s\n" "$model" "$total" "${ttft:--}" "$tokens" "$ts"
done

# ---------- 3. Error/timeout rate ----------
echo ""
echo "--- Error & Timeout Rate (last ${LOOKBACK_HOURS}h) ---"
echo ""
printf "%-32s %6s %6s %8s\n" "MODEL" "OK" "FAIL" "FAIL%"
printf "%-32s %6s %6s %8s\n" "-----" "----" "----" "-----"

run_sql "
SELECT
    model_group,
    COUNT(*) FILTER (WHERE status = 'success') AS ok,
    COUNT(*) FILTER (WHERE status != 'success') AS fail,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status != 'success') / NULLIF(COUNT(*), 0),
        1
    ) AS fail_pct
FROM \"LiteLLM_SpendLogs\"
WHERE \"startTime\" > NOW() - INTERVAL '${LOOKBACK_HOURS} hours'
GROUP BY model_group
ORDER BY fail DESC, ok DESC;
" | while IFS='|' read -r model ok fail pct; do
    printf "%-32s %6s %6s %7s%%\n" "$model" "$ok" "$fail" "$pct"
done

# ---------- 4. Hourly request volume (trends) ----------
echo ""
echo "--- Hourly Request Volume (last ${LOOKBACK_HOURS}h) ---"
echo ""
printf "%-16s %6s %8s %8s\n" "HOUR (LOCAL)" "COUNT" "AVG(s)" "ERRORS"
printf "%-16s %6s %8s %8s\n" "----------" "-----" "------" "------"

run_sql "
SELECT
    TO_CHAR(DATE_TRUNC('hour', \"startTime\" AT TIME ZONE 'America/New_York'), 'MM-DD HH24:00') AS hour,
    COUNT(*) AS cnt,
    ROUND(AVG(EXTRACT(EPOCH FROM (\"endTime\" - \"startTime\")))::numeric, 2) AS avg_rt,
    COUNT(*) FILTER (WHERE status != 'success') AS errs
FROM \"LiteLLM_SpendLogs\"
WHERE \"startTime\" > NOW() - INTERVAL '${LOOKBACK_HOURS} hours'
GROUP BY DATE_TRUNC('hour', \"startTime\" AT TIME ZONE 'America/New_York')
ORDER BY DATE_TRUNC('hour', \"startTime\" AT TIME ZONE 'America/New_York') DESC;
" | while IFS='|' read -r hour cnt avg_rt errs; do
    printf "%-16s %6s %8s %8s\n" "$hour" "$cnt" "$avg_rt" "$errs"
done

# ---------- 5. Container resource usage ----------
echo ""
echo "--- Container Resource Usage ---"
echo ""
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}" \
    chat-postgres chat-redis chat-litellm chat-openwebui chat-nginx chat-dashboard 2>/dev/null || \
    echo "(Could not read docker stats — are containers running?)"

# ---------- 6. Direct provider latency test ----------
echo ""
echo "--- Direct Provider Latency (non-streaming round-trip via LiteLLM) ---"
echo "(Sends a minimal prompt to each provider; measures wall-clock time)"
echo ""

if [[ -z "$LITELLM_MASTER_KEY" ]]; then
    echo "Skipping — LITELLM_MASTER_KEY not found in .env"
else
    test_model() {
        local model="$1"
        local start end elapsed http_code

        start=$(date +%s%N)
        http_code=$(curl -s -o /dev/null -w "%{http_code}" \
            --max-time 30 \
            -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
            -H "Content-Type: application/json" \
            -d "{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"Say hi\"}], \"max_tokens\": 5}" \
            http://localhost:4000/v1/chat/completions 2>/dev/null) || http_code="timeout"
        end=$(date +%s%N)

        elapsed=$(( (end - start) / 1000000 ))
        printf "  %-32s %6sms  (HTTP %s)\n" "$model" "$elapsed" "$http_code"
    }

    test_model "claude-haiku-4-5"
    test_model "chatgpt-5-nano"
    test_model "gemini-3-flash-preview"
    test_model "copilot"
fi

echo ""
echo "=============================================="
echo " Tips:"
echo "  - High P95/P99 with normal AVG → occasional slow queries (likely thinking models)"
echo "  - TTFT >> 0 → model is thinking before first token (expected for thinking variants)"
echo "  - High AVG across all models → proxy/DB bottleneck (check container resources above)"
echo "  - High error rate on one model → provider issue (check cooldown/retries)"
echo "  - nginx timing: docker logs chat-nginx 2>&1 | grep 'urt=' | sort -t= -k3 -rn | head"
echo "=============================================="
