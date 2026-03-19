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
    ord_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["ord_no"] = ord_no

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
    ord_no: str,
) -> Response[HTTPValidationError | OrderDeliveryResponse]:
    """주문 및 배송 상태 조회

     주문 번호로 주문 진행 상태(OP_ORD_DTL_INFO)와 배송 진행 상태·운송장 정보(OP_ORD_DLV_DTL_INFO)를 함께 반환합니다.

    Args:
        ord_no (str): 주문 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrderDeliveryResponse]
    """

    kwargs = _get_kwargs(
        ord_no=ord_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    ord_no: str,
) -> HTTPValidationError | OrderDeliveryResponse | None:
    """주문 및 배송 상태 조회

     주문 번호로 주문 진행 상태(OP_ORD_DTL_INFO)와 배송 진행 상태·운송장 정보(OP_ORD_DLV_DTL_INFO)를 함께 반환합니다.

    Args:
        ord_no (str): 주문 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrderDeliveryResponse
    """

    return sync_detailed(
        client=client,
        ord_no=ord_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    ord_no: str,
) -> Response[HTTPValidationError | OrderDeliveryResponse]:
    """주문 및 배송 상태 조회

     주문 번호로 주문 진행 상태(OP_ORD_DTL_INFO)와 배송 진행 상태·운송장 정보(OP_ORD_DLV_DTL_INFO)를 함께 반환합니다.

    Args:
        ord_no (str): 주문 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrderDeliveryResponse]
    """

    kwargs = _get_kwargs(
        ord_no=ord_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    ord_no: str,
) -> HTTPValidationError | OrderDeliveryResponse | None:
    """주문 및 배송 상태 조회

     주문 번호로 주문 진행 상태(OP_ORD_DTL_INFO)와 배송 진행 상태·운송장 정보(OP_ORD_DLV_DTL_INFO)를 함께 반환합니다.

    Args:
        ord_no (str): 주문 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrderDeliveryResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            ord_no=ord_no,
        )
    ).parsed
