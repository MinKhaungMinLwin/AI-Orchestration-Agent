# Latency Optimization Guide

Ways to make the AI chatbot respond faster.

---

## 1. Rule-Based Routing ✅ Done but disable now

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

## 3. Prompt Caching ✅ Done

**What is it?**
OpenAI saves (caches) the beginning part of a prompt if it is the same across requests. If the beginning never changes, OpenAI reuses the cached version and responds faster.

**Why it helps**
Our agent system prompts are very long. If OpenAI can cache them, each request processes faster and costs less.

---

## 4. Tool Result Caching ✅ Done

**What is it?**
Save the result of a tool call (e.g. fetch product price) in Redis. If the same tool is called again with the same input, return the saved result instead of calling the backend again.

**Why it helps**
Each tool call makes an HTTP request to the backend. Calling the same tool twice in one conversation wastes time. Caching avoids the second round-trip.

---

## 5. Singleton LLM Instance ✅ Done

**What is it?**
Create the AI model object **once** when the server starts, and reuse it for every request. Do not create a new object for each request.

**Why it helps**
Creating a new object every request wastes time and memory — it reads config, allocates memory, and may reset the HTTP connection. A single shared object only does this setup once.
