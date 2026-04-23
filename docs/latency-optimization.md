# Latency Optimization Guide

Ways to make the AI chatbot respond faster.

---

## 1. Rule-Based Routing

**What is it?**
For clear cases, skip the AI router and decide which agent to use using simple code rules — keyword matching, session state, or UI signals.

**Why it helps**
The router (`classify_multi_intent`) makes one full AI call just to pick the right agent. If we already know the answer from context or keywords, this call is unnecessary.

**Examples**

- User clicks a "주문 조회" button on the UI → the intent is clearly TRANSACTION. The frontend can send `domain_hint: TRANSACTION` in the request → backend skips the router entirely.
- User types "환불하고 싶어요" → the word "환불" is a clear SUPPORT keyword → route directly to SUPPORT agent, no AI call.
- User previously said they want to book an appointment, and now types "225/45R18 벤투스" → the system already knows: find the product first (DISCOVERY), then book it (TRANSACTION) → no need to ask the AI router.

---

## 2. Using a Smaller LLM for Simple Tasks

**What is it?**
Use a smaller, faster AI model for tasks that do not need complex reasoning.

**Why it helps**
Smaller models respond faster. Not every step needs a powerful model.

**Example**
The router only needs to pick one of 4 domains (DISCOVERY, TRANSACTION, SUPPORT, LEADING). The QC agent only checks and rewrites a short answer. Both are simple tasks — a smaller model handles them just as well but responds faster than the full-size model used everywhere today.

---

## 3. Prompt Caching

**What is it?**
OpenAI saves (caches) the beginning part of a prompt if it is the same across requests. If the beginning never changes, OpenAI reuses the cached version and responds faster.

**Why it helps**
Our agent system prompts are very long. If OpenAI can cache them, each request processes faster and costs less.

**Example**
Currently, the system prompt starts with: `"Current time: 2026-04-23 11:42:05 — You are TStation AI..."`. Because the timestamp changes every second, OpenAI never sees the same beginning → cache is never used. Fix: move the current time to the end of the user message so the system prompt stays stable and gets cached after the first request.

---

## 4. Shared Backend Client + ContextVar Token

**What is it?**
Reuse one shared backend HTTP client instead of creating a new client for each tool call. Store the current backend token in a request-local `ContextVar` instead of a shared global variable.

**Why it helps**
Reusing the client avoids repeated connection setup and makes backend requests faster. Using `ContextVar` also prevents token mix-ups between concurrent users while keeping the fast shared client design safe.

**Example**
Without sharing: each tool call (e.g. `get_final_price_tool`, `search_product_tool`) creates its own HTTP client → repeated TCP handshakes and auth setup per call. With a shared client: one client is created once, all tool calls reuse it → only one connection setup per server lifecycle.

---

## 5. Tool Call Parallelization

**What is it?**
Run independent tool calls at the same time instead of one after another.

**Why it helps**
If multiple backend calls do not depend on each other, parallel execution can reduce total waiting time from the sum of all calls to roughly the duration of the slowest one.

**Example**
User asks: "벤투스 S1 evo3 가격이랑 재고 알려줘" → the agent needs to call `get_final_price_tool` AND `get_logistics_inventory_tool`. These two calls do not depend on each other → run them in parallel → total wait time = slowest call, not both added together.

---

## 6. Tool Result Caching

**What is it?**
Save the result of a tool call (e.g. fetch product price) in Redis. If the same tool is called again with the same input, return the saved result instead of calling the backend again.

**Why it helps**
Each tool call makes an HTTP request to the backend. Calling the same tool twice in one conversation wastes time. Caching avoids the second round-trip.

**Example**
User asks the price of a tire → system calls `get_final_price_tool` → result saved in Redis for 60 seconds. Two messages later, the user asks the same price again → system reads from Redis instead of calling the backend → response is instant.

---

## 7. Reduce Hot-Path Logging

**What is it?**
Reduce or remove large `INFO` logs on the main request path, especially logs that dump full prompts, message histories, or tool payloads.

**Why it helps**
Large logs cost CPU time to serialize, memory to build strings, and I/O time to write them. On a chat system, this happens on every request, so trimming hot-path logs can reduce latency without changing business logic.

**Example**
Currently, some agents log the full message history (including all past conversation turns) on every request as `INFO`. This means building a large string and writing it to disk on every chat turn. Changing these to `DEBUG` level (disabled in production) removes the overhead without losing anything important.

---

## 8. Singleton LLM Instance

**What is it?**
Create the AI model object **once** when the server starts, and reuse it for every request. Do not create a new object for each request.

**Why it helps**
Creating a new object every request wastes time and memory — it reads config, allocates memory, and may reset the HTTP connection. A single shared object only does this setup once.

**Example**
Currently, `classify_multi_intent` creates a new `ChatLiteLLM` object on every chat request. Under 100 concurrent users, 100 separate LLM objects are created at the same time. With a singleton, one object is created at server start and shared — no repeated setup cost.
