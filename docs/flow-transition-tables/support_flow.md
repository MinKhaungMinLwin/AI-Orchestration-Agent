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

| Flow | Current State | Current-Turn Intent | Active Context | Required Slots | Allowed Tools | Forbidden Tools | Allowed Templates/Actions | Forbidden Templates/Actions | Next Tool | Next Template/Action | Expected Persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | empty | support_faq/general_policy | support topic | topic | `search_faq_hybrid_tool`, `search_faq_rag_tool`, `get_faq_tool` | `quick_order_tool`, `get_orders_of_user_tool`, `get_order_status_tool` unless owned lookup | `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete`, `qnaComplete` unless escalation explicit | FAQ/RAG tool | `quickReply` | persist support topic; transaction contexts remain dormant |
| support | empty | coupon_registration_policy/coupon_usage_policy | support topic | coupon policy topic | `search_faq_hybrid_tool` | `get_my_coupons_tool`, `get_coupon_applicable_products_tool`, `quick_order_tool` | `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | persist coupon policy topic only |
| support | empty | general_cancel_fee_policy/general_card_cancel_timing_policy | policy topic | topic | `search_faq_hybrid_tool` | `get_orders_of_user_tool`, `get_order_status_tool`, `quick_order_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete`, `qnaComplete` unless escalation explicit | `search_faq_hybrid_tool` | `quickReply` | persist general policy topic without owned order lookup state |
| support | empty | owned_order_cancel_fee_inquiry | personal order context requested | order reference or owned lookup auth | `get_orders_of_user_tool`, `get_order_status_tool` | `search_faq_hybrid_tool` when owned lookup is required, `quick_order_tool` | `quickReply` | `datepick`, `preOrder`, `orderComplete` | owned order lookup tool | `quickReply` | persist owned lookup result under support/reservation management, not purchase |
| support | empty | payment_error_troubleshooting | troubleshooting topic | issue topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_orders_of_user_tool` unless personal lookup requested | `quickReply` | `datepick`, `preOrder`, `orderComplete`, `qnaComplete` unless escalation explicit | `search_faq_hybrid_tool` | `quickReply` | persist troubleshooting topic and FAQ result |
| support | empty | tire_quality_warranty_policy/tire_manufacture_date_policy | support topic | topic | `search_faq_hybrid_tool`, `search_faq_rag_tool` | `search_product_tool`, `quick_order_tool` unless product warranty lookup is explicit | `quickReply` | `product` unless product lookup explicit, `location`, `datepick`, `preOrder`, `orderComplete` | FAQ/RAG tool | `quickReply` | persist warranty/manufacture-date topic only |
| support | empty | human_escalation | explicit escalation request | escalation category if required | `transfer_to_qna_tool` | FAQ-only tools when direct escalation is explicit, transaction tools | `qnaComplete`, `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `transfer_to_qna_tool` | `qnaComplete` | persist escalation result; keep transaction contexts dormant |
| support | faq_answered | issue_persists/escalation_requested | prior FAQ active, escalation explicit | inquiry fields if required | `transfer_to_qna_tool` | transaction tools | `qnaComplete`, `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `transfer_to_qna_tool` | `qnaComplete` | persist escalation handoff linked to prior support topic |
| support | purchase_active_parent | support_faq/policy | purchase context dormant | support topic | `search_faq_hybrid_tool` | `quick_order_tool`, `get_store_schedule_tool`, `get_final_price_tool` | `quickReply` | `product`, `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | preserve parent purchase only as dormant; weak metadata cannot resume it |
| support | stock_or_store_active_parent | support_faq/policy | stock/store context dormant | support topic | `search_faq_hybrid_tool` | stock/store/order tools | `quickReply` | `location`, `datepick`, `preOrder`, `orderComplete` | `search_faq_hybrid_tool` | `quickReply` | preserve stock/store as dormant; no booking/order action without explicit resume |
| support | any_active | purchase_resume | explicit purchase resume anchor | purchase missing slots | purchase flow tools | support FAQ tools if not asked | purchase templates/actions allowed by parent contract | support-only templates when purchase resumes | parent purchase next tool | parent purchase next template/action | resume purchase only with compatible current-turn anchor |

## Regression Test Reorganization

- Separate general policy from owned-record lookup tests.
- Add tests where support policy questions occur during active purchase, stock, or store flows and must not execute transaction tools.
- Add escalation tests for both explicit escalation and FAQ-first fallback after troubleshooting.
