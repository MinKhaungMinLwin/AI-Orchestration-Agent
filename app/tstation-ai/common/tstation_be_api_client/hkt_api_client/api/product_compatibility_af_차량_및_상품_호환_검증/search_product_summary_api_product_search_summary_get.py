from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_search_summary_response import ProductSearchSummaryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    keyword: None | str | Unset = UNSET,
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_keyword: None | str | Unset
    if isinstance(keyword, Unset):
        json_keyword = UNSET
    else:
        json_keyword = keyword
    params["keyword"] = json_keyword

    json_brand_cd: None | str | Unset
    if isinstance(brand_cd, Unset):
        json_brand_cd = UNSET
    else:
        json_brand_cd = brand_cd
    params["brand_cd"] = json_brand_cd

    json_three_pmsf_yn: None | str | Unset
    if isinstance(three_pmsf_yn, Unset):
        json_three_pmsf_yn = UNSET
    else:
        json_three_pmsf_yn = three_pmsf_yn
    params["three_pmsf_yn"] = json_three_pmsf_yn

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/search-summary",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductSearchSummaryResponse | None:
    if response.status_code == 200:
        response_200 = ProductSearchSummaryResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductSearchSummaryResponse]:
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
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[HTTPValidationError | ProductSearchSummaryResponse]:
    """사이즈 미지정 상품군 검색

     제품명 키워드로 특정 사이즈 SKU(goods_no)를 확정하지 않고 PTRN_CD + GOODS_NM 상품군 단위로 검색합니다. 상품 정보, 가격대, 판매 가능 사이즈, 리뷰
    평점, 적용 가능 워런티를 함께 반환합니다.

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '키너지 EX', 'Ventus S2 AS')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어)
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        limit (int | Unset): 반환할 최대 상품군 수. 기본 5개 Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchSummaryResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
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
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> HTTPValidationError | ProductSearchSummaryResponse | None:
    """사이즈 미지정 상품군 검색

     제품명 키워드로 특정 사이즈 SKU(goods_no)를 확정하지 않고 PTRN_CD + GOODS_NM 상품군 단위로 검색합니다. 상품 정보, 가격대, 판매 가능 사이즈, 리뷰
    평점, 적용 가능 워런티를 함께 반환합니다.

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '키너지 EX', 'Ventus S2 AS')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어)
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        limit (int | Unset): 반환할 최대 상품군 수. 기본 5개 Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductSearchSummaryResponse
    """

    return sync_detailed(
        client=client,
        keyword=keyword,
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[HTTPValidationError | ProductSearchSummaryResponse]:
    """사이즈 미지정 상품군 검색

     제품명 키워드로 특정 사이즈 SKU(goods_no)를 확정하지 않고 PTRN_CD + GOODS_NM 상품군 단위로 검색합니다. 상품 정보, 가격대, 판매 가능 사이즈, 리뷰
    평점, 적용 가능 워런티를 함께 반환합니다.

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '키너지 EX', 'Ventus S2 AS')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어)
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        limit (int | Unset): 반환할 최대 상품군 수. 기본 5개 Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductSearchSummaryResponse]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> HTTPValidationError | ProductSearchSummaryResponse | None:
    """사이즈 미지정 상품군 검색

     제품명 키워드로 특정 사이즈 SKU(goods_no)를 확정하지 않고 PTRN_CD + GOODS_NM 상품군 단위로 검색합니다. 상품 정보, 가격대, 판매 가능 사이즈, 리뷰
    평점, 적용 가능 워런티를 함께 반환합니다.

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '키너지 EX', 'Ventus S2 AS')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어)
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        limit (int | Unset): 반환할 최대 상품군 수. 기본 5개 Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductSearchSummaryResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            keyword=keyword,
            brand_cd=brand_cd,
            three_pmsf_yn=three_pmsf_yn,
            limit=limit,
        )
    ).parsed
