from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.store_detail_response import StoreDetailResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    shop_id: str,
    cal_day: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["shop_id"] = shop_id

    params["cal_day"] = cal_day

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/store/detail",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreDetailResponse | None:
    if response.status_code == 200:
        response_200 = StoreDetailResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | StoreDetailResponse]:
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
    cal_day: str,
) -> Response[HTTPValidationError | StoreDetailResponse]:
    """매장 상세 정보 및 예약 가능 시간 조회

     매장 ID와 날짜를 기준으로 매장 정보와 예약 가능 시간 슬롯(시 단위)을 반환합니다.

    Args:
        shop_id (str): 매장 ID
        cal_day (str): 조회 날짜 (YYYYMMDD)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreDetailResponse]
    """

    kwargs = _get_kwargs(
        shop_id=shop_id,
        cal_day=cal_day,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    cal_day: str,
) -> HTTPValidationError | StoreDetailResponse | None:
    """매장 상세 정보 및 예약 가능 시간 조회

     매장 ID와 날짜를 기준으로 매장 정보와 예약 가능 시간 슬롯(시 단위)을 반환합니다.

    Args:
        shop_id (str): 매장 ID
        cal_day (str): 조회 날짜 (YYYYMMDD)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreDetailResponse
    """

    return sync_detailed(
        client=client,
        shop_id=shop_id,
        cal_day=cal_day,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    cal_day: str,
) -> Response[HTTPValidationError | StoreDetailResponse]:
    """매장 상세 정보 및 예약 가능 시간 조회

     매장 ID와 날짜를 기준으로 매장 정보와 예약 가능 시간 슬롯(시 단위)을 반환합니다.

    Args:
        shop_id (str): 매장 ID
        cal_day (str): 조회 날짜 (YYYYMMDD)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreDetailResponse]
    """

    kwargs = _get_kwargs(
        shop_id=shop_id,
        cal_day=cal_day,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    shop_id: str,
    cal_day: str,
) -> HTTPValidationError | StoreDetailResponse | None:
    """매장 상세 정보 및 예약 가능 시간 조회

     매장 ID와 날짜를 기준으로 매장 정보와 예약 가능 시간 슬롯(시 단위)을 반환합니다.

    Args:
        shop_id (str): 매장 ID
        cal_day (str): 조회 날짜 (YYYYMMDD)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreDetailResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            shop_id=shop_id,
            cal_day=cal_day,
        )
    ).parsed
