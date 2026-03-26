from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.order_delivery_response import OrderDeliveryResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    query_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["query_no"] = query_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/orders/summary",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OrderDeliveryResponse | None:
    if response.status_code == 200:
        response_200 = OrderDeliveryResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | OrderDeliveryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    query_no: str,
) -> Response[HTTPValidationError | OrderDeliveryResponse]:
    """주문 및 배송 상태 조회

     조회번호가 O로 시작하면 주문번호 기준, D로 시작하면 배송번호 기준으로 주문/배송 정보를 함께 반환합니다.

    Args:
        query_no (str): 조회번호 (주문번호: O..., 배송번호: D...)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrderDeliveryResponse]
    """

    kwargs = _get_kwargs(
        query_no=query_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    query_no: str,
) -> HTTPValidationError | OrderDeliveryResponse | None:
    """주문 및 배송 상태 조회

     조회번호가 O로 시작하면 주문번호 기준, D로 시작하면 배송번호 기준으로 주문/배송 정보를 함께 반환합니다.

    Args:
        query_no (str): 조회번호 (주문번호: O..., 배송번호: D...)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrderDeliveryResponse
    """

    return sync_detailed(
        client=client,
        query_no=query_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    query_no: str,
) -> Response[HTTPValidationError | OrderDeliveryResponse]:
    """주문 및 배송 상태 조회

     조회번호가 O로 시작하면 주문번호 기준, D로 시작하면 배송번호 기준으로 주문/배송 정보를 함께 반환합니다.

    Args:
        query_no (str): 조회번호 (주문번호: O..., 배송번호: D...)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrderDeliveryResponse]
    """

    kwargs = _get_kwargs(
        query_no=query_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    query_no: str,
) -> HTTPValidationError | OrderDeliveryResponse | None:
    """주문 및 배송 상태 조회

     조회번호가 O로 시작하면 주문번호 기준, D로 시작하면 배송번호 기준으로 주문/배송 정보를 함께 반환합니다.

    Args:
        query_no (str): 조회번호 (주문번호: O..., 배송번호: D...)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrderDeliveryResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            query_no=query_no,
        )
    ).parsed
