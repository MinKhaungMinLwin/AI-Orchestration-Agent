"""Deterministic intent policy for Transaction stock/store/reservation flows."""

from __future__ import annotations

import re
import datetime
from typing import Any, Mapping

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.flow_controller import resolve_purchase_order_flow
from services.tstation.policies.policy_text_matchers import is_general_card_cancel_timing_policy_query
from services.tstation.policies.response_decision import ToolPlan
from services.tstation.policies.store_service_gate import (
    classify_store_name_role,
    extract_store_attribute_inquiry,
    extract_valid_store_name,
    has_store_service_availability_signal,
    normalize_store_service_request,
)


_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d)(\d)(?:\3)?\s*R?\s*(\d{2})\b", re.IGNORECASE)
_QUANTITY_RE = re.compile(r"(\d+)\s*(?:개|본|짝)")
_TODAY_RE = re.compile(r"오늘|당일|바로|당장", re.IGNORECASE)
_NOW_SERVICE_REQUEST_RE = re.compile(
    r"지금.{0,12}(?:장착|서비스|예약|방문|가능)|(?:장착|서비스|예약|방문).{0,12}지금",
    re.IGNORECASE,
)
_CURRENTLY_MOUNTED_TIRE_RE = re.compile(
    r"(?:지금|현재)?\s*장착\s*중(?:인)?\s*타이어|(?:지금|현재)?\s*끼고\s*있는\s*타이어",
    re.IGNORECASE,
)
_RELATIVE_RESERVATION_DATE_RE = re.compile(r"내일|모레", re.IGNORECASE)
_EXPLICIT_MD_DATE_RE = re.compile(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_BOOKING_DATETIME_SELECTION_RE = re.compile(
    r"(?:20\d{2}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일(?:\s*\([^)]+\))?\s*(?:\n|\s)\s*\d{1,2}:\d{2}",
    re.IGNORECASE,
)
_STOCK_RE = re.compile(r"재고|오늘\s*서비스|오늘서비스|당일\s*서비스|T\s*바로\s*배송|T바로배송", re.IGNORECASE)
_RESERVATION_RE = re.compile(r"예약|장착|방문|갈게|가고\s*싶|작업", re.IGNORECASE)
_PURCHASE_RE = re.compile(r"구매|주문|결제|살래|살게|사고\s*싶|사려고", re.IGNORECASE)
_CART_RE = re.compile(r"장바구니|카트|담아|담기|넣어|넣기", re.IGNORECASE)
_STORE_SCHEDULE_RE = re.compile(
    r"예약\s*가능|예약\s*(?:가능한\s*)?(?:시간|일정|슬롯)|"
    r"(?:방문\s*)?예약\s*(?:잡|해|걸|보여|알려)|"
    r"예약\s*(?:잡아|해줘|걸어줘)|"
    r"장착\s*가능.{0,20}(?:매장|지점|곳)|"
    r"(?:가능한\s*)?(?:예약\s*)?(?:시간표|스케줄|슬롯)\s*(?:보여|알려|확인)|"
    r"(?:이번|오늘|내일|모레|주말|토요일|일요일|평일|오전|오후|저녁|"
    r"\d{1,2}\s*시|\d{1,2}\s*월\s*\d{1,2}\s*일).{0,20}(?:예약|방문)\s*가능|"
    r"(?:예약|방문)\s*가능.{0,20}(?:이번|오늘|내일|모레|주말|토요일|일요일|평일|오전|오후|저녁|"
    r"\d{1,2}\s*시|\d{1,2}\s*월\s*\d{1,2}\s*일)",
    re.IGNORECASE,
)
_STORE_VISIT_ADVISORY_RE = re.compile(
    r"한가|붐비|혼잡|대기|대기\s*시간|사람\s*많|차량\s*많|덜\s*붐|"
    r"언제\s*(?:가|방문).{0,20}(?:좋|나|될|돼|괜찮)|"
    r"(?:가도|방문해도|그\s*시간에\s*가도|그때\s*가도).{0,12}(?:돼|되|괜찮|가능)|"
    r"점심\s*시간.{0,20}(?:작업|방문|가능|해|하)|"
    r"(?:일요일|공휴일|휴무|휴일).{0,20}(?:문\s*열|영업|운영|쉬|휴무|열어)|"
    r"(?:문\s*열|영업|운영|쉬|휴무|열어).{0,20}(?:일요일|공휴일|휴무|휴일)",
    re.IGNORECASE,
)
_OPEN_STORE_FILTER_RE = re.compile(
    r"(?=.*(?:매장|지점|티스테이션|더타이어샵|곳))"
    r"(?=.*(?:토요일|일요일|주말|공휴일|휴일|휴무))"
    r"(?=.*(?:문\s*열|영업|운영|열어|여는|여나|하나|하는|가능))",
    re.IGNORECASE,
)
_RESERVATION_STORE_REF_RE = re.compile(
    r"예약(?:한|하신)?\s*(?:매장|지점|곳)|내\s*예약\s*(?:매장|지점|곳)|예약\s*매장|예약\s*지점",
    re.IGNORECASE,
)
_RESERVATION_STORE_INFO_RE = re.compile(
    r"전화|전화번호|연락처|주소|위치|어디|영업|운영|휴무|정보|상세|가고\s*싶|연락|전화하고",
    re.IGNORECASE,
)
_PLAIN_STORE_INFO_RE = re.compile(
    r"정보|상세|주소|전화|전화번호|연락처|영업\s*시간|운영\s*시간|휴무|서비스|"
    r"전경|사진|외관|내부|모습|이미지|매장\s*상세",
    re.IGNORECASE,
)
_STORE_HOLIDAY_LOOKUP_RE = re.compile(
    r"일요일|공휴일|휴일|휴무|명절|설날|설\s*연휴|추석|연휴|석가탄신일|어린이날|5\s*/\s*1|"
    r"문\s*열|영업|운영|쉬나|쉬어",
    re.IGNORECASE,
)
_STORE_SELECTION_REFERENCE_RE = re.compile(
    r"(?:첫|두|세|네|다섯|마지막)\s*(?:번\s*째|번째|번)?\s*매장|"
    r"\d+\s*(?:번\s*째|번째|번|[.)])\s*매장|"
    r"이\s*매장|그\s*매장|해당\s*매장",
    re.IGNORECASE,
)
_STORE_NAME_CANDIDATE_RE = re.compile(r"((?:티스테이션\s*)?[가-힣A-Za-z0-9]+(?:점|매장))")
_STORE_RESERVATION_ACTION_RE = re.compile(
    r"예약\s*(?:가능|시간|일정|변경|바꾸|바꿔|취소|해줘|잡아)|"
    r"방문\s*(?:가능|시간|일정|변경)|"
    r"장착\s*(?:가능|예약|해줘)|"
    r"\d{1,2}\s*시\s*로\s*(?:변경|바꿔)",
    re.IGNORECASE,
)
_EXPLICIT_ORDER_EXECUTION_RE = re.compile(
    r"주문\s*서\s*만들|주문서\s*만들|주문\s*해\s*줘|주문해줘|주문\s*하기|"
    r"이\s*정보대로\s*(?:주문|진행)|이대로\s*(?:주문|진행)|예약\s*해\s*줘|예약해줘",
    re.IGNORECASE,
)
_ORDER_HISTORY_REORDER_PREVIOUS_RE = re.compile(r"지난(?:번)?|이전|전에|예전|마지막|과거", re.IGNORECASE)
_ORDER_HISTORY_REORDER_SOURCE_RE = re.compile(r"주문|구매|장착|교체|산|샀", re.IGNORECASE)
_ORDER_HISTORY_REORDER_ACTION_RE = re.compile(
    r"다시|재구매|같은|동일|또|구매|주문|장착|교체|살래|살게",
    re.IGNORECASE,
)
_REGISTERED_VEHICLE_LOOKUP_RE = re.compile(
    r"^(?:내\s*차|내차|내\s*차량|내차량|"
    r"내(?:가)?\s*(?:(?:홈페이지|사이트|티스테이션|계정)에?\s*)?"
    r"(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)\s*(?:차|차량)|"
    r"(?:홈페이지|사이트|티스테이션|계정)에?\s*등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차|차량)|"
    r"등록\s*(?:차량|차)|보유\s*(?:차량|차))"
    r"\s*(?:목록|리스트|보기|보여\s*(?:줘|주세요)?|확인|조회|"
    r"뭐(?:야|니|고|였|지|든지|ㄴ지)?|뭔지|뭔가|"
    r"무슨\s*(?:차|차종|차량)인지|어떤\s*(?:차|차종|차량)인지|"
    r"알려\s*(?:줘|줄래|주세요|주라)?)?\s*[?.!~]*$",
    re.IGNORECASE,
)
STOCK_INVENTORY_STORE_LOOKUP_ALLOWED_TOOLS = (
    "get_store_inventory_tool",
    "search_stores_tool",
    "get_store_list_tool",
    "get_logistics_inventory_tool",
)
_ORDER_HISTORY_LOOKUP_RE = re.compile(
    r"내\s*주문(?:\s*(?:내역|목록))?\s*(?:좀|쫌|한번|한\s*번)?\s*(?:보여|조회|확인|알려)|"
    r"주문\s*(?:내역|목록)\s*(?:좀|쫌|한번|한\s*번)?\s*(?:보여|조회|확인|알려)|"
    r"최근\s*주문(?:\s*내역)?\s*(?:좀|쫌|한번|한\s*번)?\s*(?:보여|조회|확인|알려)|"
    r"내가\s*주문한\s*거\s*(?:좀|쫌|한번|한\s*번)?\s*(?:보여|조회|확인|알려)",
    re.IGNORECASE,
)
_ORDER_HISTORY_PAGE_NAVIGATION_RE = re.compile(
    r"주문\s*(?:내역|목록|페이지).{0,12}(?:이동|열어|들어가|바로가기|페이지)|"
    r"(?:마이페이지|주문내역\s*페이지).{0,12}(?:이동|열어|들어가|바로가기)",
    re.IGNORECASE,
)
_RESERVATION_STATUS_LOOKUP_RE = re.compile(
    r"내\s*예약|예약\s*(?:조회|내역|확인|상태)|다음\s*방문|예약\s*어떻게\s*돼|예약\s*어떻게돼|"
    r"내\s*예약\s*(?:시간|일정).{0,24}(?:바뀌었|바뀌|변경|밀렸|옮겨졌).{0,24}(?:조회|확인|봤|봐|알려)|"
    r"(?:오늘|내일|모레|오전|오후|저녁|\d{1,2}\s*시).{0,18}"
    r"(?:예약한\s*거|예약한거|예약\s*잡힌\s*거|예약\s*잡힌거|잡힌\s*예약|예약\s*되어|예약\s*돼|예약됐)"
    r".{0,20}(?:있|확인|맞|어떻게|알려)|"
    r"(?:예약한\s*거|예약한거|예약\s*잡힌\s*거|예약\s*잡힌거|잡힌\s*예약|예약\s*되어|예약\s*돼|예약됐)"
    r".{0,20}(?:있|확인|맞|어떻게|알려)",
    re.IGNORECASE,
)
_OWNED_RESERVATION_CHANGE_STATUS_RE = re.compile(
    r"내\s*예약\s*(?:시간|일정).{0,24}(?:바뀌었|바뀌|변경|밀렸|옮겨졌).{0,24}(?:조회|확인|봤|봐|알려)",
    re.IGNORECASE,
)
_RESERVATION_AVAILABILITY_OR_BOOKING_RE = re.compile(
    r"예약\s*가능|예약\s*(?:가능한\s*)?(?:시간|일정|슬롯)|"
    r"예약\s*(?:잡아|잡아줘|잡아주세요|해줘|해주세요|걸어|걸어줘|해\s*줘)|"
    r"예약\s*(?:잡|하|걸).{0,12}(?:줘|주세요|싶|래|려고|가능)|"
    r"(?:가능한\s*)?(?:예약\s*)?(?:시간표|스케줄|슬롯)\s*(?:보여|알려|확인)",
    re.IGNORECASE,
)
_RESERVATION_WINDOW_POLICY_RE = re.compile(
    r"(?:두\s*달|2\s*달|한\s*달\s*넘|1\s*달\s*넘|30일\s*(?:이후|뒤)|"
    r"최대\s*(?:며칠|몇\s*일|몇\s*주)|언제까지\s*장착\s*예약|예약\s*가능\s*기간|"
    r"장착\s*예약(?:은)?\s*최대\s*(?:며칠|몇\s*일|몇\s*주)|"
    r"(?:두\s*달|2\s*달).{0,12}예약\s*가능|예약.{0,12}(?:30일|1개월|한\s*달).{0,8}(?:이내|까지)|"
    r"예약.{0,12}변경.{0,12}(?:언제까지|기한|마감|가능\s*기간)|"
    r"(?:언제까지|기한|마감).{0,12}예약.{0,12}변경)",
    re.IGNORECASE,
)
_DELIVERY_DELAY_RE = re.compile(
    r"배송(?:이)?\s*지연|배송이\s*늦|상품\s*미도착|미도착|입고\s*지연|도착이\s*늦|배송\s*늦",
    re.IGNORECASE,
)
_RESERVATION_AUTO_CHANGE_POLICY_RE = re.compile(
    r"예약\s*(?:일정|시간)?\s*도?\s*자동\s*(?:으로\s*)?(?:변경|바뀌|밀리)|"
    r"자동\s*(?:으로\s*)?(?:변경|바뀌|밀리).{0,20}예약|"
    r"예약\s*(?:일정|시간)?\s*(?:도\s*)?(?:변경되|바뀌|밀리)",
    re.IGNORECASE,
)
_RESERVATION_CHANGE_REQUEST_RE = re.compile(
    r"(?:내\s*)?예약.{0,24}(?:시간|일정|날짜)?.{0,24}(?:변경|바꾸|바꿔|옮겨|미뤄|당겨)|"
    r"(?:시간|일정|날짜).{0,16}(?:변경|바꾸|바꿔|옮겨|미뤄|당겨).{0,16}예약|"
    r"예약.{0,12}(?:변경하고\s*싶|바꾸고\s*싶|옮기고\s*싶)",
    re.IGNORECASE,
)
_STORE_ARRIVAL_NOTIFICATION_VISIT_RE = re.compile(
    r"(?:타이어|상품|주문|물건)?\s*"
    r"(?:매장|장착점|지점)?\s*(?:에\s*)?"
    r"(?:도착|입고|왔|왔다|왔대|배송\s*완료|배송완료).{0,30}"
    r"(?:문자|SMS|sms|알림|알람|연락|전화|카톡|알림톡).{0,50}"
    r"(?:지금|오늘|바로|출발|가도|가면|방문|들러|예약\s*시간|예약시간)|"
    r"(?:문자|SMS|sms|알림|알람|연락|전화|카톡|알림톡).{0,30}"
    r"(?:받|왔|왔다|왔어|왔는데|받았).{0,50}"
    r"(?:타이어|상품|주문|물건|매장|장착점|지점).{0,30}"
    r"(?:도착|입고|왔|배송\s*완료|배송완료).{0,50}"
    r"(?:지금|오늘|바로|출발|가도|가면|방문|들러|예약\s*시간|예약시간)|"
    r"(?:타이어|상품|주문|물건|매장|장착점|지점).{0,30}"
    r"(?:도착|입고|왔|배송\s*완료|배송완료).{0,50}"
    r"(?:지금|오늘|바로|출발|가도|가면|방문|들러|예약\s*시간|예약시간)",
    re.IGNORECASE,
)
_SERVICE_DURATION_ADVISORY_RE = re.compile(
    r"(?:예약한\s*거|예약한거|예약|서비스\s*받|작업|교체).{0,40}"
    r"(?:현장(?:에서)?\s*)?(?:얼라인먼트|휠\s*얼라이먼트|엔진오일|실내\s*필터|필터|배터리|와이퍼|경정비)"
    r".{0,40}(?:추가|같이|함께).{0,30}(?:시간|얼마나|소요|걸려)|"
    r"(?:얼라인먼트|휠\s*얼라이먼트|엔진오일|실내\s*필터|필터|배터리|와이퍼|경정비)"
    r".{0,40}(?:현장(?:에서)?\s*)?(?:추가|같이|함께).{0,30}(?:시간|얼마나|소요|걸려)",
    re.IGNORECASE,
)
_MAINTENANCE_HISTORY_LOOKUP_RE = re.compile(
    r"정비\s*이력|정비이력|정비\s*내역|정비내역|관리받은\s*(?:내역|거)|관리\s*받은\s*(?:내역|거)|"
    r"서비스\s*(?:이력|내역)|받은\s*(?:서비스|정비)|"
    r"(?:마지막|최근|전에|예전에).{0,24}"
    r"(?:휠\s*얼라인먼트|얼라인먼트|오일\s*필터|오일필터|엔진\s*오일|엔진오일|배터리|와이퍼|실내\s*필터|"
    r"타이어\s*(?:교체|장착)|경정비).{0,24}(?:언제|받|교체|갈|했|한\s*적)|"
    r"(?:휠\s*얼라인먼트|얼라인먼트|오일\s*필터|오일필터|엔진\s*오일|엔진오일|배터리|와이퍼|실내\s*필터|"
    r"타이어\s*(?:교체|장착)|경정비).{0,24}(?:받은|교체한|갈았|했던|한)\s*(?:날|날짜|때|적|게)?"
    r".{0,16}(?:언제|있)",
    re.IGNORECASE,
)
_MAINTENANCE_HISTORY_ACCESS_POLICY_RE = re.compile(
    r"(?:(?:정비|서비스|관리)\s*(?:이력|내역)|정비이력|정비내역|관리받은\s*(?:내역|거)|"
    r"관리\s*받은\s*(?:내역|거)|내\s*차\s*(?:이력|내역)).{0,60}"
    r"(?:조회\s*가능|확인\s*가능|볼\s*수|볼수|조회할\s*수|확인할\s*수|매장(?:에서)?\s*(?:조회|확인)|"
    r"아무\s*(?:티스테이션\s*)?(?:매장|지점)|다른\s*(?:지역|매장|지점)|이사|타\s*지역)|"
    r"(?:부산|여수|서울|제주|광주|대전|대구|울산|인천|경기|분당|판교|한남|모란).{0,40}"
    r"(?:(?:정비|서비스|관리)\s*(?:이력|내역)|정비이력|정비내역).{0,40}"
    r"(?:조회\s*가능|확인\s*가능|볼\s*수|볼수|매장(?:에서)?\s*(?:조회|확인))",
    re.IGNORECASE,
)
_VEHICLE_EXPERIENCE_STORE_SEARCH_RE = re.compile(
    r"(?=.*(?:매장|지점|곳|티스테이션|더타이어샵))"
    r"(?=.*(?:추천|찾|알려|보여|어디|가능|많은|많이|잘\s*하는))"
    r"(?=.*(?:BMW|비엠|벤츠|Mercedes|아우디|Audi|폭스바겐|Volkswagen|수입차|외제차|"
    r"\d+\s*시리즈|정비\s*경험|정비경험|작업\s*경험|작업경험|서비스\s*경험|서비스경험))",
    re.IGNORECASE,
)
_MAINTENANCE_HISTORY_SERVICE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("휠얼라인먼트", (r"휠\s*얼라인먼트", r"얼라인먼트")),
    ("오일필터", (r"오일\s*필터", r"오일필터")),
    ("엔진오일", (r"엔진\s*오일", r"엔진오일")),
    ("배터리", (r"배터리",)),
    ("와이퍼", (r"와이퍼",)),
    ("실내필터", (r"실내\s*필터", r"에어컨\s*필터", r"캐빈\s*필터")),
    ("타이어 교체", (r"타이어\s*(?:교체|장착)",)),
    ("경정비", (r"경정비",)),
)
_MAINTENANCE_ADDON_SERVICE_RE = re.compile(r"엔진\s*오일|실내\s*필터|필터|와이퍼|배터리|경정비", re.IGNORECASE)
_STORE_SERVICE_SEARCH_RE = re.compile(
    r"(?:매장|지점|곳).{0,20}(?:어디|찾|검색|알려|보여|있어|있나|가능)|"
    r"(?:어디|찾|검색|알려|보여|있어|있나|가능).{0,20}(?:매장|지점|곳)",
    re.IGNORECASE,
)
_TIRE_SERVICE_RE = re.compile(
    r"타이어.{0,12}(?:교체|장착|서비스|작업|예약)|(?:교체|장착|예약).{0,12}타이어",
    re.IGNORECASE,
)
_ADDON_WITH_RE = re.compile(r"같이|함께|동시|하면서|겸|추가|하고\s*싶", re.IGNORECASE)
_RESERVATION_CHANGE_RE = re.compile(r"변경|바꿔|옮겨|미뤄|당겨|취소", re.IGNORECASE)
_NOON_RE = re.compile(r"12\s*시|점심\s*시간", re.IGNORECASE)
_NEARBY_RE = re.compile(r"근처|주변|가까운|인근", re.IGNORECASE)
_STORE_SEARCH_RE = re.compile(r"매장|지점|티스테이션|더타이어샵|찾아|알려|보여", re.IGNORECASE)
_FAVORITE_STORE_RE = re.compile(
    r"내\s*단골(?:매장|가게|점)?|단골(?:매장|가게|점)|마이샵|자주\s*가는\s*매장",
    re.IGNORECASE,
)
_ORDER_DIRECT_NO_RE = re.compile(r"\bO\d{8,}\b", re.IGNORECASE)
_ORDER_NO_SUFFIX_RE = re.compile(r"(?:주문\s*)?(?P<suffix>\d{3,8})\s*번\s*주문|주문\s*(?:번호)?\s*(?P<suffix2>\d{3,8})\b", re.IGNORECASE)
_PAYMENT_METHOD_CHANGE_RE = re.compile(
    r"(?:주문|결제).{0,30}결제\s*수단.{0,30}(?:변경|바꾸|무통장|가상\s*계좌|입금)|"
    r"결제\s*수단.{0,30}(?:변경|바꾸|무통장|가상\s*계좌|입금)|"
    r"(?:무통장\s*입금|가상\s*계좌).{0,30}(?:변경|바꾸|결제\s*수단)",
    re.IGNORECASE,
)
_PAYMENT_ACCOUNT_INFO_RE = re.compile(r"무통장\s*입금\s*기한|가상\s*계좌|입금\s*기한|결제\s*정보", re.IGNORECASE)
_ORDER_CANCEL_STATUS_LOOKUP_RE = re.compile(
    r"(?:주문|결제|카드)?\s*취소.{0,18}(?:됐|되었|완료|처리|상태|확인|승인|맞지|맞아|됐어|됐나요|됐는지)|"
    r"(?:취소|캔슬)(?:된\s*거|된거|완료|처리|상태|승인).{0,18}(?:맞|확인|됐|됐어|됐나요|알려)|"
    r"(?:취소|캔슬)(?:한|된)\s*(?:주문|건).{0,18}(?:상태|확인|조회|알려)|"
    r"(?:주문|건).{0,18}(?:취소|캔슬).{0,18}(?:상태|확인|조회|알려)|"
    r"카드\s*취소\s*승인|결제\s*취소.{0,18}(?:됐|승인|처리|완료)",
    re.IGNORECASE,
)
_ORDER_DELIVERY_STATUS_LOOKUP_RE = re.compile(
    r"(?:주문|상품|타이어|구매(?:한)?\s*거).{0,24}"
    r"(?:배송\s*(?:상태|현황|조회|진행|예정)|도착\s*(?:예정|상태|일)|언제\s*(?:와|오|도착)|출고\s*(?:상태|현황))|"
    r"(?:배송\s*(?:상태|현황|조회|진행|예정)|도착\s*(?:예정|상태|일)|언제\s*(?:와|오|도착)|출고\s*(?:상태|현황))"
    r".{0,24}(?:주문|상품|타이어|구매(?:한)?\s*거)",
    re.IGNORECASE,
)
_ORDER_DELIVERY_STATUS_LOOKUP_TEXT_RE = re.compile(
    r"(?=.*(?:\uc8fc\ubb38|\uc0c1\ud488|\ud0c0\uc774\uc5b4|\uad6c\ub9e4(?:\ud55c)?\s*\uac70|\ubc30\uc1a1|\ub3c4\ucc29|\ucd9c\uace0))"
    r"(?=.*(?:\ubc30\uc1a1\s*(?:\uc0c1\ud0dc|\ud604\ud669|\uc870\ud68c|\uc9c4\ud589|\uc608\uc815)|"
    r"\ub3c4\ucc29\s*(?:\uc608\uc815|\uc0c1\ud0dc|\uc77c)|\uc5b8\uc81c\s*(?:\uc640|\uc624|\ub3c4\ucc29)|\ucd9c\uace0\s*(?:\uc0c1\ud0dc|\ud604\ud669)|"
    r"\ubc30\uc1a1|\ub3c4\ucc29|\ucd9c\uace0))",
    re.IGNORECASE,
)
_ORDER_CANCEL_REQUEST_RE = re.compile(
    r"(?:주문|예약|최근\s*주문|내\s*주문|주문번호\s*[A-Z]?\d{8,}).{0,30}(?:취소|캔슬)|"
    r"(?:취소|캔슬).{0,20}(?:해\s*줘|해주세요|처리|진행|하고\s*싶|할래|하려고|요청)|"
    r"(?:고객\s*센터|상담|전화).{0,40}(?:취소|캔슬)",
    re.IGNORECASE,
)
_ORDER_CANCEL_FEE_INQUIRY_RE = re.compile(
    r"(?=.*(?:주문|예약|취소|반품|캔슬))"
    r"(?=.*(?:위약금|수수료|비용|배송비|택배비|왕복\s*배송비|물어내|발생|얼마(?!나)))",
    re.IGNORECASE,
)
_OWNED_ORDER_CANCEL_FEE_ANCHOR_RE = re.compile(
    r"(?:\bO\d{8,}\b|"
    r"내\s*(?:주문|예약)|"
    r"내가\s*주문한\s*거|"
    r"(?:주문|예약)\s*내역|"
    r"(?:오늘|방금|최근)\s*(?:주문|예약)|"
    r"(?:주문|예약)한\s*거)",
    re.IGNORECASE,
)
_OWNED_ORDER_CANCEL_STATUS_ANCHOR_RE = re.compile(
    r"(?:\bO\d{8,}\b|"
    r"내\s*(?:주문|예약)|"
    r"내가\s*주문한\s*거|"
    r"(?:주문|예약)\s*내역|"
    r"(?:오늘|방금|최근)\s*(?:주문|예약)|"
    r"방금\s*취소한\s*(?:주문|거)|"
    r"(?:취소|캔슬)(?:한|된)\s*(?:주문|건)|"
    r"(?:이|그|해당)\s*(?:주문|예약|건|거)|"
    r"주문번호\s*[A-Z]?\d{4,})",
    re.IGNORECASE,
)
_ORDER_CANCEL_FEE_REFERENCE_RE = re.compile(r"(?:이|그|해당)\s*(?:주문|예약|건|거)", re.IGNORECASE)
_OTHER_STORE_RE = re.compile(r"다른\s*(?:매장|지점|곳)|다시\s*(?:확인|찾|검색)|새로\s*(?:찾|검색)", re.IGNORECASE)
_STORE_SCOPE_FOLLOWUP_RE = re.compile(
    r"다른\s*(?:매장|지점|곳)|근처(?:에)?\s*(?:다른\s*)?(?:매장|지점|곳)|주변\s*(?:매장|지점)|"
    r"(?:매장|지점)\s*(?:더|또|추가)|다른\s*지역|예약\s*가능\s*시간|가능\s*시간|가능\s*일정",
    re.IGNORECASE,
)
_STORE_CANDIDATE_SEARCH_RE = re.compile(
    r"(?:오늘\s*)?(?:장착\s*)?가능\s*(?:한\s*)?(?:매장|지점|곳)|"
    r"재고\s*(?:있는|있는\s*곳|확인\s*된)\s*(?:매장|지점|곳)|"
    r"다른\s*(?:매장|지점|곳)|(?:매장|지점)\s*(?:찾아|검색|보여)",
    re.IGNORECASE,
)
_SPECIFIC_STORE_RECHECK_RE = re.compile(r"다시\s*확인|재확인|한\s*번\s*더|한번\s*더", re.IGNORECASE)
_RESULT_LIMIT_RE = re.compile(r"(\d+)\s*(?:개|곳|군데)\s*(?:만|까지)?")
_KOREAN_RESULT_LIMITS = {
    "한": 1,
    "두": 2,
    "세": 3,
    "네": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}
