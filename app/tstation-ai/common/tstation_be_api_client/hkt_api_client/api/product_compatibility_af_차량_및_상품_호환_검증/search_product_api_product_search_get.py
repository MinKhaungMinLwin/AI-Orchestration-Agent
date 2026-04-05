from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_search_response import ProductSearchResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_keyword: None | str | Unset
    if isinstance(keyword, Unset):
        json_keyword = UNSET
    else:
        json_keyword = keyword
    params["keyword"] = json_keyword

    json_size: None | str | Unset
    if isinstance(size, Unset):
        json_size = UNSET
    else:
        json_size = size
    params["size"] = json_size

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductSearchResponse | None:
    if response.status_code == 200:
        response_200 = ProductSearchResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductSearchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        size=size,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductSearchResponse
    """

    return sync_detailed(
        client=client,
        keyword=keyword,
        size=size,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        size=size,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductSearchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            keyword=keyword,
            size=size,
            limit=limit,
        )
    ).parsed
