from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.schedule_mode import ScheduleMode
from ...models.store_schedule_response import StoreScheduleResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    shop_id: str,
    mode: ScheduleMode,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["shop_id"] = shop_id

    json_mode = mode.value
    params["mode"] = json_mode

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/store/schedule",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreScheduleResponse | None:
    if response.status_code == 200:
        response_200 = StoreScheduleResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | StoreScheduleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    mode: ScheduleMode,
) -> Response[HTTPValidationError | StoreScheduleResponse]:
    """매장 스케줄 (range-based) 조회

     재고 상태 조합에 따른 모드별 cal_day range 로 예약 가능 시간 슬롯을 반환합니다. 기존 /api/store/detail 이 단일 cal_day 를 조회하는 것과 달리,
    이 엔드포인트는 한 번의 호출로 해당 모드 range 내 모든 (cal_day, tm) 슬롯을 반환합니다.

    모드:
    - `today_only`: Flow 3.5 1순위 (todayShopArray O) — 오늘서비스만
    - `tna_only`: Flow 3.5 2순위 (tnaShopArray O) — T바로배송만
    - `logistics_only`: 매장재고 X + 물류재고 O — 일반배송만
    - `in_store_only`: 매장재고 O + 물류재고 X — 오늘 ∪ T바로배송
    - `in_store_logistics_combined`: 매장재고 O + 물류재고 O — 오늘 ∪ T바로배송 ∪ 일반배송
    - `general`: 타이어 미특정 단순 매장 방문 — SYSDATE ~ SYSDATE+30

    Args:
        shop_id (str): 매장 ID
        mode (ScheduleMode): 매장 스케줄 조회 모드.

            재고 상태 조합에 따라 backend 가 적용할 cal_day range 가 달라진다.

            | mode                          | 매핑                              | range
            |
            |-------------------------------|-----------------------------------|---------------------
            -------|
            | today_only                    | Flow 3.5 1순위 (todayShopArray O) | 오늘서비스 only
            |
            | tna_only                      | Flow 3.5 2순위 (tnaShopArray O)   | T바로배송 only
            |
            | logistics_only                | 매장재고 X + 물류재고 O           | 일반배송 only              |
            | in_store_only                 | 매장재고 O + 물류재고 X           | 오늘 ∪ T바로              |
            | in_store_logistics_combined   | 매장재고 O + 물류재고 O           | 오늘 ∪ T바로 ∪ 일반배송  |
            | general                       | 타이어 미특정 단순 매장 방문       | SYSDATE ~ SYSDATE+30       |

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreScheduleResponse]
    """

    kwargs = _get_kwargs(
        shop_id=shop_id,
        mode=mode,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    mode: ScheduleMode,
) -> HTTPValidationError | StoreScheduleResponse | None:
    """매장 스케줄 (range-based) 조회

     재고 상태 조합에 따른 모드별 cal_day range 로 예약 가능 시간 슬롯을 반환합니다. 기존 /api/store/detail 이 단일 cal_day 를 조회하는 것과 달리,
    이 엔드포인트는 한 번의 호출로 해당 모드 range 내 모든 (cal_day, tm) 슬롯을 반환합니다.

    모드:
    - `today_only`: Flow 3.5 1순위 (todayShopArray O) — 오늘서비스만
    - `tna_only`: Flow 3.5 2순위 (tnaShopArray O) — T바로배송만
    - `logistics_only`: 매장재고 X + 물류재고 O — 일반배송만
    - `in_store_only`: 매장재고 O + 물류재고 X — 오늘 ∪ T바로배송
    - `in_store_logistics_combined`: 매장재고 O + 물류재고 O — 오늘 ∪ T바로배송 ∪ 일반배송
    - `general`: 타이어 미특정 단순 매장 방문 — SYSDATE ~ SYSDATE+30

    Args:
        shop_id (str): 매장 ID
        mode (ScheduleMode): 매장 스케줄 조회 모드.

            재고 상태 조합에 따라 backend 가 적용할 cal_day range 가 달라진다.

            | mode                          | 매핑                              | range
            |
            |-------------------------------|-----------------------------------|---------------------
            -------|
            | today_only                    | Flow 3.5 1순위 (todayShopArray O) | 오늘서비스 only
            |
            | tna_only                      | Flow 3.5 2순위 (tnaShopArray O)   | T바로배송 only
            |
            | logistics_only                | 매장재고 X + 물류재고 O           | 일반배송 only              |
            | in_store_only                 | 매장재고 O + 물류재고 X           | 오늘 ∪ T바로              |
            | in_store_logistics_combined   | 매장재고 O + 물류재고 O           | 오늘 ∪ T바로 ∪ 일반배송  |
            | general                       | 타이어 미특정 단순 매장 방문       | SYSDATE ~ SYSDATE+30       |

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreScheduleResponse
    """

    return sync_detailed(
        client=client,
        shop_id=shop_id,
        mode=mode,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    mode: ScheduleMode,
) -> Response[HTTPValidationError | StoreScheduleResponse]:
    """매장 스케줄 (range-based) 조회

     재고 상태 조합에 따른 모드별 cal_day range 로 예약 가능 시간 슬롯을 반환합니다. 기존 /api/store/detail 이 단일 cal_day 를 조회하는 것과 달리,
    이 엔드포인트는 한 번의 호출로 해당 모드 range 내 모든 (cal_day, tm) 슬롯을 반환합니다.

    모드:
    - `today_only`: Flow 3.5 1순위 (todayShopArray O) — 오늘서비스만
    - `tna_only`: Flow 3.5 2순위 (tnaShopArray O) — T바로배송만
    - `logistics_only`: 매장재고 X + 물류재고 O — 일반배송만
    - `in_store_only`: 매장재고 O + 물류재고 X — 오늘 ∪ T바로배송
    - `in_store_logistics_combined`: 매장재고 O + 물류재고 O — 오늘 ∪ T바로배송 ∪ 일반배송
    - `general`: 타이어 미특정 단순 매장 방문 — SYSDATE ~ SYSDATE+30

    Args:
        shop_id (str): 매장 ID
        mode (ScheduleMode): 매장 스케줄 조회 모드.

            재고 상태 조합에 따라 backend 가 적용할 cal_day range 가 달라진다.

            | mode                          | 매핑                              | range
            |
            |-------------------------------|-----------------------------------|---------------------
            -------|
            | today_only                    | Flow 3.5 1순위 (todayShopArray O) | 오늘서비스 only
            |
            | tna_only                      | Flow 3.5 2순위 (tnaShopArray O)   | T바로배송 only
            |
            | logistics_only                | 매장재고 X + 물류재고 O           | 일반배송 only              |
            | in_store_only                 | 매장재고 O + 물류재고 X           | 오늘 ∪ T바로              |
            | in_store_logistics_combined   | 매장재고 O + 물류재고 O           | 오늘 ∪ T바로 ∪ 일반배송  |
            | general                       | 타이어 미특정 단순 매장 방문       | SYSDATE ~ SYSDATE+30       |

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreScheduleResponse]
    """

    kwargs = _get_kwargs(
        shop_id=shop_id,
        mode=mode,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    mode: ScheduleMode,
) -> HTTPValidationError | StoreScheduleResponse | None:
    """매장 스케줄 (range-based) 조회

     재고 상태 조합에 따른 모드별 cal_day range 로 예약 가능 시간 슬롯을 반환합니다. 기존 /api/store/detail 이 단일 cal_day 를 조회하는 것과 달리,
    이 엔드포인트는 한 번의 호출로 해당 모드 range 내 모든 (cal_day, tm) 슬롯을 반환합니다.

    모드:
    - `today_only`: Flow 3.5 1순위 (todayShopArray O) — 오늘서비스만
    - `tna_only`: Flow 3.5 2순위 (tnaShopArray O) — T바로배송만
    - `logistics_only`: 매장재고 X + 물류재고 O — 일반배송만
    - `in_store_only`: 매장재고 O + 물류재고 X — 오늘 ∪ T바로배송
    - `in_store_logistics_combined`: 매장재고 O + 물류재고 O — 오늘 ∪ T바로배송 ∪ 일반배송
    - `general`: 타이어 미특정 단순 매장 방문 — SYSDATE ~ SYSDATE+30

    Args:
        shop_id (str): 매장 ID
        mode (ScheduleMode): 매장 스케줄 조회 모드.

            재고 상태 조합에 따라 backend 가 적용할 cal_day range 가 달라진다.

            | mode                          | 매핑                              | range
            |
            |-------------------------------|-----------------------------------|---------------------
            -------|
            | today_only                    | Flow 3.5 1순위 (todayShopArray O) | 오늘서비스 only
            |
            | tna_only                      | Flow 3.5 2순위 (tnaShopArray O)   | T바로배송 only
            |
            | logistics_only                | 매장재고 X + 물류재고 O           | 일반배송 only              |
            | in_store_only                 | 매장재고 O + 물류재고 X           | 오늘 ∪ T바로              |
            | in_store_logistics_combined   | 매장재고 O + 물류재고 O           | 오늘 ∪ T바로 ∪ 일반배송  |
            | general                       | 타이어 미특정 단순 매장 방문       | SYSDATE ~ SYSDATE+30       |

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreScheduleResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            shop_id=shop_id,
            mode=mode,
        )
    ).parsed
