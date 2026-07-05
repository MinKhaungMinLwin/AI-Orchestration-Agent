from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.benefit_applicable_products_search_response import BenefitApplicableProductsSearchResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    query: str,
    lang_cd: str | Unset = "ko",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["query"] = query

    params["lang_cd"] = lang_cd

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/benefits/applicable-products/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BenefitApplicableProductsSearchResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BenefitApplicableProductsSearchResponse.from_dict(response.json())

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
) -> Response[BenefitApplicableProductsSearchResponse | HTTPValidationError]:
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
    lang_cd: str | Unset = "ko",
) -> Response[BenefitApplicableProductsSearchResponse | HTTPValidationError]:
    """쿠폰/이벤트/기획전 통합 적용 상품 검색

     검색어(query)를 기준으로 사용자의 보유 쿠폰, 현재 전시 중인 이벤트, 현재 전시 중인 기획전을 모두 검색한 뒤 매칭된 혜택별 적용 가능한 대표 상품과 매장을 반환합니다.
    차량/규격 기반 상품 검색은 포함하지 않습니다.

    Args:
        query (str): 혜택명/쿠폰명/이벤트명/기획전명 검색어
        lang_cd (str | Unset): 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BenefitApplicableProductsSearchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        query=query,
        lang_cd=lang_cd,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    query: str,
    lang_cd: str | Unset = "ko",
) -> BenefitApplicableProductsSearchResponse | HTTPValidationError | None:
    """쿠폰/이벤트/기획전 통합 적용 상품 검색

     검색어(query)를 기준으로 사용자의 보유 쿠폰, 현재 전시 중인 이벤트, 현재 전시 중인 기획전을 모두 검색한 뒤 매칭된 혜택별 적용 가능한 대표 상품과 매장을 반환합니다.
    차량/규격 기반 상품 검색은 포함하지 않습니다.

    Args:
        query (str): 혜택명/쿠폰명/이벤트명/기획전명 검색어
        lang_cd (str | Unset): 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BenefitApplicableProductsSearchResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        query=query,
        lang_cd=lang_cd,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    query: str,
    lang_cd: str | Unset = "ko",
) -> Response[BenefitApplicableProductsSearchResponse | HTTPValidationError]:
    """쿠폰/이벤트/기획전 통합 적용 상품 검색

     검색어(query)를 기준으로 사용자의 보유 쿠폰, 현재 전시 중인 이벤트, 현재 전시 중인 기획전을 모두 검색한 뒤 매칭된 혜택별 적용 가능한 대표 상품과 매장을 반환합니다.
    차량/규격 기반 상품 검색은 포함하지 않습니다.

    Args:
        query (str): 혜택명/쿠폰명/이벤트명/기획전명 검색어
        lang_cd (str | Unset): 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BenefitApplicableProductsSearchResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        query=query,
        lang_cd=lang_cd,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    query: str,
    lang_cd: str | Unset = "ko",
) -> BenefitApplicableProductsSearchResponse | HTTPValidationError | None:
    """쿠폰/이벤트/기획전 통합 적용 상품 검색

     검색어(query)를 기준으로 사용자의 보유 쿠폰, 현재 전시 중인 이벤트, 현재 전시 중인 기획전을 모두 검색한 뒤 매칭된 혜택별 적용 가능한 대표 상품과 매장을 반환합니다.
    차량/규격 기반 상품 검색은 포함하지 않습니다.

    Args:
        query (str): 혜택명/쿠폰명/이벤트명/기획전명 검색어
        lang_cd (str | Unset): 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BenefitApplicableProductsSearchResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            query=query,
            lang_cd=lang_cd,
        )
    ).parsed
