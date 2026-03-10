from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.price_response import PriceResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    goods_no: str,
    member_type: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["goods_no"] = goods_no

    json_member_type: None | str | Unset
    if isinstance(member_type, Unset):
        json_member_type = UNSET
    else:
        json_member_type = member_type
    params["member_type"] = json_member_type

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/prices/final",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PriceResponse | None:
    if response.status_code == 200:
        response_200 = PriceResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | PriceResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    goods_no: str,
    member_type: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PriceResponse]:
    """상품 가격 및 할인 조회

     상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), 공임비 및 오늘의 공임비를 반환합니다.
    (샘플번호: G000000314254)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)
        member_type (None | str | Unset): 회원 유형 (예: 'general', 'PARTNER')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PriceResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
        member_type=member_type,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    goods_no: str,
    member_type: None | str | Unset = UNSET,
) -> HTTPValidationError | PriceResponse | None:
    """상품 가격 및 할인 조회

     상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), 공임비 및 오늘의 공임비를 반환합니다.
    (샘플번호: G000000314254)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)
        member_type (None | str | Unset): 회원 유형 (예: 'general', 'PARTNER')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PriceResponse
    """

    return sync_detailed(
        client=client,
        goods_no=goods_no,
        member_type=member_type,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    goods_no: str,
    member_type: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | PriceResponse]:
    """상품 가격 및 할인 조회

     상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), 공임비 및 오늘의 공임비를 반환합니다.
    (샘플번호: G000000314254)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)
        member_type (None | str | Unset): 회원 유형 (예: 'general', 'PARTNER')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PriceResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
        member_type=member_type,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    goods_no: str,
    member_type: None | str | Unset = UNSET,
) -> HTTPValidationError | PriceResponse | None:
    """상품 가격 및 할인 조회

     상품 번호로 기본 판매가, 최대 혜택가(프로모션·쿠폰 적용), 공임비 및 오늘의 공임비를 반환합니다.
    (샘플번호: G000000314254)

    Args:
        goods_no (str): 상품 번호 (예: G000000314254)
        member_type (None | str | Unset): 회원 유형 (예: 'general', 'PARTNER')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PriceResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no=goods_no,
            member_type=member_type,
        )
    ).parsed
