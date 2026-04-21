# Coordinator Cleanup

## Goal

After direct JSON output is stable, remove all logic related to UI Template Agent.

## Why Cleanup Is Needed

If the old UI formatting path stays in the code, the system remains harder to maintain.

Possible problems if old code stays:

- two different UI-generation paths
- confusing debug logs
- duplicate data events
- unclear ownership

The final design should have only one UI payload source.

## What To Remove

Remove the whole UI formatting stage from Coordinator.

That includes:

- checks for whether UI Template Agent should run
- code mapper stage
- UI Template Agent fallback stage
- old quickReply fallback that exists only because of the old UI stage

## Files To Remove

- the full `f_ui_template_agent` folder
- `template_mapper.py`

## What To Keep

Keep these parts:

- accumulated tool data
- slot persistence
- tool context save logic
- multi-agent chaining logic
- QC flow
- history sync logic from `assistantResponse`

Important note:

As long as later layers still expect text-style events, BaseAgent should remain the compatibility adapter.
Coordinator should not become the place that understands structured payload details.

## What To Update

### Data event source

Coordinator should now treat Domain Agent output as the final source of `data` events.

The structured payload should arrive through BaseAgent as a normal `data` event.

### Token suppression

Suppression should be based on the actual `data` event or final template type, not on the old UI Template stage.

### Agent names in message sync

When a `data` event contains `assistantResponse`, store it using the real Domain Agent name, not `[UI TEMPLATE AGENT]`.

This change is already needed in Phase 1 because Leading Agent now emits its own payload.

## Final State

After cleanup:

- no UI Template Agent import
- no UI Template Agent execution
- no template mapper usage
- no UI-specific second-stage formatting

Coordinator only orchestrates agents, not extra UI formatting.

The only valid UI payload source is the Domain Agent response.
