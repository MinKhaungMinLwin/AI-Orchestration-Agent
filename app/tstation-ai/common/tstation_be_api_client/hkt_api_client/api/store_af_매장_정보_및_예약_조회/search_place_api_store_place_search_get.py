from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.place_search_response import PlaceSearchResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    query: str,
    size: int | Unset = 10,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["query"] = query

    params["size"] = size

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/store/place-search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PlaceSearchResponse | None:
    if response.status_code == 200:
        response_200 = PlaceSearchResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | PlaceSearchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    query: str,
    size: int | Unset = 10,
) -> Response[HTTPValidationError | PlaceSearchResponse]:
    """위치 명칭 검색

     Kakao 키워드 검색 API를 이용하여 위치 명칭(건물명, 장소명 등)을 검색하고 좌표를 반환합니다.

    Args:
        query (str): 검색어 (예: 부산센텀시티, 강남역)
        size (int | Unset): 반환할 최대 결과 수 Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PlaceSearchResponse]
    """

    kwargs = _get_kwargs(
        query=query,
        size=size,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    query: str,
    size: int | Unset = 10,
) -> HTTPValidationError | PlaceSearchResponse | None:
    """위치 명칭 검색

     Kakao 키워드 검색 API를 이용하여 위치 명칭(건물명, 장소명 등)을 검색하고 좌표를 반환합니다.

    Args:
        query (str): 검색어 (예: 부산센텀시티, 강남역)
        size (int | Unset): 반환할 최대 결과 수 Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PlaceSearchResponse
    """

    return sync_detailed(
        client=client,
        query=query,
        size=size,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    query: str,
    size: int | Unset = 10,
) -> Response[HTTPValidationError | PlaceSearchResponse]:
    """위치 명칭 검색

     Kakao 키워드 검색 API를 이용하여 위치 명칭(건물명, 장소명 등)을 검색하고 좌표를 반환합니다.

    Args:
        query (str): 검색어 (예: 부산센텀시티, 강남역)
        size (int | Unset): 반환할 최대 결과 수 Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PlaceSearchResponse]
    """

    kwargs = _get_kwargs(
        query=query,
        size=size,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    query: str,
    size: int | Unset = 10,
) -> HTTPValidationError | PlaceSearchResponse | None:
    """위치 명칭 검색

     Kakao 키워드 검색 API를 이용하여 위치 명칭(건물명, 장소명 등)을 검색하고 좌표를 반환합니다.

    Args:
        query (str): 검색어 (예: 부산센텀시티, 강남역)
        size (int | Unset): 반환할 최대 결과 수 Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PlaceSearchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            query=query,
            size=size,
        )
    ).parsed
