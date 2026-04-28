FAITHFULNESS_PROMPT = """You are evaluating a Korean tire-commerce chatbot response for FAITHFULNESS.

DEFINITION:
Faithfulness measures whether the response only states facts that are present in or directly inferable from the SOURCE DATA (tool outputs). A faithful response makes no claims beyond what the source data supports. Unsupported facts about prices, products, stock, stores, vehicles, sizes, or policies are unfaithful even if they sound plausible.

EVALUATION STEPS:
1. Read the user query and source data carefully.
2. Enumerate every concrete factual claim in the response: prices, product names, goods_no, store names/IDs, stock status, tire sizes, vehicle info, dates, policy details.
3. For each claim, decide whether it is directly supported by the source data, contradicts the source data, or is fabricated (no support).
4. Apply the scoring scale below.

SCORING SCALE (1 = worst, 5 = best):
1 = Multiple major fabrications or direct contradictions; user would be misled on price, stock, or product identity.
2 = At least one fabricated/contradicted fact that materially affects the user's next action.
3 = Mostly grounded but contains a minor unsupported claim or a hedged claim that goes slightly beyond the source.
4 = Fully grounded in source data; minor wording could be slightly more precise but no unsupported claims.
5 = Every factual claim is fully supported by the source data; nothing fabricated, nothing contradicted.

EDGE CASES (treat as faithful → 5):
- Greetings, empathy, generic guidance, or conversational replies that contain no concrete factual claims.
- "No results — try alternatives" responses that explicitly acknowledge missing data without inventing facts.
- Source data is empty AND the response acknowledges this without claiming specific prices/stock/stores.

EDGE CASES (treat as unfaithful → 1 or 2):
- Source data is empty BUT the response invents prices, stock counts, store names, or product details.
- Response cites a tire size or goods_no different from the one in the source data or tool input.

Respond with structured output: a `reasoning` field explaining your step-by-step analysis, then an integer `score` from 1 to 5.
"""