_KOREAN_RESULT_LIMIT_RE = re.compile(
    r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:개|곳|군데)\s*(?:만|까지)?"
)
_KNOWN_UNVERIFIED_STORE_NAMES = frozenset({"강남점", "티스테이션 강남점"})
_REGION_HINT_RE = re.compile(
    r"(서울|경기|서초|강남|마포|판교|분당|파주|강릉|부산|해운대|광교|성남|오목천|동광주|송파|한남|"
    r"청량리|인천|하남|청주|제주|서귀포)"
)
_PRODUCT_HINT_RE = re.compile(
    r"벤투스|ventus|다이나프로|dynapro|키너지|kinergy|아이온|ion|옵티모|optimo|미쉐린|michelin|cc2|"
    r"s\s*fit|g\s*fit|에스핏|지핏|i\*?cept|icept|아이셉트|4s2|dws06|cc7|ps4s|ps\s*as\s*4|psas4|cup\s*2|cup2|p7",
    re.IGNORECASE,
)
_PRICE_OR_COUPON_RE = re.compile(r"가격|할인가|최대\s*혜택|쿠폰|할인", re.IGNORECASE)
_TODAY_INSTALL_OR_RESERVATION_RE = re.compile(
    r"오늘\s*장착|오늘장착|오늘\s*서비스|오늘서비스|당일|"
    r"예약|방문|장착\s*가능|예약\s*가능|가능한\s*(?:시간|일정)|"
    r"몇\s*시|시간|스케줄",
    re.IGNORECASE,
)
_SCHEDULE_PREVIEW_SIGNAL_RE = re.compile(
    r"(?:다음\s*주|다음주|이번\s*주|이번주|주중|주말|평일|며칠\s*뒤|몇\s*일\s*뒤|\d+\s*일\s*뒤|언제|"
    r"장착\s*가능|예약\s*가능|가능한\s*(?:시간|일정|슬롯)|예약\s*(?:시간|일정|슬롯)|스케줄)",
    re.IGNORECASE,
)
_QUICK_ORDER_CONFIRM_RE = re.compile(
    r"^\s*(?:"
    r"주문\s*확정|구매하기|주문하기|결제하기|"
    r"주문해줘|구매해줘|결제해줘|"
    r"주문\s*진행|결제\s*진행|진행해(?:줘)?|바로\s*주문|"
    r"네|넵|넹|예|응|그래|좋아|ㅇㅇ|ㅇㅋ|ok|okay"
    r")\s*$",
    re.IGNORECASE,
)
_PRODUCT_ALIASES: tuple[tuple[str, str], ...] = (
    ("ventus air s", "Ventus air S"),
    ("벤투스 air s", "Ventus air S"),
    ("벤투스 에어 s", "Ventus air S"),
    ("벤투스 에어s", "Ventus air S"),
    ("dynapro hpx", "Dynapro HPX"),
    ("다이나프로 hpx", "Dynapro HPX"),
    ("kinergy ex", "Kinergy EX"),
    ("키너지 ex", "Kinergy EX"),
    ("kinergy st as", "Kinergy ST AS"),
    ("키너지 st as", "Kinergy ST AS"),
    ("ion evo as", "iON evo AS"),
    ("아이온 evo as", "iON evo AS"),
    ("아이온 에보 as", "iON evo AS"),
    ("ion evo as suv", "iON evo AS SUV"),
    ("아이온 evo as suv", "iON evo AS SUV"),
    ("아이온 에보 as suv", "iON evo AS SUV"),
    ("ion evo", "iON evo"),
    ("아이온 evo", "iON evo"),
    ("아이온 에보", "iON evo"),
    ("s fit as", "S FIT AS"),
    ("s fit", "S FIT"),
    ("에스핏", "S FIT"),
    ("g fit as", "G FIT AS"),
    ("g fit", "G FIT"),
    ("지핏", "G FIT"),
    ("i*cept", "i*cept"),
    ("icept", "i*cept"),
    ("아이셉트", "아이셉트"),
    ("4s2", "4S2"),
    ("dws06", "DWS06"),
    ("cc7", "CC7"),
    ("ps4s", "PS4S"),
    ("ps as 4", "PS AS 4"),
    ("psas4", "PS AS 4"),
    ("cup2", "CUP2"),
    ("cup 2", "CUP2"),
    ("p7", "P7"),
)


