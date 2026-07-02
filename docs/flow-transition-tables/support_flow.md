# Support Flow State Transition Table

Purpose: keep support FAQ, policy, troubleshooting, and human escalation from drifting into transaction tools or stale
purchase/order context.

## Invariants

- FAQ/policy/troubleshooting intents use FAQ/RAG first when a grounded answer is available.
- Direct 1:1 escalation is allowed only when the user explicitly asks for 상담원/1:1 문의/접수 or equivalent.
- Owned order/reservation/coupon lookup tools are forbidden for general policy questions unless the current turn asks for
  a personal record.
- Support turns make purchase/stock/store contexts dormant unless the user explicitly resumes them afterward.

## Transition Table

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Next Action | Expected Template |
|---|---|---|---|---|---|---|---|---|
| support | empty | support_faq/general_policy | support topic | topic | `search_faq_hybrid_tool`, `search_faq_rag_tool`, `get_faq_tool` | `quick_order_tool`, `get_orders_of_user_tool`, `get_order_status_tool` unless owned lookup | answer grounded FAQ | `quickReply` |
| support | empty | coupon_registration_policy/coupon_usage_policy | support topic | coupon policy topic | `search_faq_hybrid_tool` | `get_my_coupons_tool`, `get_coupon_applicable_products_tool`, `quick_order_tool` | answer how-to/policy | `quickReply` |
| support | empty | general_cancel_fee_policy/general_card_cancel_timing_policy | policy topic | topic | `search_faq_hybrid_tool` | `get_orders_of_user_tool`, `get_order_status_tool` | answer general policy | `quickReply` |
| support | empty | owned_order_cancel_fee_inquiry | personal order context requested | order reference or owned lookup auth | `get_orders_of_user_tool`, `get_order_status_tool` | `search_faq_hybrid_tool` when owned lookup is required | lookup owned order then answer | `quickReply` |
| support | empty | payment_error_troubleshooting | troubleshooting topic | issue topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_orders_of_user_tool` unless personal lookup requested | FAQ troubleshooting first, fallback CTA | `quickReply` |
| support | empty | tire_quality_warranty_policy/tire_manufacture_date_policy | support topic | topic | `search_faq_hybrid_tool`, `search_faq_rag_tool` | `search_product_tool`, `quick_order_tool` unless product warranty lookup is explicit | answer policy with grounded limits | `quickReply` |
| support | empty | human_escalation | explicit escalation request | escalation category if required | `transfer_to_qna_tool` | FAQ-only tools when direct escalation is explicit | create inquiry handoff | `qnaComplete` |
| support | faq_answered | issue_persists/escalation_requested | prior FAQ active, escalation explicit | inquiry fields if required | `transfer_to_qna_tool` | transaction tools | create fallback inquiry | `qnaComplete` |
| support | purchase_active_parent | support_faq/policy | purchase context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool`, `get_final_price_tool` | answer support; preserve dormant parent only | `quickReply` |
| support | any_active | purchase_resume | explicit purchase resume anchor | purchase missing slots | purchase flow tools | support FAQ tools if not asked | transition back to purchase | purchase expected template |

## Regression Test Reorganization

- Separate general policy from owned-record lookup tests.
- Add tests where support policy questions occur during an active purchase flow and must not execute purchase tools.
- Add escalation tests for both explicit escalation and FAQ-first fallback after troubleshooting.
