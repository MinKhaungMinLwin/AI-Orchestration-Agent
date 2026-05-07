from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_deals_response import ProductDealsResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    goods_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["goods_no"] = goods_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/events/deals/by-product",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductDealsResponse | None:
    if response.status_code == 200:
        response_200 = ProductDealsResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductDealsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    goods_no: str,
) -> Response[HTTPValidationError | ProductDealsResponse]:
    """상품번호 기준 진행 중 기획전(쿠폰 포함) 조회

     특정 상품(goods_no)에 적용 가능한, 현재 진행 중인 기획전 목록과 각 기획전에 매핑된 활성 쿠폰을 함께 반환합니다. (전시기간/요일/적용시각, 쿠폰 종류 C301,
    진행상태 40 조건 적용)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductDealsResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    goods_no: str,
) -> HTTPValidationError | ProductDealsResponse | None:
    """상품번호 기준 진행 중 기획전(쿠폰 포함) 조회

     특정 상품(goods_no)에 적용 가능한, 현재 진행 중인 기획전 목록과 각 기획전에 매핑된 활성 쿠폰을 함께 반환합니다. (전시기간/요일/적용시각, 쿠폰 종류 C301,
    진행상태 40 조건 적용)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductDealsResponse
    """

    return sync_detailed(
        client=client,
        goods_no=goods_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    goods_no: str,
) -> Response[HTTPValidationError | ProductDealsResponse]:
    """상품번호 기준 진행 중 기획전(쿠폰 포함) 조회

     특정 상품(goods_no)에 적용 가능한, 현재 진행 중인 기획전 목록과 각 기획전에 매핑된 활성 쿠폰을 함께 반환합니다. (전시기간/요일/적용시각, 쿠폰 종류 C301,
    진행상태 40 조건 적용)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductDealsResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    goods_no: str,
) -> HTTPValidationError | ProductDealsResponse | None:
    """상품번호 기준 진행 중 기획전(쿠폰 포함) 조회

     특정 상품(goods_no)에 적용 가능한, 현재 진행 중인 기획전 목록과 각 기획전에 매핑된 활성 쿠폰을 함께 반환합니다. (전시기간/요일/적용시각, 쿠폰 종류 C301,
    진행상태 40 조건 적용)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductDealsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no=goods_no,
        )
    ).parsed