def normalize_tire_size(text: str) -> str | None:
    match = _SIZE_COMPACT_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}{match.group(3)}R{match.group(4)}"


def extract_quantity(text: str) -> int | None:
    match = _QUANTITY_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def extract_result_limit(text: str) -> int | None:
    match = _RESULT_LIMIT_RE.search(text or "")
    if match:
        try:
            return max(1, min(int(match.group(1)), 10))
        except ValueError:
            return None
    korean_match = _KOREAN_RESULT_LIMIT_RE.search(text or "")
    if korean_match:
        return _KOREAN_RESULT_LIMITS.get(korean_match.group(1))
    return None


def _normalize_store_slot_value(value: Any) -> str:
    text = re.sub(r"^(?:티스테이션|더타이어샵)\s*", "", str(value or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"[\s\-_/()]+", "", text).casefold()


def _store_candidate_or_canonical(candidate: str | None, slots: Mapping[str, Any]) -> str | None:
    """Use regex store extraction as a candidate; do not let it overwrite a cleaner canonical slot."""

    candidate_text = str(candidate or "").strip()
    canonical_text = str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    if not candidate_text or not canonical_text:
        return candidate_text or None

    candidate_key = _normalize_store_slot_value(candidate_text)
    canonical_key = _normalize_store_slot_value(canonical_text)
    if not candidate_key or not canonical_key or candidate_key == canonical_key:
        return candidate_text
    if candidate_key.endswith(canonical_key):
        prefix = candidate_key[: -len(canonical_key)]
        if re.search(r"\d+(?:개|본|짝)?|(?:개|본|짝)$", prefix):
            return canonical_text
    return candidate_text


def _kst_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()


def extract_requested_cal_day(text: str, *, today: datetime.date | None = None) -> str | None:
    base = today or _kst_today()
    value = text or ""
    if _TODAY_RE.search(value) or (
        _NOW_SERVICE_REQUEST_RE.search(value) and not _CURRENTLY_MOUNTED_TIRE_RE.search(value)
    ):
        return base.strftime("%Y%m%d")
    match = _RELATIVE_RESERVATION_DATE_RE.search(value)
    if match:
        token = match.group(0)
        offset = 1 if token == "내일" else 2
        return (base + datetime.timedelta(days=offset)).strftime("%Y%m%d")
    explicit = _EXPLICIT_MD_DATE_RE.search(value)
    if explicit:
        year = int(explicit.group(1) or base.year)
        month = int(explicit.group(2))
        day = int(explicit.group(3))
        try:
            requested = datetime.date(year, month, day)
        except ValueError:
            return None
        if explicit.group(1) is None and requested < base:
            requested = datetime.date(year + 1, month, day)
        return requested.strftime("%Y%m%d")
    return None


def _has_pending_today_install_context(slots: dict[str, Any]) -> bool:
    if not slots:
        return False
    if slots.get("availability_intent") == "today_install":
        return True
    if slots.get("pending_intent") in {"today_install", "stock", "store_with_stock"} and slots.get("requested_cal_day"):
        return True
    return bool(slots.get("requested_cal_day") and slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))


def _has_confirmed_product_quantity_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))

def _has_purchase_ready_product_quantity_context(slots: dict[str, Any]) -> bool:
    return bool(_has_confirmed_product_quantity_context(slots) and slots.get("tire_size"))


def _normalized_quantity(slots: dict[str, Any], text: str = "") -> int | None:
    value = extract_quantity(text) or slots.get("quantity") or slots.get("ord_qty")
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _has_confirmed_store_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))


def _is_stock_flow_context(slots: dict[str, Any]) -> bool:
    return bool(slots.get("pending_intent") == "stock" or slots.get("goal_type") == "store_with_stock")


def _is_order_or_reservation_context(slots: dict[str, Any]) -> bool:
    return bool(
        slots.get("pending_intent") in {"order", "reservation", "cart"}
        or slots.get("goal_type") in {"place_order", "add_to_cart"}
    )


def _has_parent_order_or_reservation_context(slots: dict[str, Any]) -> bool:
    availability_context = slots.get("availability_context")
    if not isinstance(availability_context, Mapping):
        return False
    for key in ("pending_order_context", "dormant_purchase_context"):
        context = availability_context.get(key)
        if not isinstance(context, Mapping):
            continue
        if context.get("pending_intent") in {"order", "reservation", "cart"}:
            return True
        if context.get("goal_type") in {"place_order", "add_to_cart"}:
            return True
    return False


def _is_preview_location_store_selection_turn(
    text: str,
    slots: dict[str, Any],
    *,
    current_has_product: bool,
    explicit_tire_size: str | None,
    current_price: bool,
    current_purchase: bool,
    current_reservation: bool,
) -> bool:
    if str(slots.get("source_tool") or "") != "transaction_store_preview_tool":
        return False
    if not (_has_confirmed_product_quantity_context(slots) and _has_confirmed_store_context(slots)):
        return False
    if current_has_product or explicit_tire_size or extract_quantity(text):
        return False
    if current_price or current_purchase or current_reservation:
        return False
    return True


def _is_today_install_context(slots: dict[str, Any], requested_cal_day: str | None = None) -> bool:
    return bool(
        slots.get("availability_intent") == "today_install"
        or requested_cal_day
        or slots.get("requested_cal_day")
    )


def _is_store_candidate_search_turn(text: str, slots: dict[str, Any]) -> bool:
    if not _STORE_CANDIDATE_SEARCH_RE.search(text or ""):
        return False
    if not (_is_stock_flow_context(slots) or _is_today_install_context(slots)):
        return False
    return bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))


def _is_specific_store_recheck_turn(text: str, current_store_name: str | None, slots: dict[str, Any]) -> bool:
    if not _SPECIFIC_STORE_RECHECK_RE.search(text or ""):
        return False
    return bool(current_store_name or slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))


def _extract_policy_store_name_candidate(text: str) -> str | None:
    match = _STORE_NAME_CANDIDATE_RE.search(text or "")
    if not match:
        return None
    return re.sub(r"^티스테이션\s+", "", re.sub(r"\s+", " ", match.group(1)).strip(), flags=re.IGNORECASE)


def _is_explicit_order_execution_request(text: str, slots: dict[str, Any]) -> bool:
    value = text or ""
    if not _EXPLICIT_ORDER_EXECUTION_RE.search(value):
        return False
    store_name = _extract_store_name(value) or str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    has_product = bool(
        _PRODUCT_HINT_RE.search(value)
        or slots.get("goods_no")
        or slots.get("product_name")
        or slots.get("tire_model")
        or slots.get("pattern_name")
    )
    has_quantity = bool(_QUANTITY_RE.search(value) or slots.get("quantity") or slots.get("ord_qty"))
    has_schedule = bool(
        _EXPLICIT_MD_DATE_RE.search(value)
        or _BOOKING_DATETIME_SELECTION_RE.search(value)
        or slots.get("requested_cal_day")
        or slots.get("rsv_hour")
    )
    return bool(has_product and has_quantity and store_name and has_schedule)


def _has_selected_store_reference(text: str, store_name: str | None) -> bool:
    return bool(store_name and _STORE_SELECTION_REFERENCE_RE.search(text or ""))


def _is_plain_store_info_lookup(text: str, *, selected_store_name: str | None = None) -> bool:
    if not _PLAIN_STORE_INFO_RE.search(text or ""):
        return False
    if _STORE_RESERVATION_ACTION_RE.search(text or ""):
        return False
    store_name = _extract_policy_store_name_candidate(text)
    if not store_name and not _has_selected_store_reference(text, selected_store_name):
        return False
    if _SERVICE_DURATION_ADVISORY_RE.search(text or ""):
        return False
    if has_store_service_availability_signal(text):
        return False
    if extract_store_attribute_inquiry(text, store_name=store_name) is not None:
        return False
    return True


def _is_store_holiday_lookup(text: str, *, selected_store_name: str | None = None) -> bool:
    value = text or ""
    if not _STORE_HOLIDAY_LOOKUP_RE.search(value):
        return False
    if _STORE_RESERVATION_ACTION_RE.search(value):
        return False
    return bool(_extract_policy_store_name_candidate(value) or _has_selected_store_reference(value, selected_store_name))


def _is_order_history_reorder_turn(text: str) -> bool:
    value = text or ""
    return bool(
        _ORDER_HISTORY_REORDER_PREVIOUS_RE.search(value)
        and _ORDER_HISTORY_REORDER_SOURCE_RE.search(value)
        and _ORDER_HISTORY_REORDER_ACTION_RE.search(value)
    )


def _is_order_history_lookup_turn(text: str) -> bool:
    value = text or ""
    if _ORDER_HISTORY_PAGE_NAVIGATION_RE.search(value):
        return False
    if _is_order_history_reorder_turn(value):
        return False
    return bool(_ORDER_HISTORY_LOOKUP_RE.search(value))


def _is_preorder_ready_context(slots: dict[str, Any]) -> bool:
    if not slots:
        return False
    quantity = slots.get("ord_qty") or slots.get("quantity")
    return bool(
        (slots.get("pending_intent") == "order" or slots.get("goal_type") == "place_order")
        and slots.get("goods_no")
        and quantity
        and (slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))
        and slots.get("requested_cal_day")
        and slots.get("rsv_hour")
    )


def _is_order_execute_confirmation_context(text: str, slots: dict[str, Any]) -> bool:
    if not re.search(r"주문\s*확정|결제\s*진행|진행해(?:줘)?|ㅇㅇ|ㅇㅋ|ok|okay", text or "", re.IGNORECASE):
        return False
    quantity = slots.get("ord_qty") or slots.get("quantity")
    return bool(
        (slots.get("pending_intent") == "order" or slots.get("goal_type") == "place_order")
        and slots.get("goods_no")
        and quantity
    )


def _requested_maintenance_history_item(text: str) -> str | None:
    for label, patterns in _MAINTENANCE_HISTORY_SERVICE_RULES:
        if any(re.search(pattern, text or "", re.IGNORECASE) for pattern in patterns):
            return label
    return None


def _is_preorder_confirmation_text(text: str) -> bool:
    return bool(_QUICK_ORDER_CONFIRM_RE.match(text or ""))


def _is_quantity_only_followup(
    text: str,
    *,
    current_has_product: bool,
    explicit_tire_size: str | None,
    current_store_name: str | None,
    current_region: str | None,
    current_price: bool,
    current_purchase: bool,
    current_reservation: bool,
    current_store_search: bool,
) -> bool:
    return bool(
        extract_quantity(text)
        and not current_has_product
        and not explicit_tire_size
        and not current_store_name
        and not current_region
        and not current_price
        and not current_purchase
        and not current_reservation
        and not current_store_search
    )


def _has_owned_order_cancel_fee_anchor(text: str, slots: dict[str, Any]) -> bool:
    if _ORDER_DIRECT_NO_RE.search(text) or _ORDER_NO_SUFFIX_RE.search(text):
        return True
    if _OWNED_ORDER_CANCEL_FEE_ANCHOR_RE.search(text):
        return True
    if not _ORDER_CANCEL_FEE_REFERENCE_RE.search(text):
        return bool(
            str(slots.get("referred_object_type") or "") == "order"
            and str(slots.get("referred_object_status") or "resolved") in {"resolved", "resolvable_from_context"}
        )
    return bool(
        slots.get("order_no")
        or slots.get("order_no_suffix")
        or slots.get("ord_no")
        or slots.get("selected_order_no")
        or slots.get("pending_order_no")
        or slots.get("reservation_store_reference")
        or slots.get("owned_record_target") in {"order", "reservation"}
        or (
            str(slots.get("referred_object_type") or "") == "order"
            and str(slots.get("referred_object_status") or "resolved") in {"resolved", "resolvable_from_context"}
        )
    )


def _has_owned_order_cancel_status_anchor(text: str, slots: dict[str, Any]) -> bool:
    if _OWNED_ORDER_CANCEL_STATUS_ANCHOR_RE.search(text):
        return True
    if _ORDER_DIRECT_NO_RE.search(text) or _ORDER_NO_SUFFIX_RE.search(text):
        return True
    return bool(
        slots.get("order_no")
        or slots.get("order_no_suffix")
        or slots.get("ord_no")
        or slots.get("selected_order_no")
        or slots.get("pending_order_no")
        or slots.get("owned_record_target") == "order"
        or (
            str(slots.get("referred_object_type") or "") == "order"
            and str(slots.get("referred_object_status") or "resolved") in {"resolved", "resolvable_from_context"}
        )
    )


