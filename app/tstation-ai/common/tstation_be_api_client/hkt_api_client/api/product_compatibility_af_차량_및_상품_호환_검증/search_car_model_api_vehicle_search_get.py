from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.car_model_search_response import CarModelSearchResponse
from ...models.http_validation_error import HTTPValidationError
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
        "url": "/api/vehicle/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CarModelSearchResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CarModelSearchResponse.from_dict(response.json())

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
) -> Response[CarModelSearchResponse | HTTPValidationError]:
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
) -> Response[CarModelSearchResponse | HTTPValidationError]:
    """차량 모델 검색

     차량 모델명 키워드로 PR_CAR_BASE에서 차량을 검색합니다. alias 확장 지원.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: '소나타', '그랜저')
        limit (int | Unset): 반환할 최대 차량 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarModelSearchResponse | HTTPValidationError]
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
) -> CarModelSearchResponse | HTTPValidationError | None:
    """차량 모델 검색

     차량 모델명 키워드로 PR_CAR_BASE에서 차량을 검색합니다. alias 확장 지원.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: '소나타', '그랜저')
        limit (int | Unset): 반환할 최대 차량 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarModelSearchResponse | HTTPValidationError
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
) -> Response[CarModelSearchResponse | HTTPValidationError]:
    """차량 모델 검색

     차량 모델명 키워드로 PR_CAR_BASE에서 차량을 검색합니다. alias 확장 지원.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: '소나타', '그랜저')
        limit (int | Unset): 반환할 최대 차량 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarModelSearchResponse | HTTPValidationError]
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
) -> CarModelSearchResponse | HTTPValidationError | None:
    """차량 모델 검색

     차량 모델명 키워드로 PR_CAR_BASE에서 차량을 검색합니다. alias 확장 지원.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: '소나타', '그랜저')
        limit (int | Unset): 반환할 최대 차량 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarModelSearchResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            keyword=keyword,
            limit=limit,
        )
    ).parsed
