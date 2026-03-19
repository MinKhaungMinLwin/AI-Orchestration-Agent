from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.store_inventory_request import StoreInventoryRequest
from ...models.store_inventory_response import StoreInventoryResponse
from ...types import Response


def _get_kwargs(
    *,
    body: StoreInventoryRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/inventory/store",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreInventoryResponse | None:
    if response.status_code == 200:
        response_200 = StoreInventoryResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | StoreInventoryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: StoreInventoryRequest,
) -> Response[HTTPValidationError | StoreInventoryResponse]:
    """매장 재고 가용 여부 조회

     상품 목록과 매장 목록을 입력받아 오늘 장착 가능 매장(todayShopArray)과 T바로배송 가능 매장(tnaShopArray)을 반환합니다. (외부 API:
    getStockCheckShopList)

    Args:
        body (StoreInventoryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreInventoryResponse]
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
    client: AuthenticatedClient,
    body: StoreInventoryRequest,
) -> HTTPValidationError | StoreInventoryResponse | None:
    """매장 재고 가용 여부 조회

     상품 목록과 매장 목록을 입력받아 오늘 장착 가능 매장(todayShopArray)과 T바로배송 가능 매장(tnaShopArray)을 반환합니다. (외부 API:
    getStockCheckShopList)

    Args:
        body (StoreInventoryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreInventoryResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: StoreInventoryRequest,
) -> Response[HTTPValidationError | StoreInventoryResponse]:
    """매장 재고 가용 여부 조회

     상품 목록과 매장 목록을 입력받아 오늘 장착 가능 매장(todayShopArray)과 T바로배송 가능 매장(tnaShopArray)을 반환합니다. (외부 API:
    getStockCheckShopList)

    Args:
        body (StoreInventoryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreInventoryResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: StoreInventoryRequest,
) -> HTTPValidationError | StoreInventoryResponse | None:
    """매장 재고 가용 여부 조회

     상품 목록과 매장 목록을 입력받아 오늘 장착 가능 매장(todayShopArray)과 T바로배송 가능 매장(tnaShopArray)을 반환합니다. (외부 API:
    getStockCheckShopList)

    Args:
        body (StoreInventoryRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreInventoryResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
