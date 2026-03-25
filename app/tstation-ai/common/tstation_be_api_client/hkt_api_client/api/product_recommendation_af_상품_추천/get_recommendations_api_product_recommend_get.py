from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rcmd_type import RcmdType
from ...models.recommendation_response import RecommendationResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    entr_yn: str,
    entr_no: None | str | Unset = UNSET,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_rcmd_type = rcmd_type.value
    params["rcmd_type"] = json_rcmd_type

    params["limit"] = limit

    params["brand_cd"] = brand_cd

    params["entr_yn"] = entr_yn

    json_entr_no: None | str | Unset
    if isinstance(entr_no, Unset):
        json_entr_no = UNSET
    else:
        json_entr_no = entr_no
    params["entr_no"] = json_entr_no

    json_car_lnc_cd: None | str | Unset
    if isinstance(car_lnc_cd, Unset):
        json_car_lnc_cd = UNSET
    else:
        json_car_lnc_cd = car_lnc_cd
    params["car_lnc_cd"] = json_car_lnc_cd

    json_tire_size: None | str | Unset
    if isinstance(tire_size, Unset):
        json_tire_size = UNSET
    else:
        json_tire_size = tire_size
    params["tire_size"] = json_tire_size

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/recommend",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | RecommendationResponse | None:
    if response.status_code == 200:
        response_200 = RecommendationResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | RecommendationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    entr_yn: str,
    entr_no: None | str | Unset = UNSET,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        entr_yn (str): 제휴 사이트 (y/n)
        entr_no (None | str | Unset): 제휴사 번호 (entr_yn=y 일 때 필수)
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecommendationResponse]
    """

    kwargs = _get_kwargs(
        rcmd_type=rcmd_type,
        limit=limit,
        brand_cd=brand_cd,
        entr_yn=entr_yn,
        entr_no=entr_no,
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    entr_yn: str,
    entr_no: None | str | Unset = UNSET,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        entr_yn (str): 제휴 사이트 (y/n)
        entr_no (None | str | Unset): 제휴사 번호 (entr_yn=y 일 때 필수)
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecommendationResponse
    """

    return sync_detailed(
        client=client,
        rcmd_type=rcmd_type,
        limit=limit,
        brand_cd=brand_cd,
        entr_yn=entr_yn,
        entr_no=entr_no,
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    entr_yn: str,
    entr_no: None | str | Unset = UNSET,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        entr_yn (str): 제휴 사이트 (y/n)
        entr_no (None | str | Unset): 제휴사 번호 (entr_yn=y 일 때 필수)
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecommendationResponse]
    """

    kwargs = _get_kwargs(
        rcmd_type=rcmd_type,
        limit=limit,
        brand_cd=brand_cd,
        entr_yn=entr_yn,
        entr_no=entr_no,
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    entr_yn: str,
    entr_no: None | str | Unset = UNSET,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        entr_yn (str): 제휴 사이트 (y/n)
        entr_no (None | str | Unset): 제휴사 번호 (entr_yn=y 일 때 필수)
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. 입력 시 타이어 사이즈보다 우선 적용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecommendationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            rcmd_type=rcmd_type,
            limit=limit,
            brand_cd=brand_cd,
            entr_yn=entr_yn,
            entr_no=entr_no,
            car_lnc_cd=car_lnc_cd,
            tire_size=tire_size,
        )
    ).parsed