def build_transaction_intent_frame(
    last_user_text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> IntentFrame:
    """Build a Transaction intent frame from current text and existing slots."""
    text = last_user_text or ""
    slots = dict(known_slots or {})
    explicit_tire_size = normalize_tire_size(text)
    current_store_name = _store_candidate_or_canonical(_extract_store_name(text), slots)
    raw_current_region = _extract_region(text)
    current_product_name = _extract_product_name(text)
    current_has_product = bool(current_product_name or _PRODUCT_HINT_RE.search(text))
    current_store_name_role = classify_store_name_role(text, store_name=current_store_name)
    current_store_is_context = current_store_name_role.role == "context"
    selected_store_name = current_store_name or str(slots.get("shop_name") or slots.get("store_name") or "").strip()
    current_selected_store_reference = _has_selected_store_reference(text, selected_store_name)
    current_region = None if current_store_is_context else raw_current_region
    action_store_name = None if current_store_is_context else current_store_name
    current_store_search = bool(_STORE_SEARCH_RE.search(text))
    current_favorite_store_lookup = bool(_FAVORITE_STORE_RE.search(text))
    current_reservation_store_info_lookup = bool(
        _RESERVATION_STORE_REF_RE.search(text) and _RESERVATION_STORE_INFO_RE.search(text)
    )
    current_reservation_window_policy = bool(
        _RESERVATION_WINDOW_POLICY_RE.search(text)
        and _RESERVATION_RE.search(text)
        and not current_reservation_store_info_lookup
        and not _ORDER_DIRECT_NO_RE.search(text)
        and not _RELATIVE_RESERVATION_DATE_RE.search(text)
        and not _EXPLICIT_MD_DATE_RE.search(text)
    )
    current_delivery_delay_reservation_schedule_policy = bool(
        _DELIVERY_DELAY_RE.search(text)
        and _RESERVATION_AUTO_CHANGE_POLICY_RE.search(text)
        and not current_reservation_store_info_lookup
        and not _ORDER_DIRECT_NO_RE.search(text)
    )
    owned_reservation_change_status_lookup = bool(_OWNED_RESERVATION_CHANGE_STATUS_RE.search(text))
    current_reservation_status_lookup = bool(
        (_RESERVATION_STATUS_LOOKUP_RE.search(text) or owned_reservation_change_status_lookup)
        and (owned_reservation_change_status_lookup or not _RESERVATION_AVAILABILITY_OR_BOOKING_RE.search(text))
        and not current_reservation_store_info_lookup
        and not current_reservation_window_policy
        and not current_delivery_delay_reservation_schedule_policy
    )
    current_reservation_change_request = bool(
        _RESERVATION_CHANGE_REQUEST_RE.search(text)
        and not current_reservation_window_policy
        and not current_delivery_delay_reservation_schedule_policy
    )
    current_order_cancel_status_signal = bool(_ORDER_CANCEL_STATUS_LOOKUP_RE.search(text))
    current_owned_order_cancel_status_lookup = bool(
        current_order_cancel_status_signal and _has_owned_order_cancel_status_anchor(text, slots)
    )
    current_general_card_cancel_timing_policy = bool(
        is_general_card_cancel_timing_policy_query(text)
        and not _has_owned_order_cancel_status_anchor(text, slots)
    )
    router_order_cart_status_check = str(slots.get("router_transaction_intent") or "") == "order_cart_status_check"
    router_order_cancel_fee_inquiry = str(slots.get("router_transaction_intent") or "") == "order_cancel_fee_inquiry"
    current_order_cancel_fee_inquiry = bool(
        router_order_cancel_fee_inquiry
        or (
            _ORDER_CANCEL_FEE_INQUIRY_RE.search(text)
            and not current_order_cancel_status_signal
        )
    )
    current_owned_order_cancel_fee_inquiry = bool(
        current_order_cancel_fee_inquiry and _has_owned_order_cancel_fee_anchor(text, slots)
    )
    current_general_cancel_fee_policy = bool(
        current_order_cancel_fee_inquiry and not current_owned_order_cancel_fee_inquiry
    )
    current_order_cancel_request = bool(
        _ORDER_CANCEL_REQUEST_RE.search(text)
        and not current_order_cancel_status_signal
        and not current_general_card_cancel_timing_policy
        and not current_order_cancel_fee_inquiry
    )
    current_payment_method_change = bool(_PAYMENT_METHOD_CHANGE_RE.search(text))
    current_payment_account_info = bool(_PAYMENT_ACCOUNT_INFO_RE.search(text))
    current_store_arrival_visit_guidance = bool(_STORE_ARRIVAL_NOTIFICATION_VISIT_RE.search(text))
    current_order_delivery_status_lookup = bool(
        _ORDER_DELIVERY_STATUS_LOOKUP_RE.search(text) or _ORDER_DELIVERY_STATUS_LOOKUP_TEXT_RE.search(text)
    )
    current_today_request = bool(
        _TODAY_RE.search(text)
        or (_NOW_SERVICE_REQUEST_RE.search(text) and not _CURRENTLY_MOUNTED_TIRE_RE.search(text))
    )
    current_stock = bool(_STOCK_RE.search(text) or current_today_request)
    current_price = bool(_PRICE_OR_COUPON_RE.search(text))
    router_alert_contract = str(slots.get("router_transaction_intent") or "") == "price_or_benefit_alert_request"
    current_maintenance_history_access_policy = bool(_MAINTENANCE_HISTORY_ACCESS_POLICY_RE.search(text))
    current_maintenance_history_lookup = bool(
        _MAINTENANCE_HISTORY_LOOKUP_RE.search(text) and not current_maintenance_history_access_policy
    )
    current_vehicle_experience_store_search = bool(
        str(slots.get("router_transaction_intent") or slots.get("policy_intent") or "").strip()
        == "store_recommendation_by_vehicle_experience"
        or _VEHICLE_EXPERIENCE_STORE_SEARCH_RE.search(text)
    )
    current_order_history_lookup = _is_order_history_lookup_turn(text)
    current_registered_vehicle_lookup = bool(
        str(slots.get("router_transaction_intent") or "").strip() == "vehicle_lookup"
        or _REGISTERED_VEHICLE_LOOKUP_RE.search(text)
    )
    current_plain_store_info_lookup = bool(
        (not current_store_is_context or current_selected_store_reference)
        and _is_plain_store_info_lookup(text, selected_store_name=selected_store_name)
        and not _is_explicit_order_execution_request(text, slots)
    )
    current_store_holiday_lookup = bool(
        (not current_store_is_context or current_selected_store_reference)
        and _is_store_holiday_lookup(text, selected_store_name=selected_store_name)
    )
    current_order_history_reorder = _is_order_history_reorder_turn(text)
    current_purchase = bool(_PURCHASE_RE.search(text))
    current_cart = bool(_CART_RE.search(text))
    current_service_duration_advisory = bool(
        _SERVICE_DURATION_ADVISORY_RE.search(text) and not _RESERVATION_CHANGE_RE.search(text)
    )
    current_store_attribute_inquiry = (
        None
        if current_store_is_context
        else extract_store_attribute_inquiry(text, store_name=action_store_name)
    )
    current_store_service_request = normalize_store_service_request(text)
    router_policy_intent = str(slots.get("policy_intent") or "")
    router_store_service_search = (
        router_policy_intent in {
            "store_service_search",
            "unsupported_or_unmapped_store_service_policy",
        }
        and bool(str(slots.get("service_name") or slots.get("service_code") or "").strip())
        and bool(
            str(slots.get("region") or slots.get("place_query") or slots.get("store_name") or "").strip()
        )
    )
    router_store_service_codes = tuple(
        str(code).strip()
        for code in (slots.get("service_codes") or ())
        if str(code).strip()
    ) or (() if not slots.get("service_code") else (str(slots.get("service_code")).strip(),))
    current_store_service_availability = has_store_service_availability_signal(text)
    current_store_service_search = bool(
        (
            (
                router_store_service_search
                and router_policy_intent == "unsupported_or_unmapped_store_service_policy"
            )
            or (
                router_store_service_search
                and not action_store_name
            )
            or (
                current_store_service_request
                and _STORE_SERVICE_SEARCH_RE.search(text)
                and not current_stock
                and not current_price
                and not current_purchase
            )
        )
    )
    current_store_visit_advisory = bool(
        _STORE_VISIT_ADVISORY_RE.search(text)
        and not current_price
        and not current_purchase
    )
    current_open_store_filter = bool(
        current_store_visit_advisory
        and _OPEN_STORE_FILTER_RE.search(text)
        and not action_store_name
        and (current_region or _NEARBY_RE.search(text))
        and not current_has_product
    )
    current_maintenance_addon_with_tire = bool(
        _TIRE_SERVICE_RE.search(text)
        and _MAINTENANCE_ADDON_SERVICE_RE.search(text)
        and _ADDON_WITH_RE.search(text)
        and not current_service_duration_advisory
    )
    current_reservation = bool(
        _RESERVATION_RE.search(text) or _STORE_SCHEDULE_RE.search(text) or current_purchase
    )
    preview_location_store_selection = _is_preview_location_store_selection_turn(
        text,
        slots,
        current_has_product=current_has_product,
        explicit_tire_size=explicit_tire_size,
        current_price=current_price,
        current_purchase=current_purchase,
        current_reservation=current_reservation,
    )
    plain_store_search = (
        current_store_search
        and not current_favorite_store_lookup
        and not current_stock
        and not current_price
        and not current_reservation
        and current_store_attribute_inquiry is None
    )
    pending_today_install = _has_pending_today_install_context(slots)
    confirmed_product_quantity_context = _has_confirmed_product_quantity_context(slots)
    product_quantity_context_ready_for_store_scope = (
        _has_purchase_ready_product_quantity_context(slots)
        if _is_order_or_reservation_context(slots)
        else confirmed_product_quantity_context
    )
    other_store_today_install_continuation = (
        pending_today_install
        and bool(_OTHER_STORE_RE.search(text))
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
    )
    region_only_today_install_continuation = (
        pending_today_install
        and bool(current_region)
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
        and not (plain_store_search and not _OTHER_STORE_RE.search(text))
    )
    date_only_today_install_continuation = (
        pending_today_install
        and bool(extract_requested_cal_day(text))
        and not current_region
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not current_price
        and not current_purchase
        and not current_reservation
        and not plain_store_search
        and not (
            _BOOKING_DATETIME_SELECTION_RE.search(text)
            and _is_order_or_reservation_context(slots)
            and _has_confirmed_store_context(slots)
            and slots.get("rsv_hour")
        )
    )
    store_scope_product_continuation = (
        product_quantity_context_ready_for_store_scope
        and not (plain_store_search and not _OTHER_STORE_RE.search(text))
        and bool(_STORE_SCOPE_FOLLOWUP_RE.search(text) or (current_region and len(text.strip()) <= 20))
        and not current_store_name
        and not current_has_product
        and not explicit_tire_size
        and not extract_quantity(text)
        and not current_price
        and not current_purchase
        and not current_reservation
    )
    region_scope_product_continuation = bool(store_scope_product_continuation and current_region and not current_store_name)
    quantity_slot_fill_stock_continuation = (
        _is_stock_flow_context(slots)
        and bool(slots.get("goods_no") and (slots.get("tire_size") or slots.get("product_name")))
        and _is_quantity_only_followup(
            text,
            current_has_product=current_has_product,
            explicit_tire_size=explicit_tire_size,
            current_store_name=current_store_name,
            current_region=current_region,
            current_price=current_price,
            current_purchase=current_purchase,
            current_reservation=current_reservation,
            current_store_search=current_store_search,
        )
    )
    quantity_slot_fill_purchase_continuation = (
        _is_order_or_reservation_context(slots)
        and bool(slots.get("goods_no") and (slots.get("tire_size") or slots.get("product_name") or slots.get("tire_model")))
        and _is_quantity_only_followup(
            text,
            current_has_product=current_has_product,
            explicit_tire_size=explicit_tire_size,
            current_store_name=current_store_name,
            current_region=current_region,
            current_price=current_price,
            current_purchase=current_purchase,
            current_reservation=current_reservation,
            current_store_search=current_store_search,
        )
    )
    quantity_only_stock_continuation = (
        _is_stock_flow_context(slots)
        and confirmed_product_quantity_context
        and _has_confirmed_store_context(slots)
        and _is_quantity_only_followup(
            text,
            current_has_product=current_has_product,
            explicit_tire_size=explicit_tire_size,
            current_store_name=current_store_name,
            current_region=current_region,
            current_price=current_price,
            current_purchase=current_purchase,
            current_reservation=current_reservation,
            current_store_search=current_store_search,
        )
    )
    preorder_confirmation = bool(
        _is_preorder_confirmation_text(text)
        and (
            _is_preorder_ready_context(slots)
            or _is_order_execute_confirmation_context(text, slots)
        )
    )
    quantity = _normalized_quantity(slots, text)
    result_limit = extract_result_limit(text) or slots.get("limit")
    requested_cal_day = extract_requested_cal_day(text)
    today_requested = current_today_request
    explicit_preview_request = bool(
        requested_cal_day
        or today_requested
        or _TODAY_INSTALL_OR_RESERVATION_RE.search(text)
        or slots.get("availability_intent") == "today_install"
    )

    tire_size = explicit_tire_size or slots.get("tire_size")
    if pending_today_install and not requested_cal_day:
        requested_cal_day = slots.get("requested_cal_day")
    store_candidate_search = (
        _is_store_candidate_search_turn(text, slots)
        and not _is_specific_store_recheck_turn(text, current_store_name, slots)
    )
    specific_store_recheck = (
        _is_specific_store_recheck_turn(text, current_store_name, slots)
        and _is_stock_flow_context(slots)
        and bool(slots.get("goods_no") and (slots.get("quantity") or slots.get("ord_qty")))
    )
    preserve_pending_today_install = (
        region_only_today_install_continuation
        or date_only_today_install_continuation
        or other_store_today_install_continuation
        or store_candidate_search
        or specific_store_recheck
    )
    purchase_store_slot_fill_context = bool(
        _is_order_or_reservation_context(slots)
        and (slots.get("ord_qty") or slots.get("quantity"))
        and (slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))
    )
    preserve_transaction_product_context = (
        preserve_pending_today_install
        or store_scope_product_continuation
        or purchase_store_slot_fill_context
    )
    goods_no = (
        None
        if plain_store_search and not current_has_product and not preserve_transaction_product_context
        else slots.get("goods_no")
    )
    product_name = (
        current_product_name
        or (
            None
            if plain_store_search and not preserve_transaction_product_context
            else slots.get("product_name") or slots.get("tire_model") or slots.get("pattern_name")
        )
    )
    store_name = action_store_name or (
        None
        if (plain_store_search and not preserve_transaction_product_context)
        or store_candidate_search
        or region_scope_product_continuation
        else slots.get("store_name") or slots.get("shop_name")
    )
    region = current_region or slots.get("region") or slots.get("place")

    has_product = bool(goods_no or product_name or _PRODUCT_HINT_RE.search(text))
    has_location = bool(
        region
        or slots.get("place_query")
        or store_name
        or (
            not store_candidate_search
            and (slots.get("shop_name") or slots.get("shop_id"))
        )
        or slots.get("lat")
        or slots.get("lng")
    )
    today_install_candidate_scope = bool(
        store_candidate_search
        or (
            quantity_slot_fill_stock_continuation
            and _is_today_install_context(slots, requested_cal_day)
            and not _has_confirmed_store_context(slots)
        )
    )
    today_requested = current_today_request
    stored_quantity = quantity or slots.get("ord_qty") or slots.get("quantity")
    selected_store_schedule_ready = bool(
        has_product
        and tire_size
        and stored_quantity
        and (store_name or slots.get("shop_id") or slots.get("shop_name") or slots.get("store_name"))
    )
    schedule_preview_requested = bool(
        _SCHEDULE_PREVIEW_SIGNAL_RE.search(text)
        and not _TODAY_RE.search(text)
        and not _is_today_install_context(slots, requested_cal_day)
    )
    stock_context_has_product = bool(
        current_has_product
        or slots.get("goods_no")
        or slots.get("product_name")
        or slots.get("tire_model")
        or slots.get("pattern_name")
        or slots.get("pending_product_name")
    )
    stock_context_has_location = bool(
        current_region
        or slots.get("place_query")
        or store_name
        or slots.get("region")
        or slots.get("place")
        or slots.get("shop_id")
        or slots.get("shop_name")
        or slots.get("store_name")
    )
    selected_schedule_followup = bool(
        _BOOKING_DATETIME_SELECTION_RE.search(text)
        and has_product
        and _has_confirmed_store_context(slots)
        and (_is_order_or_reservation_context(slots) or _has_parent_order_or_reservation_context(slots))
        and slots.get("requested_cal_day")
        and slots.get("rsv_hour")
    )

    entities: dict[str, Any] = {
        "tire_size": tire_size,
        "explicit_tire_size": explicit_tire_size,
        "quantity": quantity,
        "product_in_text": bool(_PRODUCT_HINT_RE.search(text)),
        "store_name": store_name,
        "region": region,
        "nearby": bool(_NEARBY_RE.search(text)),
        "today_requested": today_requested,
        "requested_cal_day": requested_cal_day,
        "noon_requested": bool(_NOON_RE.search(text)),
        "result_limit": result_limit,
        "stock_check_mode": "inventory_only",
        "today_install_candidate_scope": today_install_candidate_scope,
    }

    if current_payment_method_change:
        intent = "payment_method_change_request"
        sub_intent = "payment_method_change"
        entities["payment_method_change_request"] = True
        direct_order_match = _ORDER_DIRECT_NO_RE.search(text)
        suffix_match = _ORDER_NO_SUFFIX_RE.search(text)
        if direct_order_match:
            entities["order_no"] = direct_order_match.group(0).upper()
        elif suffix_match:
            entities["order_no_suffix"] = suffix_match.group("suffix") or suffix_match.group("suffix2")
    elif current_payment_account_info:
        intent = "payment_account_info_lookup"
        sub_intent = "payment_account_info"
        entities["payment_account_info_lookup"] = True
        direct_order_match = _ORDER_DIRECT_NO_RE.search(text)
        suffix_match = _ORDER_NO_SUFFIX_RE.search(text)
        if direct_order_match:
            entities["order_no"] = direct_order_match.group(0).upper()
        elif suffix_match:
            entities["order_no_suffix"] = suffix_match.group("suffix") or suffix_match.group("suffix2")
    elif current_owned_order_cancel_fee_inquiry:
        intent = "owned_order_cancel_fee_inquiry"
        sub_intent = "cancel_fee"
        entities["owned_order_cancel_fee_inquiry"] = True
        direct_order_match = _ORDER_DIRECT_NO_RE.search(text)
        suffix_match = _ORDER_NO_SUFFIX_RE.search(text)
        entities["owned_anchor_target"] = "reservation" if "예약" in text and not direct_order_match else "order"
        if direct_order_match:
            entities["order_no"] = direct_order_match.group(0).upper()
        elif suffix_match:
            entities["order_no_suffix"] = suffix_match.group("suffix") or suffix_match.group("suffix2")
    elif current_general_cancel_fee_policy:
        intent = "general_cancel_fee_policy"
        sub_intent = "cancel_fee_policy"
        entities["general_cancel_fee_policy"] = True
    elif current_general_card_cancel_timing_policy:
        intent = "general_card_cancel_timing_policy"
        sub_intent = "card_cancel_timing_policy"
        entities["general_card_cancel_timing_policy"] = True
    elif current_owned_order_cancel_status_lookup:
        intent = "order_cancel_status_lookup"
        sub_intent = "cancel_status"
        entities["order_cancel_status_lookup"] = True
        direct_order_match = _ORDER_DIRECT_NO_RE.search(text)
        if direct_order_match:
            entities["order_no"] = direct_order_match.group(0).upper()
    elif current_order_cancel_request:
        intent = "order_cancel_request"
        sub_intent = "cancel_request"
        entities["order_cancel_request"] = True
        direct_order_match = _ORDER_DIRECT_NO_RE.search(text)
        if direct_order_match:
            entities["order_no"] = direct_order_match.group(0).upper()
    elif current_delivery_delay_reservation_schedule_policy:
        intent = "delivery_delay_reservation_schedule_policy"
        sub_intent = "reservation_schedule_policy"
        entities["delivery_delay_reservation_schedule_policy"] = True
    elif current_reservation_window_policy:
        intent = "reservation_window_policy"
        sub_intent = "reservation_window_policy"
        entities["reservation_window_policy"] = True
    elif current_store_arrival_visit_guidance or current_order_delivery_status_lookup:
        intent = "order_arrival_status_lookup"
        sub_intent = "store_arrival_visit_guidance" if current_store_arrival_visit_guidance else "order_delivery_status"
        entities["store_arrival_visit_guidance"] = current_store_arrival_visit_guidance
        entities["owned_record_target"] = "order"
    elif current_maintenance_history_access_policy:
        intent = "maintenance_history_access_policy"
        sub_intent = "service_history_policy"
        entities["maintenance_history_access_policy"] = True
    elif current_maintenance_history_lookup:
        intent = "maintenance_history_lookup"
        sub_intent = "service_history"
        entities["requested_service_item"] = _requested_maintenance_history_item(text)
    elif current_order_history_lookup:
        intent = "order_history_lookup"
        sub_intent = "owned_order_list"
        entities["owned_record_target"] = "order"
    elif current_order_history_reorder:
        intent = "order_history_reorder"
        sub_intent = "reorder_from_owned_history"
        entities["owned_record_target"] = "order"
    elif current_registered_vehicle_lookup:
        intent = "vehicle_lookup"
        sub_intent = "registered_vehicle"
        entities["owned_record_target"] = "vehicle"
    elif current_store_holiday_lookup:
        intent = "store_holiday_lookup"
        sub_intent = "store_holiday"
        entities["store_name"] = _extract_policy_store_name_candidate(text) or selected_store_name or store_name
    elif current_plain_store_info_lookup:
        intent = "plain_store_info_lookup"
        sub_intent = "store_detail"
        entities["store_name"] = _extract_policy_store_name_candidate(text) or selected_store_name or store_name
    elif router_order_cart_status_check:
        intent = "order_history_lookup"
        sub_intent = "lookup"
        entities["owned_record_target"] = "order"
        entities["router_contract"] = True
    elif router_alert_contract:
        intent = "price_or_benefit_alert_request"
        sub_intent = "alert_request"
        entities["alert_request"] = True
        entities["alert_scope"] = "price_or_benefit"
        entities["router_contract"] = True
        if current_product_name or slots.get("goods_no") or slots.get("tire_model") or slots.get("product_name"):
            entities["product_context_available"] = True
    elif current_reservation_store_info_lookup:
        intent = "reservation_store_info_lookup"
        sub_intent = "reservation_store_reference"
        entities["reservation_store_reference"] = True
    elif current_reservation_change_request:
        intent = "reservation_change_request"
        sub_intent = "change_request"
        entities["reservation_management_action"] = "change_request"
        entities["owned_record_target"] = "reservation"
    elif current_reservation_status_lookup:
        intent = "reservation_status_lookup"
        sub_intent = "owned_record_status"
        entities["owned_record_target"] = "reservation"
    elif current_service_duration_advisory:
        intent = "service_duration_advisory"
        sub_intent = "additional_service_duration"
        if re.search(r"얼라인먼트|휠\s*얼라이먼트", text, re.IGNORECASE):
            entities["service_type"] = "alignment"
    elif current_store_attribute_inquiry and not (current_stock or current_price or current_purchase):
        intent = "store_attribute_inquiry"
        sub_intent = "store_attribute_inquiry"
        entities["attribute_text"] = current_store_attribute_inquiry.attribute_text
        entities["attribute_type"] = current_store_attribute_inquiry.attribute_type
        entities["verification_level"] = current_store_attribute_inquiry.verification_level
    elif current_store_service_search:
        service_name = str(
            (current_store_service_request or {}).get("service_name")
            or slots.get("service_name")
            or "매장 서비스"
        ).strip()
        service_codes = tuple(
            (current_store_service_request or {}).get("service_codes")
            or router_store_service_codes
        )
        unknown_service_requested = bool(service_codes) and all(str(code).strip() == "unknown" for code in service_codes)
        intent = (
            "unsupported_or_unmapped_store_service_policy"
            if unknown_service_requested
            else "store_service_search"
        )
        sub_intent = intent
        entities["service_name"] = service_name
        entities["service_codes"] = service_codes
        entities["service_key"] = str(
            (current_store_service_request or {}).get("service_key")
            or slots.get("service_key")
            or service_name
        ).strip()
        policy_store_name = _extract_policy_store_name_candidate(text) or store_name
        if policy_store_name:
            entities["store_name"] = policy_store_name
    elif current_vehicle_experience_store_search:
        intent = "store_recommendation_by_vehicle_experience"
        sub_intent = "store_search"
        entities["vehicle_experience_store_search"] = True
        entities["store_search_condition"] = "vehicle_experience"
        entities["requested_vehicle_experience"] = _vehicle_experience_store_search_condition(text, slots)
    elif current_store_service_availability and not (current_stock or current_price or current_purchase):
        intent = "store_service_advisory"
        sub_intent = "store_service_advisory"
        service_name = (
            str(current_store_service_request["service_name"])
            if current_store_service_request
            else "매장 서비스"
        )
        entities["attribute_text"] = service_name
        if current_store_service_request:
            entities["service_name"] = service_name
            entities["service_codes"] = tuple(current_store_service_request["service_codes"])
            entities["service_key"] = current_store_service_request["service_key"]
        entities["attribute_type"] = "service"
        entities["verification_level"] = "store_contact_required"
    elif current_open_store_filter:
        intent = "open_store_search"
        sub_intent = "open_store_filter"
        entities["open_store_filter"] = True
    elif current_store_visit_advisory and (store_name or has_location):
        intent = "store_visit_advisory"
        sub_intent = "store_visit_timing"
        entities["advisory_type"] = "store_visit_timing"
    elif current_maintenance_addon_with_tire:
        intent = "maintenance_addon_with_tire_service"
        sub_intent = "store_service_availability"
        entities["service_type"] = "maintenance_addon"
    elif preorder_confirmation:
        intent = "quick_order_execute"
        sub_intent = "confirm"
    elif selected_schedule_followup:
        intent = "quick_order_reservation"
        sub_intent = "reservation"
        entities["stock_check_mode"] = "preview"
    elif preserve_pending_today_install:
        intent = "stock_store_search"
        sub_intent = "today_install"
        entities["stock_check_mode"] = "preview"
    elif quantity_slot_fill_purchase_continuation:
        intent = "quick_order_reservation"
        sub_intent = "cart" if slots.get("pending_intent") == "cart" or slots.get("goal_type") == "add_to_cart" else "reservation"
        entities["stock_check_mode"] = "preview"
    elif quantity_only_stock_continuation or quantity_slot_fill_stock_continuation:
        intent = "stock_store_search"
        sub_intent = "today_install" if explicit_preview_request else ("reservation" if selected_store_schedule_ready else "stock")
        entities["stock_check_mode"] = "preview" if explicit_preview_request or selected_store_schedule_ready else "inventory_only"
    elif store_scope_product_continuation:
        if _is_order_or_reservation_context(slots):
            intent = "quick_order_reservation"
            sub_intent = "reservation"
            entities["stock_check_mode"] = "preview"
        else:
            intent = "stock_store_search"
            use_preview_scope = bool(
                _is_today_install_context(slots, requested_cal_day)
                or region_scope_product_continuation
            )
            sub_intent = "today_install" if use_preview_scope else "stock"
            entities["stock_check_mode"] = "preview" if use_preview_scope else "inventory_only"
    elif (
        _is_stock_flow_context(slots)
        and schedule_preview_requested
        and stock_context_has_product
        and stock_context_has_location
    ):
        intent = "stock_store_search"
        sub_intent = "reservation"
        entities["stock_check_mode"] = "preview"
    elif _PRICE_OR_COUPON_RE.search(text):
        intent = "price_or_coupon_check"
        sub_intent = "coupon" if "쿠폰" in text else "price"
    elif (
        _is_order_or_reservation_context(slots)
        and goods_no
        and stored_quantity
        and (
            slots.get("shop_id")
            or slots.get("pending_intent") == "cart"
            or slots.get("goal_type") == "add_to_cart"
        )
    ):
        intent = "quick_order_reservation"
        sub_intent = "cart" if slots.get("pending_intent") == "cart" or slots.get("goal_type") == "add_to_cart" else "reservation"
        entities["stock_check_mode"] = str(slots.get("stock_check_mode") or "preview")
    elif _is_order_or_reservation_context(slots) and has_product and (
        slots.get("pending_intent") == "cart" or slots.get("goal_type") == "add_to_cart" or current_cart
    ):
        intent = "quick_order_reservation"
        sub_intent = "cart"
    elif (
        current_purchase
        and (slots.get("pending_intent") == "stock" or slots.get("goal_type") == "store_with_stock")
        and goods_no
        and stored_quantity
        and (
            region
            or slots.get("region")
            or slots.get("place_query")
            or slots.get("shop_id")
            or slots.get("shop_name")
            or slots.get("store_name")
        )
    ):
        intent = "quick_order_reservation"
        sub_intent = "reservation"
        entities["stock_check_mode"] = "preview"
        entities["stock_to_purchase_continuation"] = True
    elif (
        (slots.get("pending_intent") == "stock" or slots.get("goal_type") == "store_with_stock")
        and goods_no
        and stored_quantity
        and (region or slots.get("region"))
    ):
        intent = "stock_store_search"
        sub_intent = "today_install" if _is_today_install_context(slots, requested_cal_day) else "stock"
        entities["stock_check_mode"] = str(
            slots.get("stock_check_mode") or ("preview" if sub_intent == "today_install" else "inventory_only")
        )
    elif (
        _STORE_SCHEDULE_RE.search(text)
        and has_product
        and (has_location or requested_cal_day or today_requested)
        and not (current_store_name and re.search(r"예약\s*(?:해줘|잡아|걸어)", text, re.IGNORECASE))
    ):
        intent = "stock_store_search"
        sub_intent = "today_install"
        entities["stock_check_mode"] = "preview"
    elif _STORE_SCHEDULE_RE.search(text) and (store_name or has_location) and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif _NOON_RE.search(text) and has_location and not has_product:
        intent = "store_schedule"
        sub_intent = "store_visit"
    elif current_favorite_store_lookup:
        intent = "favorite_store_lookup"
        sub_intent = "favorite"
    elif _STORE_SEARCH_RE.search(text) and has_location and not has_product and not preview_location_store_selection:
        intent = "store_search"
        sub_intent = "nearby" if entities["nearby"] else "region"
    elif _STOCK_RE.search(text) and selected_store_schedule_ready and not today_requested:
        intent = "stock_store_search"
        sub_intent = "reservation"
        entities["stock_check_mode"] = "preview"
    elif preview_location_store_selection and _is_order_or_reservation_context(slots):
        intent = "quick_order_reservation"
        sub_intent = "reservation"
        entities["stock_check_mode"] = "preview"
    elif preview_location_store_selection:
        intent = "stock_store_search"
        sub_intent = "today_install" if _is_today_install_context(slots, requested_cal_day) else "reservation"
        entities["stock_check_mode"] = "preview"
    elif (_STOCK_RE.search(text) or today_requested) and has_product:
        intent = "stock_store_search"
        sub_intent = "today_install" if today_requested else "stock"
        entities["stock_check_mode"] = "preview" if sub_intent == "today_install" else "inventory_only"
    elif (_RESERVATION_RE.search(text) or current_purchase or current_cart) and has_product:
        intent = "quick_order_reservation"
        sub_intent = "cart" if current_cart else "reservation"
    elif (_STORE_SCHEDULE_RE.search(text) or _RESERVATION_RE.search(text)) and not current_store_is_context:
        intent = "store_schedule"
        sub_intent = "store_visit"
    else:
        intent = "transaction_fallback"
        sub_intent = None

    missing_slots = _missing_slots_for_intent(
        intent=intent,
        has_product=has_product,
        goods_no=goods_no,
        tire_size=tire_size,
        quantity=quantity,
        has_location=has_location or today_install_candidate_scope,
        has_store=bool(store_name or slots.get("shop_id")),
        shop_id=slots.get("shop_id"),
        requested_cal_day=requested_cal_day or slots.get("requested_cal_day"),
        rsv_hour=slots.get("rsv_hour"),
    )

    known = {
        **slots,
        **({"region": region} if region else {}),
        **({"limit": result_limit} if result_limit else {}),
        **({"requested_cal_day": requested_cal_day} if requested_cal_day else {}),
    }
    if intent == "stock_store_search" and requested_cal_day:
        known["availability_intent"] = "today_install"
    if intent == "maintenance_addon_with_tire_service":
        known["pending_intent"] = "maintenance_addon_with_tire_service"
        known["service_action_boundary"] = "store_verification" if action_store_name else "service_booking_support"
        known["goal_type"] = known["service_action_boundary"]
        known["service_type"] = "maintenance_addon"
        if action_store_name:
            known["store_name"] = action_store_name
            known["shop_name"] = action_store_name
    if intent == "store_attribute_inquiry":
        known["goal_type"] = "store_attribute_inquiry"
        known["service_action_boundary"] = "store_verification"
        known["service_type"] = "store_attribute_inquiry"
        known["attribute_text"] = entities.get("attribute_text") or slots.get("attribute_text")
        known["attribute_type"] = entities.get("attribute_type") or slots.get("attribute_type") or "unknown"
        known["verification_level"] = (
            entities.get("verification_level") or slots.get("verification_level") or "store_contact_required"
        )
    if intent == "store_service_search":
        known["goal_type"] = "store_service_search"
        known["service_action_boundary"] = "store_verification"
        known["service_type"] = "store_service_search"
        known["service_name"] = entities.get("service_name")
        known["service_codes"] = tuple(entities.get("service_codes") or ())
    if intent == "store_recommendation_by_vehicle_experience":
        known["pending_intent"] = "store_recommendation_by_vehicle_experience"
        known["goal_type"] = "store_search"
        known["store_search_condition"] = "vehicle_experience"
        known["requested_vehicle_experience"] = entities.get("requested_vehicle_experience")
        if region:
            known["region"] = region
            known["place_query"] = known.get("place_query") or region
    if intent == "unsupported_or_unmapped_store_service_policy":
        known["goal_type"] = "unsupported_or_unmapped_store_service_policy"
        known["service_type"] = "unsupported_or_unmapped_store_service_policy"
        known["service_name"] = entities.get("service_name")
        known["service_codes"] = tuple(entities.get("service_codes") or ())
        if entities.get("store_name"):
            known["store_name"] = entities.get("store_name")
    if intent == "store_service_advisory":
        known["goal_type"] = "store_service_advisory"
        known["service_action_boundary"] = "policy_answer"
        known["service_type"] = "store_service_advisory"
        known["attribute_text"] = entities.get("attribute_text") or slots.get("attribute_text")
        if entities.get("service_name"):
            known["service_name"] = entities.get("service_name")
            known["service_codes"] = tuple(entities.get("service_codes") or ())
    if intent == "open_store_search":
        known["goal_type"] = "store_finder"
        known["open_only"] = True
    if intent == "reservation_store_info_lookup":
        known["pending_intent"] = "reservation_store_info_lookup"
        known["goal_type"] = "reservation_store_info"
        known["reservation_store_reference"] = True
    if intent == "reservation_status_lookup":
        known["pending_intent"] = "reservation_status_lookup"
        known["goal_type"] = "owned_record_lookup"
        known["owned_record_target"] = "reservation"
        known["reservation_management_action"] = "lookup"
    if intent == "reservation_change_request":
        known["pending_intent"] = "reservation_change_request"
        known["goal_type"] = "reservation_management"
        known["owned_record_target"] = "reservation"
        known["reservation_management_action"] = "change_request"
    if intent == "order_arrival_status_lookup":
        known["pending_intent"] = "order_arrival_status_lookup"
        known["goal_type"] = "owned_record_lookup"
        known["owned_record_target"] = "order"
        if entities.get("store_arrival_visit_guidance"):
            known["store_arrival_visit_guidance"] = True
    if intent == "delivery_delay_reservation_schedule_policy":
        known["pending_intent"] = "delivery_delay_reservation_schedule_policy"
        known["goal_type"] = "support_policy_answer"
        known["delivery_delay_reservation_schedule_policy"] = True
    if intent == "reservation_window_policy":
        known["pending_intent"] = "reservation_window_policy"
        known["goal_type"] = "support_policy_answer"
        known["reservation_window_policy"] = True
    if intent == "order_cancel_status_lookup":
        known["pending_intent"] = "order_cancel_status_lookup"
        known["goal_type"] = "order_cancel_status_lookup"
        known["order_cancel_status_lookup"] = True
        if entities.get("order_no"):
            known["order_no"] = entities["order_no"]
    if intent == "general_card_cancel_timing_policy":
        known["pending_intent"] = "general_card_cancel_timing_policy"
        known["goal_type"] = "support_policy_answer"
        known["general_card_cancel_timing_policy"] = True
    if intent == "owned_order_cancel_fee_inquiry":
        known["pending_intent"] = "owned_order_cancel_fee_inquiry"
        known["goal_type"] = "owned_order_cancel_fee_inquiry"
        known["owned_order_cancel_fee_inquiry"] = True
        if entities.get("owned_anchor_target"):
            known["owned_anchor_target"] = entities["owned_anchor_target"]
        if entities.get("order_no"):
            known["order_no"] = entities["order_no"]
        if entities.get("order_no_suffix"):
            known["order_no_suffix"] = entities["order_no_suffix"]
    if intent == "general_cancel_fee_policy":
        known["pending_intent"] = "general_cancel_fee_policy"
        known["goal_type"] = "general_cancel_fee_policy"
        known["general_cancel_fee_policy"] = True
    if intent == "order_cancel_request":
        known["pending_intent"] = "order_cancel_request"
        if "예약" in text:
            known["goal_type"] = "reservation_management"
            known["reservation_management_action"] = "cancel_request"
            known["owned_record_target"] = "reservation"
        else:
            known["goal_type"] = "order_cancel_request"
        known["order_cancel_request"] = True
        if entities.get("order_no"):
            known["order_no"] = entities["order_no"]
    if intent in {"payment_method_change_request", "payment_account_info_lookup"}:
        known["pending_intent"] = intent
        known["goal_type"] = intent
        if entities.get("order_no"):
            known["order_no"] = entities["order_no"]
        if entities.get("order_no_suffix"):
            known["order_no_suffix"] = entities["order_no_suffix"]
    if intent == "maintenance_history_lookup":
        known["pending_intent"] = "maintenance_history_lookup"
        known["goal_type"] = "maintenance_history_lookup"
        if entities.get("requested_service_item"):
            known["requested_service_item"] = entities["requested_service_item"]
    if intent == "order_history_lookup":
        known["pending_intent"] = "order_history_lookup"
        known["goal_type"] = "owned_record_lookup"
        known["owned_record_target"] = "order"
    if intent == "maintenance_history_access_policy":
        known["pending_intent"] = "maintenance_history_access_policy"
        known["goal_type"] = "maintenance_history_access_policy"
        known["maintenance_history_access_policy"] = True
    if intent == "order_history_reorder":
        known["pending_intent"] = "order_history_reorder"
        known["goal_type"] = "order_history_reorder"
        known["owned_record_target"] = "order"
    if intent == "vehicle_lookup":
        known["pending_intent"] = "vehicle_lookup"
        known["goal_type"] = "registered_vehicle_lookup"
        known["owned_record_target"] = "vehicle"
    if intent in {"plain_store_info_lookup", "store_holiday_lookup"}:
        known["pending_intent"] = intent
        known["goal_type"] = intent
        if entities.get("store_name"):
            known["store_name"] = entities["store_name"]
            known["shop_name"] = entities["store_name"]
    if intent == "stock_store_search":
        known["stock_check_mode"] = str(entities.get("stock_check_mode") or "inventory_only")
        if requested_cal_day:
            known["requested_cal_day"] = requested_cal_day
        if quantity:
            known["quantity"] = quantity
            known["ord_qty"] = quantity
    if intent == "quick_order_reservation" and selected_schedule_followup:
        known["pending_intent"] = "order"
        known["goal_type"] = "place_order"
    if intent == "quick_order_reservation" and entities.get("stock_to_purchase_continuation"):
        known["pending_intent"] = "order"
        known["goal_type"] = "place_order"
        known["stock_check_mode"] = "preview"
    if (
        plain_store_search
        and intent not in {"plain_store_info_lookup", "store_holiday_lookup"}
        and not current_has_product
        and not preserve_transaction_product_context
    ):
        for key in (
            "goods_no",
            "product_name",
            "pattern_name",
            "tire_size",
            "quantity",
            "ord_qty",
            "store_name",
            "shop_name",
            "shop_id",
        ):
            known.pop(key, None)
    else:
        known.update({
            **({"tire_size": tire_size} if tire_size else {}),
            **({"quantity": quantity, "ord_qty": quantity} if quantity else {}),
            **({"product_name": product_name} if product_name else {}),
            **({"store_name": store_name} if store_name else {}),
            **({"shop_name": store_name} if store_name else {}),
        })
    if (store_candidate_search or region_scope_product_continuation) and intent not in {
        "plain_store_info_lookup",
        "store_holiday_lookup",
    }:
        for key in ("shop_id", "shop_name", "store_name"):
            known.pop(key, None)
    if store_name and "store_exact_match" not in known and store_name in _KNOWN_UNVERIFIED_STORE_NAMES:
        known["store_exact_match"] = False

    if intent in {"quick_order_reservation", "quick_order_execute"}:
        flow_state = resolve_purchase_order_flow(intent=intent, known_slots=known)
        if flow_state is not None:
            missing_slots = flow_state.missing_slots

    return IntentFrame(
        domain=PolicyDomain.TRANSACTION,
        intent=intent,
        sub_intent=sub_intent,
        entities=entities,
        known_slots=known,
        missing_slots=missing_slots,
        confidence=0.88,
        source="transaction_intent_policy",
    )


