# Migration Strategy

## Goal

Move from the old design to the new direct JSON design safely.

The final goal is:

- no UI Template Agent in the main flow
- Domain Agent returns the final JSON payload directly

## Rollout Order

1. shared schema models
2. BaseAgent structured-output validation and adapter logic
3. Leading Agent
4. Discovery Agent
5. Support Agent
6. Transaction Agent
7. Coordinator cleanup

## Why This Order

This order reduces risk:

- Leading is the simplest and proves the BaseAgent adapter works
- Discovery is prioritized next because it is the most frequently used domain and delivers the highest user impact; it is migrated in sub-phases (2A–2E) so each template can be tested before adding the next
- Support is still small and can reuse the patterns validated by Discovery
- Transaction is last because `preOrder` is the most complex case

## Recommended Process Per Agent

For each agent:

1. update prompt rules
2. verify correct template selection
3. verify schema validation
4. verify FE rendering
5. verify QC still works

Only then move to the next agent.

## Suggested Phases

### Phase 0

Prepare shared Pydantic models and BaseAgent adapter logic.

Goal of this phase:

- schema definitions are stable
- BaseAgent can validate structured payloads
- BaseAgent can emit `token`, `message`, and `data` from one structured payload
- validation errors are visible in logs

### Phase 1

Migrate Leading Agent first because it is simplest.

Success check:

- every Leading turn returns one `quickReply`
- BaseAgent rebuilds the text-style flow from `assistantResponse`
- UI Template Agent is skipped for Leading turns

### Phase 2

Migrate Discovery Agent next, in five sub-phases.

| Sub-phase | Scope | Success check |
|-----------|-------|---------------|
| 2A | Add Pydantic schemas for `product`, `listCar`, `cheapestProduct`, `previewYoutube`; expose Discovery Union | Pydantic validates JSON for all 4 templates |
| 2B | Discovery + `quickReply` only via `OUTPUT_TEMPLATE` | Compatibility / no-result / single-car / description turns return `quickReply`; UI Template Agent skipped |
| 2C | Add `product` to the Union | Search and recommendation turns return `product`; empty results fall back to `quickReply` |
| 2D | Add `listCar` to the Union | Multi-car turns return `listCar`; single-car turns auto-select and return `quickReply` |
| 2E | Add `cheapestProduct` and `previewYoutube` | Discount comparison returns `cheapestProduct`; tire video search returns `previewYoutube` |

All Discovery sub-phases must keep:
- `source_domain = discovery` on every emitted `data` event
- exactly one template per turn
- list templates within max 5 items

### Phase 3

Migrate Support Agent.

Success check:

- FAQ turns return `quickReply`
- QnA transfer turns return `qnaComplete`

### Phase 4

Migrate Transaction Agent last because `preOrder` is the most complex case.

Success check:

- coupon turns return `voucher`
- store turns return `location`
- schedule turns return `datepick`
- preview turns return `preOrder`
- final confirmation returns `orderComplete`

### Phase 5

Remove UI Template Agent code and template mapper after stability is proven.

## Testing Focus

Each phase should validate:

- exactly one template per turn
- correct template name
- correct field names and types
- no broken FE rendering
- no missing `data` event

## Rollback Principle

If direct JSON output is not stable enough, rollback should restore the previous release version.

Do not keep two permanent UI-generation paths in the final design.

Temporary rollback is acceptable during migration, but the target architecture has only one path.

That one path is:

- Domain Agent returns the final structured payload
- BaseAgent validates it and adapts it into the runtime events

## Final Release Condition

The migration is complete only when:

- all agents return direct JSON correctly
- FE renders correctly with no schema change
- UI Template Agent is no longer used
- old UI formatting code is removed
