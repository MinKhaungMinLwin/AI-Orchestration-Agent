# Latency Optimization Guide

Ways to make the AI chatbot respond faster.

---

## 1. Rule-Based Routing

**What is it?**
For clear cases, skip the AI router and decide which agent to use using simple code rules — keyword matching, session state, or UI signals.

**Why it helps**
The router (`classify_multi_intent`) makes one full AI call just to pick the right agent. If we already know the answer from context or keywords, this call is unnecessary.

---

## 2. Using a Smaller LLM for Simple Tasks

**What is it?**
Use a smaller, faster AI model for tasks that do not need complex reasoning.

**Why it helps**
Smaller models respond faster. Not every step needs a powerful model.

---

## 3. Prompt Caching

**What is it?**
OpenAI saves (caches) the beginning part of a prompt if it is the same across requests. If the beginning never changes, OpenAI reuses the cached version and responds faster.

**Why it helps**
Our agent system prompts are very long. If OpenAI can cache them, each request processes faster and costs less.

---

## 4. Shared Backend Client + ContextVar Token

**What is it?**
Reuse one shared backend HTTP client instead of creating a new client for each tool call. Store the current backend token in a request-local `ContextVar` instead of a shared global variable.

**Why it helps**
Reusing the client avoids repeated connection setup and makes backend requests faster. Using `ContextVar` also prevents token mix-ups between concurrent users while keeping the fast shared client design safe.

---

## 5. Tool Call Parallelization

**What is it?**
Run independent tool calls at the same time instead of one after another.

**Why it helps**
If multiple backend calls do not depend on each other, parallel execution can reduce total waiting time from the sum of all calls to roughly the duration of the slowest one.

---

## 6. Tool Result Caching

**What is it?**
Save the result of a tool call (e.g. fetch product price) in Redis. If the same tool is called again with the same input, return the saved result instead of calling the backend again.

**Why it helps**
Each tool call makes an HTTP request to the backend. Calling the same tool twice in one conversation wastes time. Caching avoids the second round-trip.

---

## 7. Reduce Hot-Path Logging

**What is it?**
Reduce or remove large `INFO` logs on the main request path, especially logs that dump full prompts, message histories, or tool payloads.

**Why it helps**
Large logs cost CPU time to serialize, memory to build strings, and I/O time to write them. On a chat system, this happens on every request, so trimming hot-path logs can reduce latency without changing business logic.

---

## 8. Singleton LLM Instance

**What is it?**
Create the AI model object **once** when the server starts, and reuse it for every request. Do not create a new object for each request.

**Why it helps**
Creating a new object every request wastes time and memory — it reads config, allocates memory, and may reset the HTTP connection. A single shared object only does this setup once.