def plan_transaction_tools(frame: IntentFrame) -> ToolPlan:
    """Return the preferred Transaction tool family for the intent frame."""
    action = _transaction_action(frame)
    action_required_slots = _action_required_slots(frame, action)
    if frame.intent == "vehicle_lookup":
        return ToolPlan(
            allowed_tools=("get_my_cars_tool",),
            preferred_tool="get_my_cars_tool",
            tool_args_patch={},
            metadata={"response_intent": "vehicle_lookup", "template": "listCar"},
        )
    if (
        frame.intent in {"stock_store_search", "quick_order_reservation"}
        and "tire_size" in action_required_slots
        and len(action_required_slots) > 1
        and not frame.known_slots.get("goods_no")
    ):
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "get_store_list_tool",
                "get_store_detail_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
            ),
            required_slots=action_required_slots,
            metadata={
                "response_intent": frame.intent,
                "action": action,
                "guard": "require_product_size_before_transaction",
            },
        )
    if frame.intent in {"stock_store_search", "stock_store_search_slot_fill_store"}:
        args = _slot_args(
            frame,
            "goods_no",
            "tire_size",
            "quantity",
            "region",
            "place_query",
            "store_name",
            "requested_cal_day",
            "shop_id",
            "shop_name",
        )
        stock_check_mode = str(frame.known_slots.get("stock_check_mode") or frame.entities.get("stock_check_mode") or "")
        selected_store_schedule_mode = str(
            frame.known_slots.get("schedule_mode")
            or frame.known_slots.get("inventory_mode")
            or ""
        ).strip()
        if stock_check_mode == "inventory_only":
            boundary = stock_inventory_store_lookup_tool_boundary(frame)
            return ToolPlan(
                allowed_tools=boundary["allowed_tools"],
                preferred_tool=boundary["preferred_tool"],
                tool_args_patch={**args, **boundary["tool_args_patch"]},
                forbidden_tools=(
                    "transaction_store_preview_tool",
                    "get_store_schedule_tool",
                    "preorder_with_null_required_fields",
                ),
                required_slots=action_required_slots,
                metadata={
                    "response_intent": "stock_store_search",
                    "stock_check_mode": "inventory_only",
                    "action": action,
                    "tool_boundary": "stock_inventory_store_lookup",
                },
            )
        if (
            frame.known_slots.get("shop_id")
            and selected_store_schedule_mode
            and str(frame.known_slots.get("source_tool") or "") == "transaction_store_preview_tool"
            and frame.known_slots.get("goods_no")
            and frame.known_slots.get("tire_size")
            and (frame.known_slots.get("ord_qty") or frame.known_slots.get("quantity"))
            and not (frame.known_slots.get("requested_cal_day") and frame.known_slots.get("rsv_hour"))
            and stock_check_mode in {"", "preview"}
        ):
            return ToolPlan(
                allowed_tools=("get_store_schedule_tool",),
                preferred_tool="get_store_schedule_tool",
                tool_args_patch={
                    "shop_id": str(frame.known_slots["shop_id"]),
                    "mode": selected_store_schedule_mode,
                },
                forbidden_tools=(
                    "transaction_store_preview_tool",
                    "get_store_inventory_tool",
                    "get_logistics_inventory_tool",
                    "get_store_list_tool",
                    "get_nearby_stores_tool",
                    "search_stores_tool",
                    "get_multi_store_schedule_tool",
                    "quick_order_tool",
                ),
                required_slots=(),
                metadata={
                    "response_intent": "stock_store_search",
                    "stock_check_mode": "preview",
                    "schedule_mode": selected_store_schedule_mode,
                    "action": action,
                },
            )
        if frame.entities.get("today_requested"):
            args["today_only"] = True
        return ToolPlan(
            allowed_tools=("transaction_store_preview_tool", "get_store_inventory_tool", "get_store_list_tool"),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "preorder_with_null_required_fields"),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "stock_store_search",
                "stock_check_mode": "preview",
                "action": action,
            },
        )

    if frame.intent == "store_schedule":
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_schedule_tool", "get_store_detail_tool"),
            preferred_tool="get_store_schedule_tool",
            tool_args_patch=_slot_args(frame, "store_name", "region"),
            forbidden_tools=("transaction_store_preview_tool",),
            required_slots=action_required_slots,
            metadata={"response_intent": "store_schedule", "action": action},
        )

    if frame.intent == "open_store_search":
        args = _slot_args(frame, "region", "limit", "requested_cal_day")
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
            args["place_query"] = frame.known_slots["region"]
        args["open_only"] = True
        return ToolPlan(
            allowed_tools=(
                "search_stores_complex_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "get_store_detail_tool",
            ),
            preferred_tool="search_stores_complex_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "get_multi_store_schedule_tool", "transaction_store_preview_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "open_store_search", "action": action},
        )

    if frame.intent == "store_search":
        args = _slot_args(frame, "store_name", "limit")
        if frame.known_slots.get("place_query"):
            args["place_query"] = frame.known_slots["place_query"]
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
        if not args.get("place_query") and frame.entities.get("nearby") and frame.known_slots.get("region"):
            args["place_query"] = frame.known_slots["region"]
        return ToolPlan(
            allowed_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            preferred_tool="search_stores_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "transaction_store_preview_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "store_search", "action": action},
        )

    if frame.intent == "store_service_search":
        args = _slot_args(frame, "region", "limit")
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
            args["place_query"] = frame.known_slots["region"]
        service_codes = tuple(frame.known_slots.get("service_codes") or frame.entities.get("service_codes") or ())
        if service_codes:
            args["svc_codes"] = list(service_codes)
        return ToolPlan(
            allowed_tools=("search_stores_tool", "get_store_list_tool"),
            preferred_tool="search_stores_tool",
            tool_args_patch=args,
            forbidden_tools=("get_store_schedule_tool", "transaction_store_preview_tool", "quick_order_tool"),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "store_service_search",
                "action": action,
                "service_name": frame.known_slots.get("service_name") or frame.entities.get("service_name"),
                "service_codes": service_codes,
            },
        )

    if frame.intent == "store_recommendation_by_vehicle_experience":
        args = _slot_args(frame, "region", "limit", "requested_vehicle_experience")
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
            args["place_query"] = frame.known_slots.get("place_query") or frame.known_slots["region"]
        condition = str(
            frame.known_slots.get("requested_vehicle_experience")
            or frame.entities.get("requested_vehicle_experience")
            or ""
        ).strip()
        if condition:
            args["keyword"] = condition
        return ToolPlan(
            allowed_tools=("search_stores_complex_tool", "search_stores_tool", "get_store_list_tool"),
            preferred_tool="search_stores_complex_tool",
            tool_args_patch=args,
            forbidden_tools=(
                "quick_order_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
                "get_logistics_inventory_tool",
                "get_multi_store_schedule_tool",
            ),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "store_recommendation_by_vehicle_experience",
                "action": action,
                "tool_boundary": "store_search",
                "store_search_condition": "vehicle_experience",
                "requested_vehicle_experience": condition,
            },
        )

    if frame.intent == "unsupported_or_unmapped_store_service_policy":
        args = _slot_args(frame, "store_name", "region")
        if frame.known_slots.get("region"):
            args["region_code"] = frame.known_slots["region"]
            args["place_query"] = frame.known_slots.get("place_query") or frame.known_slots["region"]
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_detail_tool"),
            preferred_tool="get_store_list_tool" if frame.known_slots.get("store_name") else None,
            tool_args_patch=args,
            forbidden_tools=(
                "search_stores_tool",
                "transaction_store_preview_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "quick_order_tool",
            ),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "unsupported_or_unmapped_store_service_policy",
                "action": action,
                "service_name": frame.known_slots.get("service_name") or frame.entities.get("service_name"),
                "service_codes": tuple(frame.known_slots.get("service_codes") or frame.entities.get("service_codes") or ()),
            },
        )

    if frame.intent == "favorite_store_lookup":
        return ToolPlan(
            allowed_tools=("get_favorite_stores_tool",),
            preferred_tool="get_favorite_stores_tool",
            tool_args_patch={},
            forbidden_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "favorite_store_lookup", "action": action},
        )

    if frame.intent == "reservation_store_info_lookup":
        return ToolPlan(
            allowed_tools=("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool="get_my_reservations_tool",
            tool_args_patch={"sct_cd": "all"},
            forbidden_tools=("search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "reservation_store_info_lookup", "action": action},
        )

    if frame.intent == "reservation_status_lookup":
        return ToolPlan(
            allowed_tools=("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool="get_my_reservations_tool",
            tool_args_patch={"sct_cd": "all"},
            forbidden_tools=(
                "search_product_tool",
                "get_products_recommendations_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "get_nearby_stores_tool",
                "transaction_store_preview_tool",
                "get_store_schedule_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "reservation_status_lookup", "action": action},
        )

    if frame.intent == "reservation_change_request":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "quick_order_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
                "get_logistics_inventory_tool",
                "search_stores_tool",
                "get_store_list_tool",
            ),
            required_slots=(),
            metadata={
                "response_intent": "reservation_change_request",
                "action": action,
                "reservation_management_action": "change_request",
            },
        )

    if frame.intent == "order_arrival_status_lookup":
        return ToolPlan(
            allowed_tools=("get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool="get_orders_of_user_tool",
            tool_args_patch={},
            forbidden_tools=(
                "search_faq_hybrid_tool",
                "get_store_schedule_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "transaction_store_preview_tool",
                "quick_order_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "order_arrival_status_lookup", "action": action},
        )

    if frame.intent == "delivery_delay_reservation_schedule_policy":
        return ToolPlan(
            allowed_tools=("search_faq_hybrid_tool",),
            preferred_tool="search_faq_hybrid_tool",
            tool_args_patch={},
            forbidden_tools=(
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "delivery_delay_reservation_schedule_policy", "action": action},
        )

    if frame.intent == "reservation_window_policy":
        return ToolPlan(
            allowed_tools=("search_faq_hybrid_tool",),
            preferred_tool="search_faq_hybrid_tool",
            tool_args_patch={},
            forbidden_tools=(
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "transaction_store_preview_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "quick_order_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "reservation_window_policy", "action": action},
        )

    if frame.intent == "order_cancel_status_lookup":
        order_no = str(frame.known_slots.get("order_no") or frame.entities.get("order_no") or "").strip()
        return ToolPlan(
            allowed_tools=("get_order_status_tool", "get_orders_of_user_tool"),
            preferred_tool="get_order_status_tool" if order_no else "get_orders_of_user_tool",
            tool_args_patch={"query_no": order_no} if order_no else {},
            forbidden_tools=(
                "search_faq_hybrid_tool",
                "get_store_schedule_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "transaction_store_preview_tool",
                "quick_order_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "order_cancel_status_lookup", "action": action},
        )

    if frame.intent == "general_card_cancel_timing_policy":
        return ToolPlan(
            allowed_tools=("search_faq_hybrid_tool",),
            preferred_tool="search_faq_hybrid_tool",
            tool_args_patch={},
            forbidden_tools=(
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_my_reservations_tool",
                "quick_order_tool",
                "get_store_schedule_tool",
                "search_stores_tool",
                "get_store_list_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "general_card_cancel_timing_policy", "action": action},
        )

    if frame.intent == "owned_order_cancel_fee_inquiry":
        order_no = str(frame.known_slots.get("order_no") or frame.entities.get("order_no") or "").strip()
        reservation_anchor = (
            str(frame.known_slots.get("owned_anchor_target") or frame.entities.get("owned_anchor_target") or "") == "reservation"
        )
        return ToolPlan(
            allowed_tools=("get_my_reservations_tool", "get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool=(
                "get_order_status_tool"
                if order_no
                else "get_my_reservations_tool"
                if reservation_anchor
                else "get_orders_of_user_tool"
            ),
            tool_args_patch={"query_no": order_no} if order_no else {},
            forbidden_tools=(
                "search_faq_hybrid_tool",
                "get_store_schedule_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "quick_order_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "owned_order_cancel_fee_inquiry", "action": action},
        )

    if frame.intent == "general_cancel_fee_policy":
        return ToolPlan(
            allowed_tools=("search_faq_hybrid_tool",),
            preferred_tool="search_faq_hybrid_tool",
            tool_args_patch={},
            forbidden_tools=(
                "get_my_reservations_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_store_schedule_tool",
                "search_stores_tool",
                "get_store_list_tool",
                "quick_order_tool",
            ),
            required_slots=action_required_slots,
            metadata={"response_intent": "general_cancel_fee_policy", "action": action},
        )

    if frame.intent == "order_cancel_request":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "quick_order_tool",
                "get_store_schedule_tool",
                "get_multi_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_store_inventory_tool",
                "get_logistics_inventory_tool",
                "get_orders_of_user_tool",
                "get_order_status_tool",
                "get_my_reservations_tool",
                "direct_cancel_processing_tool",
                "get_order_cancel_tool",
            ),
            required_slots=(),
            metadata={
                "response_intent": "order_cancel_request",
                "action": action,
                **(
                    {"reservation_management_action": "cancel_request"}
                    if frame.known_slots.get("reservation_management_action") == "cancel_request"
                    else {}
                ),
            },
        )

    if frame.intent in {"payment_method_change_request", "payment_account_info_lookup"}:
        return ToolPlan(
            allowed_tools=("get_orders_of_user_tool", "get_order_status_tool"),
            preferred_tool="get_orders_of_user_tool",
            tool_args_patch={},
            forbidden_tools=(
                "search_faq_hybrid_tool",
                "quick_order_tool",
                "preorder_with_null_required_fields",
                "payment_method_direct_change_tool",
                "arbitrary_order_selection",
            ),
            required_slots=(),
            metadata={"response_intent": frame.intent, "action": action},
        )

    if frame.intent == "maintenance_history_lookup":
        return ToolPlan(
            allowed_tools=("get_maintenance_history_tool",),
            preferred_tool="get_maintenance_history_tool",
            tool_args_patch={"limit": 5},
            forbidden_tools=("get_products_recommendations_tool", "search_product_tool", "get_orders_of_user_tool"),
            required_slots=(),
            metadata={
                "response_intent": "maintenance_history_lookup",
                "action": action,
                **(
                    {"requested_service_item": frame.known_slots["requested_service_item"]}
                    if frame.known_slots.get("requested_service_item")
                    else {}
                ),
            },
        )

    if frame.intent == "order_history_lookup":
        return ToolPlan(
            allowed_tools=("get_orders_of_user_tool",),
            preferred_tool="get_orders_of_user_tool",
            tool_args_patch={},
            forbidden_tools=(
                "quick_order_tool",
                "search_product_tool",
                "get_final_price_tool",
                "transaction_store_preview_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "order_history_lookup", "action": action},
        )

    if frame.intent == "order_history_reorder":
        return ToolPlan(
            allowed_tools=("get_orders_of_user_tool",),
            preferred_tool="get_orders_of_user_tool",
            tool_args_patch={},
            forbidden_tools=(
                "search_product_tool",
                "get_products_recommendations_tool",
                "quick_order_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "order_history_reorder", "action": action},
        )

    if frame.intent in {"plain_store_info_lookup", "store_holiday_lookup"}:
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_detail_tool"),
            preferred_tool="get_store_list_tool",
            tool_args_patch=_slot_args(frame, "store_name", "shop_id"),
            forbidden_tools=(
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "quick_order_tool",
                "get_store_inventory_tool",
            ),
            required_slots=(),
            metadata={"response_intent": frame.intent, "action": action},
        )

    if frame.intent == "maintenance_history_access_policy":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "get_maintenance_history_tool",
                "get_orders_of_user_tool",
                "get_products_recommendations_tool",
                "search_product_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "maintenance_history_access_policy", "action": action},
        )

    if frame.intent == "service_duration_advisory":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=("get_store_schedule_tool", "get_store_detail_tool", "transaction_store_preview_tool"),
            required_slots=(),
            metadata={"response_intent": "service_duration_advisory", "action": action},
        )

    if frame.intent == "store_visit_advisory":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=("get_store_schedule_tool", "get_multi_store_schedule_tool", "transaction_store_preview_tool"),
            required_slots=(),
            metadata={"response_intent": "store_visit_advisory", "action": action},
        )

    if frame.intent == "maintenance_addon_with_tire_service":
        service_boundary = str(frame.known_slots.get("service_action_boundary") or "").strip()
        if service_boundary != "store_verification":
            return ToolPlan(
                allowed_tools=("search_faq_hybrid_tool",),
                preferred_tool="search_faq_hybrid_tool",
                tool_args_patch={},
                forbidden_tools=(
                    "get_store_list_tool",
                    "get_store_detail_tool",
                    "get_store_schedule_tool",
                    "transaction_store_preview_tool",
                    "get_maintenance_dday_tool",
                    "get_products_recommendations_tool",
                ),
                required_slots=(),
                metadata={
                    "response_intent": "maintenance_addon_with_tire_service",
                    "action": action,
                    "service_action_boundary": service_boundary or "service_booking_support",
                },
            )
        return ToolPlan(
            allowed_tools=("get_store_list_tool", "get_store_detail_tool"),
            preferred_tool="get_store_list_tool",
            tool_args_patch=_slot_args(frame, "store_name", "shop_id"),
            forbidden_tools=(
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "get_maintenance_dday_tool",
            ),
            required_slots=action_required_slots,
            metadata={
                "response_intent": "maintenance_addon_with_tire_service",
                "action": action,
                "service_action_boundary": "store_verification",
            },
        )

    if frame.intent in {"store_attribute_inquiry", "store_service_availability"}:
        if frame.known_slots.get("store_name") or frame.known_slots.get("shop_name") or frame.known_slots.get("shop_id"):
            return ToolPlan(
                allowed_tools=("get_store_list_tool", "get_store_detail_tool"),
                preferred_tool="get_store_list_tool",
                tool_args_patch=_slot_args(frame, "store_name", "shop_id"),
                forbidden_tools=(
                    "search_stores_tool",
                    "get_store_schedule_tool",
                    "transaction_store_preview_tool",
                    "preorder_with_null_required_fields",
                ),
                required_slots=(),
                metadata={"response_intent": "store_attribute_inquiry", "action": action},
            )
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "search_stores_tool",
                "get_store_list_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "preorder_with_null_required_fields",
            ),
            required_slots=(),
            metadata={"response_intent": "store_attribute_inquiry", "action": action},
        )

    if frame.intent == "store_service_advisory":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            tool_args_patch={},
            forbidden_tools=(
                "search_stores_tool",
                "get_store_list_tool",
                "get_store_schedule_tool",
                "transaction_store_preview_tool",
                "preorder_with_null_required_fields",
            ),
            required_slots=(),
            metadata={
                "response_intent": "store_service_advisory",
                "action": action,
                "service_name": frame.known_slots.get("service_name") or frame.entities.get("service_name"),
            },
        )

    if frame.intent in {"quick_order_reservation", "quick_order_reservation_continue"}:
        flow_state = resolve_purchase_order_flow(intent=frame.intent, known_slots=frame.known_slots)
        if flow_state is not None:
            return ToolPlan(
                allowed_tools=flow_state.allowed_tools,
                preferred_tool=flow_state.preferred_tool,
                tool_args_patch=dict(flow_state.slot_patch),
                forbidden_tools=flow_state.forbidden_tools,
                required_slots=flow_state.required_slots,
                metadata={
                    "response_intent": frame.intent,
                    "action": action,
                    "flow_id": flow_state.flow_id,
                    "flow_step": flow_state.flow_step,
                    "flow_slots": dict(flow_state.slot_patch),
                    "flow_missing_slots": list(flow_state.missing_slots),
                    "flow_response_shape_key": flow_state.response_shape_key,
                },
            )
        return ToolPlan(
            allowed_tools=(
                "search_product_tool",
                "transaction_store_preview_tool",
                "get_multi_store_schedule_tool",
                "get_store_schedule_tool",
            ),
            preferred_tool="transaction_store_preview_tool",
            tool_args_patch=_slot_args(
                frame, "goods_no", "tire_size", "quantity", "store_name", "region", "requested_cal_day"
            ),
            forbidden_tools=("store_hours_instead_of_slots", "order_summary_with_null_required_fields"),
            required_slots=action_required_slots,
            metadata={"response_intent": frame.intent, "action": action},
        )

    if frame.intent == "quick_order_execute":
        flow_state = resolve_purchase_order_flow(intent=frame.intent, known_slots=frame.known_slots)
        args = _slot_args(
            frame,
            "goods_no",
            "ord_qty",
            "quantity",
            "shop_id",
            "requested_cal_day",
            "rsv_hour",
            "car_lnc_cd",
            "payment_amount",
        )
        if flow_state is not None:
            return ToolPlan(
                allowed_tools=flow_state.allowed_tools,
                preferred_tool=flow_state.preferred_tool,
                tool_args_patch={**dict(flow_state.slot_patch), **args},
                forbidden_tools=flow_state.forbidden_tools,
                required_slots=flow_state.required_slots,
                metadata={
                    "response_intent": "quick_order_execute",
                    "action": action,
                    "flow_id": flow_state.flow_id,
                    "flow_step": flow_state.flow_step,
                    "flow_slots": {**dict(flow_state.slot_patch), **args},
                    "flow_missing_slots": list(flow_state.missing_slots),
                    "flow_response_shape_key": flow_state.response_shape_key,
                },
            )
        if action_required_slots:
            return ToolPlan(
                allowed_tools=(),
                preferred_tool=None,
                tool_args_patch=args,
                forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
                required_slots=action_required_slots,
                metadata={"response_intent": "quick_order_execute", "action": action},
            )
        return ToolPlan(
            allowed_tools=("quick_order_tool",),
            preferred_tool="quick_order_tool",
            tool_args_patch=args,
            forbidden_tools=("transaction_store_preview_tool", "get_store_schedule_tool"),
            required_slots=action_required_slots,
            metadata={"response_intent": "quick_order_execute", "action": action},
        )

    if frame.intent == "price_or_coupon_check":
        return ToolPlan(
            allowed_tools=(
                "search_product_tool",
                "get_final_price_tool",
                "get_my_coupons_tool",
                "get_coupon_applicable_products_tool",
            ),
            preferred_tool="get_final_price_tool",
            tool_args_patch=_slot_args(frame, "goods_no", "tire_size", "quantity"),
            required_slots=action_required_slots,
            metadata={"response_intent": "price_or_coupon_check", "action": action},
        )

    if frame.intent == "price_or_benefit_alert_request":
        return ToolPlan(
            allowed_tools=(),
            preferred_tool=None,
            forbidden_tools=(
                "get_benefit_event_deal_list_tool",
                "get_events_tool",
                "get_deals_tool",
                "issue_coupon_tool",
                "create_price_alert_tool",
                "create_benefit_alert_tool",
            ),
            required_slots=(),
            metadata={"response_intent": "price_or_benefit_alert_request", "action": action},
        )

    return ToolPlan(required_slots=action_required_slots, metadata={"response_intent": frame.intent, "action": action})


