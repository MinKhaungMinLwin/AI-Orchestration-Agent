http://54.180.189.87/api/tstation/messages/actions/quick-order

payload
{
"session_id": "b39df795-4a56-443a-a818-37628eb4aa68",
"message_id": "quick-order-1783523498385",
"action": "quick_order_execute",
"payload": {
"goodsNo": "G000000310120",
"goodsId": "G000000310120",
"ordQty": 3,
"shopId": "F07780",
"requestedCalDay": "20260709",
"rsvHour": "09",
"carNo": null,
"carLncCd": null,
"paymentAmount": 402600,
"productName": "벤투스 S2 AS",
"tireSize": null,
"storeName": "티스테이션 서초점",
"bookingDateTime": "2026년 07월 09일 09:00",
"mbrCarRegSeq": null
},
"stream": true
}

response:

data: {"session_id": "b39df795-4a56-443a-a818-37628eb4aa68", "message_id": "7707aa87-88c7-4880-971e-533ef58c760a", "role": "user", "content": "주문하기", "created_at": "2026-07-08 15:11:38", "stream_started": true}

data: {"type": "agent_flow", "agent": "[응답 생성 중]", "status": "processing"}

data: {"type": "sub-agent", "agent": "[TRANSACTION AGENT]", "status": "start"}

data: {"type": "status", "status": "tool_start", "tool": "quick_order_tool", "display_name": "주문서 생성 중...", "source_domain": "transaction"}

data: {"type": "agent_flow", "agent": "[Quick Shopping AF]", "agent_class": "Transaction Agent", "status": "success", "source_domain": "transaction"}

data: {"type": "tool", "input": {"goods_no": "G000000310120", "ord_qty": 3, "shop_id": "F07780", "rsv_date": "20260709", "rsv_hour": "09"}, "output": "{\"status\": \"success\", \"http_status\": 200, \"data\": {\"result\": false, \"message\": \"로그인이 필요합니다.\", \"drtPurYn\": null, \"data\": null}}", "node": "tools", "tool": "quick_order_tool", "source_domain": "transaction"}

data: {"type": "sub-agent", "agent": "[TRANSACTION AGENT]", "status": "done"}

data: {"type": "data", "template": "quickReply", "data": {"assistantResponse": "주문서 생성에 실패했어요. 주문 정보를 다시 확인해 주세요.", "quickReplies": [{"label": "주문 정보 다시 확인", "domain": "TRANSACTION"}, {"label": "장바구니 확인", "domain": "TRANSACTION", "url": "https://wwwqa.tstation.com/cart"}], "metadata": {"goodsId": "G000000310120", "shopId": "F07780", "quickOrderResult": "failed", "action": "quick_order_execute", "router_skipped": true, "source": "preOrder_action", "called_tools": ["quick_order_tool"]}}, "source_domain": "transaction", "assistant_response_source": "code_quick_order_action"}

data: {"type": "message", "content": "주문서 생성에 실패했어요. 주문 정보를 다시 확인해 주세요.", "agent": "[TRANSACTION AGENT]"}

data: {"type": "sub-agent", "agent": "[DONE]", "status": "success"}

data: {"type": "DONE"}

data: [DONE]
