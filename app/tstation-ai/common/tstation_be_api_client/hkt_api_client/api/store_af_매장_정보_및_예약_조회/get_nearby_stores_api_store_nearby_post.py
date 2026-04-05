from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.nearby_store_request import NearbyStoreRequest
from ...models.nearby_store_response import NearbyStoreResponse
from ...types import Response


def _get_kwargs(
    *,
    body: NearbyStoreRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/store/nearby",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | NearbyStoreResponse | None:
    if response.status_code == 200:
        response_200 = NearbyStoreResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | NearbyStoreResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: NearbyStoreRequest,
) -> Response[HTTPValidationError | NearbyStoreResponse]:
    """주변 매장 목록 조회

     고객 좌표 기준으로 지정 반경(기본 20km) 내 가까운 매장 목록과 거리(km)를 반환합니다.

    Args:
        body (NearbyStoreRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | NearbyStoreResponse]
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
    body: NearbyStoreRequest,
) -> HTTPValidationError | NearbyStoreResponse | None:
    """주변 매장 목록 조회

     고객 좌표 기준으로 지정 반경(기본 20km) 내 가까운 매장 목록과 거리(km)를 반환합니다.

    Args:
        body (NearbyStoreRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | NearbyStoreResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: NearbyStoreRequest,
) -> Response[HTTPValidationError | NearbyStoreResponse]:
    """주변 매장 목록 조회

     고객 좌표 기준으로 지정 반경(기본 20km) 내 가까운 매장 목록과 거리(km)를 반환합니다.

    Args:
        body (NearbyStoreRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | NearbyStoreResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: NearbyStoreRequest,
) -> HTTPValidationError | NearbyStoreResponse | None:
    """주변 매장 목록 조회

     고객 좌표 기준으로 지정 반경(기본 20km) 내 가까운 매장 목록과 거리(km)를 반환합니다.

    Args:
        body (NearbyStoreRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | NearbyStoreResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