def _transaction_action(frame: IntentFrame) -> str:
    if frame.intent == "stock_store_search":
        stock_check_mode = str(frame.known_slots.get("stock_check_mode") or frame.entities.get("stock_check_mode") or "")
        has_store = _has_action_store(frame)
        if stock_check_mode == "inventory_only":
            return "store_inventory_lookup"
        if (
            (frame.known_slots.get("region") and not has_store)
            or frame.known_slots.get("lat")
            or frame.known_slots.get("lng")
            or not has_store
        ):
            return "regional_install_availability_preview"
        return "selected_store_schedule"
    if frame.intent == "store_schedule":
        return "selected_store_schedule"
    if frame.intent == "open_store_search":
        return "open_store_filter"
    if frame.intent == "store_service_search":
        return "store_service_search"
    if frame.intent == "store_recommendation_by_vehicle_experience":
        return "vehicle_experience_store_search"
    if frame.intent == "unsupported_or_unmapped_store_service_policy":
        return "unsupported_or_unmapped_store_service_policy"
    if frame.intent == "store_service_advisory":
        return "store_service_advisory"
    if frame.intent == "service_duration_advisory":
        return "service_duration_advisory"
    if frame.intent == "store_visit_advisory":
        return "store_visit_advisory"
    if frame.intent == "maintenance_addon_with_tire_service":
        return "maintenance_addon_with_tire_service"
    if frame.intent in {"store_attribute_inquiry", "store_service_availability"}:
        return "store_attribute_inquiry"
    if frame.intent == "reservation_store_info_lookup":
        return "reservation_store_info_lookup"
    if frame.intent == "reservation_status_lookup":
        return "reservation_status_lookup"
    if frame.intent == "reservation_change_request":
        return "reservation_change_request"
    if frame.intent == "order_arrival_status_lookup":
        return "order_arrival_status_lookup"
    if frame.intent == "delivery_delay_reservation_schedule_policy":
        return "support_policy_answer"
    if frame.intent == "reservation_window_policy":
        return "support_policy_answer"
    if frame.intent == "order_cancel_status_lookup":
        return "order_cancel_status_lookup"
    if frame.intent == "general_card_cancel_timing_policy":
        return "support_policy_answer"
    if frame.intent == "owned_order_cancel_fee_inquiry":
        return "owned_order_cancel_fee_inquiry"
    if frame.intent == "general_cancel_fee_policy":
        return "general_cancel_fee_policy"
    if frame.intent == "order_cancel_request":
        return "order_cancel_request"
    if frame.intent == "maintenance_history_lookup":
        return "maintenance_history_lookup"
    if frame.intent == "maintenance_history_access_policy":
        return "maintenance_history_access_policy"
    return frame.intent or "transaction_fallback"


