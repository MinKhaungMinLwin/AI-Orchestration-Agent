from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.quick_order_request import QuickOrderRequest
from ...models.quick_order_response import QuickOrderResponse
from ...types import Response


def _get_kwargs(
    *,
    body: QuickOrderRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/quick-order/draft",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | QuickOrderResponse | None:
    if response.status_code == 200:
        response_200 = QuickOrderResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | QuickOrderResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: QuickOrderRequest,
) -> Response[HTTPValidationError | QuickOrderResponse]:
    """퀵 쇼핑 / 주문서 초안 생성

     회원번호(MBR_NO) 또는 차량번호(CAR_NO)와 상품번호(GOODS_NO), 수량(ORD_QTY)을 입력받아 상품 유효성(PR_GOODS_BASE: 판매 상태, 최소 주문
    수량)을 검증한 뒤, 주문서 작성 페이지 URL(REDIRECT_URL)을 반환합니다.

    Args:
        body (QuickOrderRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | QuickOrderResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: QuickOrderRequest,
) -> HTTPValidationError | QuickOrderResponse | None:
    """퀵 쇼핑 / 주문서 초안 생성

     회원번호(MBR_NO) 또는 차량번호(CAR_NO)와 상품번호(GOODS_NO), 수량(ORD_QTY)을 입력받아 상품 유효성(PR_GOODS_BASE: 판매 상태, 최소 주문
    수량)을 검증한 뒤, 주문서 작성 페이지 URL(REDIRECT_URL)을 반환합니다.

    Args:
        body (QuickOrderRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | QuickOrderResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: QuickOrderRequest,
) -> Response[HTTPValidationError | QuickOrderResponse]:
    """퀵 쇼핑 / 주문서 초안 생성

     회원번호(MBR_NO) 또는 차량번호(CAR_NO)와 상품번호(GOODS_NO), 수량(ORD_QTY)을 입력받아 상품 유효성(PR_GOODS_BASE: 판매 상태, 최소 주문
    수량)을 검증한 뒤, 주문서 작성 페이지 URL(REDIRECT_URL)을 반환합니다.

    Args:
        body (QuickOrderRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | QuickOrderResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: QuickOrderRequest,
) -> HTTPValidationError | QuickOrderResponse | None:
    """퀵 쇼핑 / 주문서 초안 생성

     회원번호(MBR_NO) 또는 차량번호(CAR_NO)와 상품번호(GOODS_NO), 수량(ORD_QTY)을 입력받아 상품 유효성(PR_GOODS_BASE: 판매 상태, 최소 주문
    수량)을 검증한 뒤, 주문서 작성 페이지 URL(REDIRECT_URL)을 반환합니다.

    Args:
        body (QuickOrderRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | QuickOrderResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
