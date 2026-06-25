# T-Station Langfuse Trace Access

For future T-Station session investigations, use Langfuse first with the dev container's internal Langfuse endpoint and keys.

Do not start with local `uv run python` Langfuse SDK calls from the workspace.
They often fail under sandboxed network restrictions and waste time.
Default path:
- first use SSH into the dev host
- then query Langfuse from inside `tstation-agent-dev-tstation-ai-1`
- only fall back to local SDK access if explicitly needed and network access is already available

## Known Working Method

1. Read Langfuse env from the dev AI container if needed:

   ```bash
   ssh -i ~/hankooktire.pem ubuntu@172.28.1.156 "cd ~/tstation-agent-dev && docker exec tstation-agent-dev-tstation-ai-1 env | grep LANGFUSE"
   ```

2. Query traces by session ID from inside the AI container. Prefer `$LANGFUSE_HOST` over hard-coded hosts:

   ```bash
   ssh -i ~/hankooktire.pem ubuntu@172.28.1.156 "docker exec tstation-agent-dev-tstation-ai-1 sh -lc 'curl -sS --max-time 15 -u \"\$LANGFUSE_PUBLIC_KEY:\$LANGFUSE_SECRET_KEY\" \"\$LANGFUSE_HOST/api/public/traces?sessionId=<SESSION_ID>&limit=30\"'"
   ```

3. Pick the final user-visible trace from the trace list. Do not assume the newest trace is the correct one. Compare:

   - `timestamp`
   - `input` / `output`
   - `metadata.final_status`
   - `metadata.final_template`
   - `metadata.called_tools`
   - `metadata.assistant_response_source`
   - `metadata.turn_contract`

4. Query observations by trace ID:

   ```bash
   ssh -i ~/hankooktire.pem ubuntu@172.28.1.156 "docker exec tstation-agent-dev-tstation-ai-1 sh -lc 'curl -sS --max-time 15 -u \"\$LANGFUSE_PUBLIC_KEY:\$LANGFUSE_SECRET_KEY\" \"\$LANGFUSE_HOST/api/public/observations?traceId=<TRACE_ID>&limit=100\"'"
   ```

5. If the JSON is too large, cap output locally inside the container command:

   ```bash
   ssh -i ~/hankooktire.pem ubuntu@172.28.1.156 "docker exec tstation-agent-dev-tstation-ai-1 sh -lc 'curl -sS --max-time 15 -u \"\$LANGFUSE_PUBLIC_KEY:\$LANGFUSE_SECRET_KEY\" \"\$LANGFUSE_HOST/api/public/observations?traceId=<TRACE_ID>&limit=100\" | head -c 100000'"
   ```

## Quoting Notes

- Escape `$` as `\$` inside the outer SSH command so `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` expand inside the container, not locally.
- If you forget this, the local shell expands empty env vars and `curl` may fail with `URL using bad/illegal format or missing URL`.

## Useful Fields To Inspect

- trace `metadata.final_status`
- `metadata.final_template`
- `metadata.called_tools`
- `metadata.turn_contract`
- `metadata.turn_contract.domain`
- `metadata.turn_contract.intent`
- `metadata.turn_contract.action_mode`
- `metadata.turn_contract.context_state`
- `metadata.turn_contract.execution_plan`
- `metadata.turn_contract.override_applied`
- `metadata.turn_contract.override_reason`
- `metadata.turn_contract.override_blocked`
- `metadata.turn_contract.blocked_override_reason`
- `metadata.contract_violations` and `metadata.hard_contract_violations`
- router/model observation output: `domains`, `execution_plan`, `policy_intent`, `agent_prompt_profile`, `planner_confidence`
- agent observation output: `tools_called`, `data_event_emitted`, final response/template
- model observation messages, especially tool calls and tool outputs
- latency fields: `latency_ms`, `latency_first_visible_ms`, `latency_agent_pre_tool_think_ms`, `latency_agent_post_tool_output_ms`

## Recent Verified Trace Pattern

- Session `d59c69ce-19c4-4cd9-920b-84a7fcd17bab`
- Trace `1735d0c8e34c49a9bd6aa2af01c0528b`
- Session trace query showed the user-visible answer and metadata.
- Observation query showed router output had `policy_intent=store_attribute_inquiry`, `store_attribute_store_name=티스테이션 정자점`, and `agent_prompt_profile=transaction_store`, but final route stayed `support`.
- Agent observation confirmed the support agent called only `search_faq_hybrid_tool`.
- That delta identified the root cause as route/contract normalization, not the store tool itself.

## Observed Issue Example

- Session `46bc4382-6d4f-4088-8199-7f5b5a9600fd`
- Trace `139c7aadaffc40bd8b78ff0deadf3b5a`
- Tools called: `search_place_tool`, `get_nearby_stores_tool`
- Missing constraints in tool call: EV/service filter and Sunday availability; only landmark coordinates and `limit=5` were applied.