def _has_action_product(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("goods_no")
        or frame.known_slots.get("product_name")
        or frame.known_slots.get("tire_model")
        or frame.known_slots.get("pattern_name")
        or frame.known_slots.get("pending_product_name")
    )


def _has_action_location(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("region")
        or frame.known_slots.get("place")
        or frame.known_slots.get("place_query")
        or frame.known_slots.get("lat")
        or frame.known_slots.get("lng")
        or frame.known_slots.get("shop_id")
        or frame.known_slots.get("shop_name")
        or frame.known_slots.get("store_name")
    )


def _has_action_store(frame: IntentFrame) -> bool:
    return bool(frame.known_slots.get("shop_id") or frame.known_slots.get("shop_name") or frame.known_slots.get("store_name"))


def _has_action_date(frame: IntentFrame) -> bool:
    return bool(
        frame.known_slots.get("requested_cal_day")
        or frame.known_slots.get("availability_intent") == "today_install"
        or frame.entities.get("today_requested")
    )


def _action_required_slots(frame: IntentFrame, action: str) -> tuple[str, ...]:
    required: list[str] = []

    def add(slot: str, condition: bool) -> None:
        if condition and slot not in required:
            required.append(slot)

    if action == "regional_install_availability_preview":
        add("product", not _has_action_product(frame))
        add("tire_size", not (frame.known_slots.get("tire_size") or frame.known_slots.get("goods_no")))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("location", not (_has_action_location(frame) or frame.entities.get("today_install_candidate_scope")))
        add("requested_cal_day", not _has_action_date(frame))
    elif action == "store_inventory_lookup":
        add("product", not _has_action_product(frame))
        add("tire_size", not (frame.known_slots.get("tire_size") or frame.known_slots.get("goods_no")))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not _has_action_store(frame))
    elif action == "selected_store_schedule":
        add("store", not _has_action_store(frame))
        stock_context = bool(frame.known_slots.get("goods_no") or frame.known_slots.get("stock_check_mode") == "preview")
        if stock_context:
            add("product", not _has_action_product(frame))
            add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
    elif action == "quick_order_reservation":
        add("product", not frame.known_slots.get("goods_no"))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not (_has_action_store(frame) or frame.known_slots.get("region") or frame.known_slots.get("place")))
    elif action == "quick_order_execute":
        add("product", not frame.known_slots.get("goods_no"))
        add("quantity", not (frame.known_slots.get("quantity") or frame.known_slots.get("ord_qty")))
        add("store", not frame.known_slots.get("shop_id"))
        add("booking_datetime", not (frame.known_slots.get("requested_cal_day") and frame.known_slots.get("rsv_hour")))
    elif action == "maintenance_addon_with_tire_service":
        return ()
    elif action == "store_service_search":
        add("region", not frame.known_slots.get("region"))
    elif action == "vehicle_experience_store_search":
        add("region", not frame.known_slots.get("region"))
    elif action == "unsupported_or_unmapped_store_service_policy":
        return ()
    elif action == "store_service_availability":
        return ()
    elif action == "store_service_advisory":
        return ()
    elif action == "store_visit_advisory":
        return ()
    else:
        for slot in frame.missing_slots:
            add(slot, True)
    return tuple(required)


