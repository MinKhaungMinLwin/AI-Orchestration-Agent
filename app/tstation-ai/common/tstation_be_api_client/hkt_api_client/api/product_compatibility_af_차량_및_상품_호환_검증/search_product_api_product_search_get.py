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
    keyword: str,
    limit: int | Unset = 20,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["keyword"] = keyword

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
    keyword: str,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')

    Args:
        keyword (str): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    keyword: str,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')

    Args:
        keyword (str): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
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
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    keyword: str,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')

    Args:
        keyword (str): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        limit (int | Unset): 반환할 최대 상품 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    keyword: str,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')

    Args:
        keyword (str): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
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
            limit=limit,
        )
    ).parsed
