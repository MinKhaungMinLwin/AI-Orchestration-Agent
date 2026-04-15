from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.discount_price_response import DiscountPriceResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    goods_no_list: list[str],
    quantity: int,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_goods_no_list = goods_no_list

    params["goods_no_list"] = json_goods_no_list

    params["quantity"] = quantity

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/prices/discount-compare",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DiscountPriceResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DiscountPriceResponse.from_dict(response.json())

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
) -> Response[DiscountPriceResponse | HTTPValidationError]:
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
    quantity: int,
) -> Response[DiscountPriceResponse | HTTPValidationError]:
    """복수 상품 할인 가격 비교 조회

     복수 상품 번호와 수량을 입력하여 상품별 정가, 상품할인, 쿠폰할인, 최종 결제금액을 비교합니다. JWT 토큰의 affiliate_yn 값으로 일반/제휴 회원을 자동 구분합니다.
    최저가 상품 번호(cheapest_goods_no)를 함께 반환합니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000314254', 'G000000312692'])
        quantity (int): 수량

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscountPriceResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no_list=goods_no_list,
        quantity=quantity,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int,
) -> DiscountPriceResponse | HTTPValidationError | None:
    """복수 상품 할인 가격 비교 조회

     복수 상품 번호와 수량을 입력하여 상품별 정가, 상품할인, 쿠폰할인, 최종 결제금액을 비교합니다. JWT 토큰의 affiliate_yn 값으로 일반/제휴 회원을 자동 구분합니다.
    최저가 상품 번호(cheapest_goods_no)를 함께 반환합니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000314254', 'G000000312692'])
        quantity (int): 수량

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscountPriceResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        goods_no_list=goods_no_list,
        quantity=quantity,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int,
) -> Response[DiscountPriceResponse | HTTPValidationError]:
    """복수 상품 할인 가격 비교 조회

     복수 상품 번호와 수량을 입력하여 상품별 정가, 상품할인, 쿠폰할인, 최종 결제금액을 비교합니다. JWT 토큰의 affiliate_yn 값으로 일반/제휴 회원을 자동 구분합니다.
    최저가 상품 번호(cheapest_goods_no)를 함께 반환합니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000314254', 'G000000312692'])
        quantity (int): 수량

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscountPriceResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no_list=goods_no_list,
        quantity=quantity,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    goods_no_list: list[str],
    quantity: int,
) -> DiscountPriceResponse | HTTPValidationError | None:
    """복수 상품 할인 가격 비교 조회

     복수 상품 번호와 수량을 입력하여 상품별 정가, 상품할인, 쿠폰할인, 최종 결제금액을 비교합니다. JWT 토큰의 affiliate_yn 값으로 일반/제휴 회원을 자동 구분합니다.
    최저가 상품 번호(cheapest_goods_no)를 함께 반환합니다.

    Args:
        goods_no_list (list[str]): 상품 번호 목록 (예: ['G000000314254', 'G000000312692'])
        quantity (int): 수량

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscountPriceResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no_list=goods_no_list,
            quantity=quantity,
        )
    ).parsed
