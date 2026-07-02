from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.best_seller_search_request import BestSellerSearchRequest
from ...models.best_seller_search_response import BestSellerSearchResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: BestSellerSearchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/product/best-sellers/search",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BestSellerSearchResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BestSellerSearchResponse.from_dict(response.json())

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
) -> Response[BestSellerSearchResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BestSellerSearchRequest,
) -> Response[BestSellerSearchResponse | HTTPValidationError]:
    """통합 베스트셀러 조회

     차종 없는 일반 베스트셀러, 차종별 베스트셀러, 기간 지정 베스트셀러를 하나의 API로 조회합니다. vehicle_query가 없으면 전체 주문 기준, 있으면 차량 해석 후 해당
    차량 계열 주문 기준으로 집계합니다.

    Args:
        body (BestSellerSearchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BestSellerSearchResponse | HTTPValidationError]
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
    body: BestSellerSearchRequest,
) -> BestSellerSearchResponse | HTTPValidationError | None:
    """통합 베스트셀러 조회

     차종 없는 일반 베스트셀러, 차종별 베스트셀러, 기간 지정 베스트셀러를 하나의 API로 조회합니다. vehicle_query가 없으면 전체 주문 기준, 있으면 차량 해석 후 해당
    차량 계열 주문 기준으로 집계합니다.

    Args:
        body (BestSellerSearchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BestSellerSearchResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BestSellerSearchRequest,
) -> Response[BestSellerSearchResponse | HTTPValidationError]:
    """통합 베스트셀러 조회

     차종 없는 일반 베스트셀러, 차종별 베스트셀러, 기간 지정 베스트셀러를 하나의 API로 조회합니다. vehicle_query가 없으면 전체 주문 기준, 있으면 차량 해석 후 해당
    차량 계열 주문 기준으로 집계합니다.

    Args:
        body (BestSellerSearchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BestSellerSearchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: BestSellerSearchRequest,
) -> BestSellerSearchResponse | HTTPValidationError | None:
    """통합 베스트셀러 조회

     차종 없는 일반 베스트셀러, 차종별 베스트셀러, 기간 지정 베스트셀러를 하나의 API로 조회합니다. vehicle_query가 없으면 전체 주문 기준, 있으면 차량 해석 후 해당
    차량 계열 주문 기준으로 집계합니다.

    Args:
        body (BestSellerSearchRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BestSellerSearchResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
