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
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    min_price: int | None | Unset = UNSET,
    max_price: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
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

    json_min_price: int | None | Unset
    if isinstance(min_price, Unset):
        json_min_price = UNSET
    else:
        json_min_price = min_price
    params["min_price"] = json_min_price

    json_max_price: int | None | Unset
    if isinstance(max_price, Unset):
        json_max_price = UNSET
    else:
        json_max_price = max_price
    params["max_price"] = json_max_price

    json_sort_by: None | str | Unset
    if isinstance(sort_by, Unset):
        json_sort_by = UNSET
    else:
        json_sort_by = sort_by
    params["sort_by"] = json_sort_by

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
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    min_price: int | None | Unset = UNSET,
    max_price: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어). 미지정 시 전 브랜드 검색
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        min_price (int | None | Unset): 최소 가격 필터 (원). max_price가 있으면 예산 검색으로 보고 무시합니다.
        max_price (int | None | Unset): 최대 가격 필터 (원). 지정 시 0~max_price 범위에서 가격 내림차순으로 반환합니다.
        sort_by (None | str | Unset): 가격 정렬. max_price 지정 시 price_desc로 강제됩니다.
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
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
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
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    min_price: int | None | Unset = UNSET,
    max_price: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어). 미지정 시 전 브랜드 검색
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        min_price (int | None | Unset): 최소 가격 필터 (원). max_price가 있으면 예산 검색으로 보고 무시합니다.
        max_price (int | None | Unset): 최대 가격 필터 (원). 지정 시 0~max_price 범위에서 가격 내림차순으로 반환합니다.
        sort_by (None | str | Unset): 가격 정렬. max_price 지정 시 price_desc로 강제됩니다.
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
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    min_price: int | None | Unset = UNSET,
    max_price: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | ProductSearchResponse]:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어). 미지정 시 전 브랜드 검색
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        min_price (int | None | Unset): 최소 가격 필터 (원). max_price가 있으면 예산 검색으로 보고 무시합니다.
        max_price (int | None | Unset): 최대 가격 필터 (원). 지정 시 0~max_price 범위에서 가격 내림차순으로 반환합니다.
        sort_by (None | str | Unset): 가격 정렬. max_price 지정 시 price_desc로 강제됩니다.
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
        brand_cd=brand_cd,
        three_pmsf_yn=three_pmsf_yn,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    keyword: None | str | Unset = UNSET,
    size: None | str | Unset = UNSET,
    brand_cd: None | str | Unset = UNSET,
    three_pmsf_yn: None | str | Unset = UNSET,
    min_price: int | None | Unset = UNSET,
    max_price: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | ProductSearchResponse | None:
    """상품 검색

     제품명 키워드로 상품을 검색합니다. 한글/영문 혼용, 부분 키워드 지원. (예: '벤투스', 's1 evo', '아이온 suv')
    사이즈를 지정하여 검색 결과를 필터링할 수도 있습니다. (예: '2254517')

    Args:
        keyword (None | str | Unset): 검색할 제품명 키워드 (예: '벤투스 S2', 's1-evo')
        size (None | str | Unset): 타이어 사이즈 (예: '2254517' 또는 '225/45R17')
        brand_cd (None | str | Unset): 브랜드 코드 (HK=한국타이어, LF=라우펜, MC=미쉐린, PI=피렐리, BS=브리지스톤,
            CT=콘티넨탈, GY=굿이어). 미지정 시 전 브랜드 검색
        three_pmsf_yn (None | str | Unset): 3PMSF/삼봉마크 인증 타이어만 검색하려면 Y
        min_price (int | None | Unset): 최소 가격 필터 (원). max_price가 있으면 예산 검색으로 보고 무시합니다.
        max_price (int | None | Unset): 최대 가격 필터 (원). 지정 시 0~max_price 범위에서 가격 내림차순으로 반환합니다.
        sort_by (None | str | Unset): 가격 정렬. max_price 지정 시 price_desc로 강제됩니다.
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
            brand_cd=brand_cd,
            three_pmsf_yn=three_pmsf_yn,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            limit=limit,
        )
    ).parsed
