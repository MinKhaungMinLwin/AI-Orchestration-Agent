from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cheapest_by_coupon_response import CheapestByCouponResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    goods_no_list: list[str],
    quantity: int | Unset = 1,
    shop_id: None | str | Unset = UNSET,
    channel: str | Unset = "web",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_goods_no_list = goods_no_list

    params["goods_no_list"] = json_goods_no_list

    params["quantity"] = quantity

    json_shop_id: None | str | Unset
    if isinstance(shop_id, Unset):
        json_shop_id = UNSET
    else:
        json_shop_id = shop_id
    params["shop_id"] = json_shop_id

    params["channel"] = channel

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/prices/cheapest-by-coupon",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CheapestByCouponResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CheapestByCouponResponse.from_dict(response.json())

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
) -> Response[CheapestByCouponResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int | Unset = 1,
    shop_id: None | str | Unset = UNSET,
    channel: str | Unset = "web",
) -> Response[CheapestByCouponResponse | HTTPValidationError]:
    """회원 보유 쿠폰 기반 상품별 최저가 시뮬레이션

     회원 보유 쿠폰을 상품→결제→플러스 순으로 그리디 적용하여 상품별 최종 혜택가를 계산합니다. 각 단계에서 적용 가능한 쿠폰 중 할인금액이 가장 큰 1개를 자동 선택합니다.
    상품쿠폰의 CPN_DUP_USE_YN='N' 이면 결제쿠폰 단계를 건너뜁니다. 여러 상품을 받아 각각 독립적으로 시뮬레이션합니다(여러 상품 중 1개를 고르는 것이 아님).
    회원번호/제휴사번호는 JWT 클레임에서, 매장 ID 와 채널은 query 로 받습니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000319449', 'G000000312692'])
        quantity (int | Unset): 구매 수량 (최저가 단순 조회면 1, 주문이면 사용자 선택 수량) Default: 1.
        shop_id (None | str | Unset): 매장 ID (선택 시 매장 단위 쿠폰 적용 가능 여부 반영)
        channel (str | Unset): 채널 (web→100, app→300) Default: 'web'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheapestByCouponResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no_list=goods_no_list,
        quantity=quantity,
        shop_id=shop_id,
        channel=channel,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int | Unset = 1,
    shop_id: None | str | Unset = UNSET,
    channel: str | Unset = "web",
) -> CheapestByCouponResponse | HTTPValidationError | None:
    """회원 보유 쿠폰 기반 상품별 최저가 시뮬레이션

     회원 보유 쿠폰을 상품→결제→플러스 순으로 그리디 적용하여 상품별 최종 혜택가를 계산합니다. 각 단계에서 적용 가능한 쿠폰 중 할인금액이 가장 큰 1개를 자동 선택합니다.
    상품쿠폰의 CPN_DUP_USE_YN='N' 이면 결제쿠폰 단계를 건너뜁니다. 여러 상품을 받아 각각 독립적으로 시뮬레이션합니다(여러 상품 중 1개를 고르는 것이 아님).
    회원번호/제휴사번호는 JWT 클레임에서, 매장 ID 와 채널은 query 로 받습니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000319449', 'G000000312692'])
        quantity (int | Unset): 구매 수량 (최저가 단순 조회면 1, 주문이면 사용자 선택 수량) Default: 1.
        shop_id (None | str | Unset): 매장 ID (선택 시 매장 단위 쿠폰 적용 가능 여부 반영)
        channel (str | Unset): 채널 (web→100, app→300) Default: 'web'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheapestByCouponResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        goods_no_list=goods_no_list,
        quantity=quantity,
        shop_id=shop_id,
        channel=channel,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int | Unset = 1,
    shop_id: None | str | Unset = UNSET,
    channel: str | Unset = "web",
) -> Response[CheapestByCouponResponse | HTTPValidationError]:
    """회원 보유 쿠폰 기반 상품별 최저가 시뮬레이션

     회원 보유 쿠폰을 상품→결제→플러스 순으로 그리디 적용하여 상품별 최종 혜택가를 계산합니다. 각 단계에서 적용 가능한 쿠폰 중 할인금액이 가장 큰 1개를 자동 선택합니다.
    상품쿠폰의 CPN_DUP_USE_YN='N' 이면 결제쿠폰 단계를 건너뜁니다. 여러 상품을 받아 각각 독립적으로 시뮬레이션합니다(여러 상품 중 1개를 고르는 것이 아님).
    회원번호/제휴사번호는 JWT 클레임에서, 매장 ID 와 채널은 query 로 받습니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000319449', 'G000000312692'])
        quantity (int | Unset): 구매 수량 (최저가 단순 조회면 1, 주문이면 사용자 선택 수량) Default: 1.
        shop_id (None | str | Unset): 매장 ID (선택 시 매장 단위 쿠폰 적용 가능 여부 반영)
        channel (str | Unset): 채널 (web→100, app→300) Default: 'web'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CheapestByCouponResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no_list=goods_no_list,
        quantity=quantity,
        shop_id=shop_id,
        channel=channel,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int | Unset = 1,
    shop_id: None | str | Unset = UNSET,
    channel: str | Unset = "web",
) -> CheapestByCouponResponse | HTTPValidationError | None:
    """회원 보유 쿠폰 기반 상품별 최저가 시뮬레이션

     회원 보유 쿠폰을 상품→결제→플러스 순으로 그리디 적용하여 상품별 최종 혜택가를 계산합니다. 각 단계에서 적용 가능한 쿠폰 중 할인금액이 가장 큰 1개를 자동 선택합니다.
    상품쿠폰의 CPN_DUP_USE_YN='N' 이면 결제쿠폰 단계를 건너뜁니다. 여러 상품을 받아 각각 독립적으로 시뮬레이션합니다(여러 상품 중 1개를 고르는 것이 아님).
    회원번호/제휴사번호는 JWT 클레임에서, 매장 ID 와 채널은 query 로 받습니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000319449', 'G000000312692'])
        quantity (int | Unset): 구매 수량 (최저가 단순 조회면 1, 주문이면 사용자 선택 수량) Default: 1.
        shop_id (None | str | Unset): 매장 ID (선택 시 매장 단위 쿠폰 적용 가능 여부 반영)
        channel (str | Unset): 채널 (web→100, app→300) Default: 'web'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CheapestByCouponResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no_list=goods_no_list,
            quantity=quantity,
            shop_id=shop_id,
            channel=channel,
        )
    ).parsed
