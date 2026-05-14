from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.best_seller_period import BestSellerPeriod
from ...models.best_seller_response import BestSellerResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    period: BestSellerPeriod | Unset = UNSET,
    limit: int | Unset = 5,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_period: str | Unset = UNSET
    if not isinstance(period, Unset):
        json_period = period.value

    params["period"] = json_period

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/best-sellers",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BestSellerResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BestSellerResponse.from_dict(response.json())

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
) -> Response[BestSellerResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    period: BestSellerPeriod | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[BestSellerResponse | HTTPValidationError]:
    """기간별 베스트셀러 상품 조회

     PR_GOODS_SUM 의 일/주/월/3개월별 판매 수량 컬럼을 기준으로 정렬해 가장 많이 팔린 상품을 반환합니다. 사용자가 '요즘 / 최근' 같은 모호한 표현을 쓰면 호출 측에서
    month 로 매핑하세요.

    Args:
        period (BestSellerPeriod | Unset): 판매 기간 구분. PR_GOODS_SUM 컬럼과 매핑.
        limit (int | Unset): 반환할 상품 수 (1-50, 기본 5) Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BestSellerResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        period=period,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    period: BestSellerPeriod | Unset = UNSET,
    limit: int | Unset = 5,
) -> BestSellerResponse | HTTPValidationError | None:
    """기간별 베스트셀러 상품 조회

     PR_GOODS_SUM 의 일/주/월/3개월별 판매 수량 컬럼을 기준으로 정렬해 가장 많이 팔린 상품을 반환합니다. 사용자가 '요즘 / 최근' 같은 모호한 표현을 쓰면 호출 측에서
    month 로 매핑하세요.

    Args:
        period (BestSellerPeriod | Unset): 판매 기간 구분. PR_GOODS_SUM 컬럼과 매핑.
        limit (int | Unset): 반환할 상품 수 (1-50, 기본 5) Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BestSellerResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        period=period,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    period: BestSellerPeriod | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[BestSellerResponse | HTTPValidationError]:
    """기간별 베스트셀러 상품 조회

     PR_GOODS_SUM 의 일/주/월/3개월별 판매 수량 컬럼을 기준으로 정렬해 가장 많이 팔린 상품을 반환합니다. 사용자가 '요즘 / 최근' 같은 모호한 표현을 쓰면 호출 측에서
    month 로 매핑하세요.

    Args:
        period (BestSellerPeriod | Unset): 판매 기간 구분. PR_GOODS_SUM 컬럼과 매핑.
        limit (int | Unset): 반환할 상품 수 (1-50, 기본 5) Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BestSellerResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        period=period,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    period: BestSellerPeriod | Unset = UNSET,
    limit: int | Unset = 5,
) -> BestSellerResponse | HTTPValidationError | None:
    """기간별 베스트셀러 상품 조회

     PR_GOODS_SUM 의 일/주/월/3개월별 판매 수량 컬럼을 기준으로 정렬해 가장 많이 팔린 상품을 반환합니다. 사용자가 '요즘 / 최근' 같은 모호한 표현을 쓰면 호출 측에서
    month 로 매핑하세요.

    Args:
        period (BestSellerPeriod | Unset): 판매 기간 구분. PR_GOODS_SUM 컬럼과 매핑.
        limit (int | Unset): 반환할 상품 수 (1-50, 기본 5) Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BestSellerResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            period=period,
            limit=limit,
        )
    ).parsed