def _missing_slots_for_intent(
    *,
    intent: str,
    has_product: bool,
    goods_no: Any,
    tire_size: Any,
    quantity: Any,
    has_location: bool,
    has_store: bool,
    shop_id: Any = None,
    requested_cal_day: Any = None,
    rsv_hour: Any = None,
) -> tuple[str, ...]:
    missing: list[str] = []
    if intent == "stock_store_search":
        if not has_product:
            missing.append("product")
        if has_product and not goods_no and not tire_size:
            missing.append("tire_size")
        if has_product and not quantity:
            missing.append("quantity")
        if not has_location:
            missing.append("location")
    elif intent == "quick_order_reservation":
        if not (goods_no or tire_size):
            missing.append("tire_size")
        if not quantity:
            missing.append("quantity")
        if not (has_store or has_location):
            missing.append("store")
    elif intent == "quick_order_execute":
        if not goods_no:
            missing.append("product")
        if not quantity:
            missing.append("quantity")
        if not shop_id:
            missing.append("store")
        if not requested_cal_day or not rsv_hour:
            missing.append("booking_datetime")
    elif intent in ("store_schedule", "store_search", "open_store_search"):
        if not has_location:
            missing.append("store")
    elif intent in {"store_service_search", "store_recommendation_by_vehicle_experience"}:
        if not has_location:
            missing.append("region")
    elif intent == "unsupported_or_unmapped_store_service_policy":
        return ()
    return tuple(missing)


def _slot_args(frame: IntentFrame, *keys: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for key in keys:
        if key == "store_name":
            value = frame.known_slots.get("shop_name") or frame.known_slots.get("store_name")
        else:
            value = frame.known_slots.get(key)
        if value not in (None, ""):
            args[key] = value
    return args


def _vehicle_experience_store_search_condition(text: str, slots: Mapping[str, Any]) -> str:
    """Preserve the current-turn vehicle/service condition without turning it into a purchase slot."""

    requested = str(slots.get("requested_vehicle_experience") or "").strip()
    if requested:
        return requested
    compact = " ".join(str(text or "").split())
    if not compact:
        return "vehicle_experience"
    return compact[:120]


def stock_inventory_store_lookup_tool_boundary(frame: IntentFrame) -> dict[str, Any]:
    """Return the canonical stock inventory/store lookup tool boundary.

    This is intentionally policy-only. Callers may consume the returned ToolPlan
    values, but should not re-decide the allowed/preferred tool set in orchestration.
    """

    known_slots = frame.known_slots or {}
    entities = frame.entities or {}
    has_selected_store = bool(known_slots.get("shop_id"))
    store_name = str(known_slots.get("shop_name") or known_slots.get("store_name") or "").strip()
    region = str(known_slots.get("region") or "").strip()
    place_query = str(known_slots.get("place_query") or "").strip()
    nearby = bool(entities.get("nearby"))
    if not place_query and nearby and region:
        place_query = region

    preferred_tool = "get_store_inventory_tool"
    if not has_selected_store:
        if place_query and not store_name:
            preferred_tool = "search_stores_tool"
        elif store_name or region:
            preferred_tool = "get_store_list_tool"

    tool_args_patch = stock_inventory_store_lookup_tool_input(
        known_slots,
        preferred_tool=preferred_tool,
        nearby=nearby,
    )
    return {
        "allowed_tools": STOCK_INVENTORY_STORE_LOOKUP_ALLOWED_TOOLS,
        "preferred_tool": preferred_tool,
        "tool_args_patch": tool_args_patch,
    }


def stock_inventory_store_lookup_tool_input(
    known_slots: Mapping[str, Any],
    *,
    preferred_tool: str | None,
    nearby: bool = False,
) -> dict[str, Any]:
    """Build canonical tool input for the stock inventory store-resolution step."""

    store_name = str(known_slots.get("shop_name") or known_slots.get("store_name") or "").strip()
    region = str(known_slots.get("region") or "").strip()
    place_query = str(known_slots.get("place_query") or "").strip()
    if not place_query and nearby and region:
        place_query = region

    preferred = str(preferred_tool or "").strip()
    tool_input: dict[str, Any] = {"limit": 10}
    if preferred == "search_stores_tool":
        if place_query or region:
            tool_input["place_query"] = place_query or region
        elif store_name:
            tool_input["store_nm"] = store_name
        return tool_input if len(tool_input) > 1 else {}
    if preferred == "get_store_list_tool":
        if store_name:
            tool_input["store_nm"] = store_name
        if region:
            tool_input["region_code"] = region
        return tool_input if len(tool_input) > 1 else {}
    return {}


def _extract_store_name(text: str) -> str | None:
    store_name = extract_valid_store_name(text or "")
    if not store_name:
        return None
    return re.sub(r"^(?:티스테이션|더타이어샵)\s*", "", store_name, flags=re.IGNORECASE).strip()


def _extract_product_name(text: str) -> str | None:
    normalized = (text or "").casefold()
    for needle, display_name in _PRODUCT_ALIASES:
        if needle.casefold() in normalized:
            return display_name
    return None


def _extract_region(text: str) -> str | None:
    match = _REGION_HINT_RE.search(text or "")
    if not match:
        return None
    return match.group(1)
