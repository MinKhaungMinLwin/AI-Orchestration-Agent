from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.store_list_response import StoreListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    region_code: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_region_code: None | str | Unset
    if isinstance(region_code, Unset):
        json_region_code = UNSET
    else:
        json_region_code = region_code
    params["region_code"] = json_region_code

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/store/list",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreListResponse | None:
    if response.status_code == 200:
        response_200 = StoreListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | StoreListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    region_code: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | StoreListResponse]:
    """매장 목록 조회

     지역명(도로명주소 LIKE 검색) 기준으로 매장 목록을 반환합니다. region_code 미입력 시 전체 조회.

    Args:
        region_code (None | str | Unset): 지역 검색어 (ROAD_ADDR_BASE LIKE 검색, 예: '서울', '강남')
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreListResponse]
    """

    kwargs = _get_kwargs(
        region_code=region_code,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    region_code: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | StoreListResponse | None:
    """매장 목록 조회

     지역명(도로명주소 LIKE 검색) 기준으로 매장 목록을 반환합니다. region_code 미입력 시 전체 조회.

    Args:
        region_code (None | str | Unset): 지역 검색어 (ROAD_ADDR_BASE LIKE 검색, 예: '서울', '강남')
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreListResponse
    """

    return sync_detailed(
        client=client,
        region_code=region_code,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    region_code: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | StoreListResponse]:
    """매장 목록 조회

     지역명(도로명주소 LIKE 검색) 기준으로 매장 목록을 반환합니다. region_code 미입력 시 전체 조회.

    Args:
        region_code (None | str | Unset): 지역 검색어 (ROAD_ADDR_BASE LIKE 검색, 예: '서울', '강남')
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreListResponse]
    """

    kwargs = _get_kwargs(
        region_code=region_code,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    region_code: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | StoreListResponse | None:
    """매장 목록 조회

     지역명(도로명주소 LIKE 검색) 기준으로 매장 목록을 반환합니다. region_code 미입력 시 전체 조회.

    Args:
        region_code (None | str | Unset): 지역 검색어 (ROAD_ADDR_BASE LIKE 검색, 예: '서울', '강남')
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            region_code=region_code,
            limit=limit,
        )
    ).parsed
