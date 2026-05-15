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
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
    season_nm: None | str | Unset = UNSET,
    pfm_nm: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_rcmd_type = rcmd_type.value
    params["rcmd_type"] = json_rcmd_type

    params["limit"] = limit

    params["brand_cd"] = brand_cd

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

    json_season_nm: None | str | Unset
    if isinstance(season_nm, Unset):
        json_season_nm = UNSET
    else:
        json_season_nm = season_nm
    params["season_nm"] = json_season_nm

    json_pfm_nm: None | str | Unset
    if isinstance(pfm_nm, Unset):
        json_pfm_nm = UNSET
    else:
        json_pfm_nm = pfm_nm
    params["pfm_nm"] = json_pfm_nm

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
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
    season_nm: None | str | Unset = UNSET,
    pfm_nm: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    **기존 타입 (전용 SQL)**
    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    **신규 타입 (베이스 템플릿 + 설정 기반, `entr_yn=y` 시 제휴사 가격 자동 적용)**
    - **wet**: 빗길 성능 (`WET` 높은 순)
    - **snow**: 눈길/빙판 (`T_SNOW`, `T_ICE` 높은 순)
    - **high_speed**: 고속 주행 (`T_HIGHSPD` 높은 순)
    - **handling**: 핸들링 (`T_HIGH_HAND_AVG` 높은 순)
    - **low_vibration**: 진동 적은 (`T_COM_SIL_AVG`, `T_COM_CVS` 높은 순)
    - **performance**: 퍼포먼스 (`GOODS_PFM_NM='SPORT'` + `T_HIGH_HAND_AVG` 높은 순)
    - **commute**: 출퇴근 (`SEASON_NM='사계절'` + `T_MILG_CVS` 높은 순)
    - **long_distance**: 장거리 (`T_COM_SIL_AVG`/`T_COM_CVS`/`T_MILG_CVS` 높은 순)
    - **urban**: 도심 주행 (`SEASON_NM='사계절'` + `GOODS_PFM_NM='COMFORT'`)
    - **family**: 가족용 (`GOODS_PFM_NM IN ('COMFORT','RUNFLAT')`)
    - **ev**: 전기차용 (`CAR_KND_NM='전기차'`)
    - **heavy_load**: 짐 많이 (`T_WGT_IDX`, `T_WGT_IDX_KG` 높은 순)
    - **weekend**: 주말 (`SEASON_NM='사계절'` + `PRC_GRD_NM='스탠다드'`, `T_TRAY_WARE` 높은 순)
    - **safe_kids**: 아이 안전 (`T_RLX_ISN_YN='O'` + 정숙·하중 높은 순)
    - **all_weather**: 눈길/비 전천후 (`WET`/`T_SNOW`/`T_ICE` 높은 순)
    - **warranty**: 워런티 가능 (`ET_DGTL_WRT_APLY_INFO.WRT_TGT_YN='Y'`, `WRT_GRTE_TERM` 긴 순)
    - **summer**: 여름용 (`SEASON_NM='여름'`, `WET`/`T_HIGH_HAND_AVG` 높은 순)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. tire_size가 없을 때만 사용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용). 입력 시 car_lnc_cd보다
            우선 적용
        season_nm (None | str | Unset): 계절 직교 필터. 값: '여름'/'겨울'/'사계절'/'올웨더'. '여름'/'겨울'/'사계절' 은
            PR_GOODS_BASE.SEASON_NM 매칭, '올웨더' 는 PR_PATTERN_BASE.ALLWEATHER_YN='Y' 매칭. 신규(동적) rcmd_type
            에만 적용됨.
        pfm_nm (None | str | Unset): 성능 등급 직교 필터. 값: 'SPORT'/'COMFORT'/'RUNFLAT'. 신규(동적) rcmd_type
            에만 적용됨.

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
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
        season_nm=season_nm,
        pfm_nm=pfm_nm,
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
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
    season_nm: None | str | Unset = UNSET,
    pfm_nm: None | str | Unset = UNSET,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    **기존 타입 (전용 SQL)**
    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    **신규 타입 (베이스 템플릿 + 설정 기반, `entr_yn=y` 시 제휴사 가격 자동 적용)**
    - **wet**: 빗길 성능 (`WET` 높은 순)
    - **snow**: 눈길/빙판 (`T_SNOW`, `T_ICE` 높은 순)
    - **high_speed**: 고속 주행 (`T_HIGHSPD` 높은 순)
    - **handling**: 핸들링 (`T_HIGH_HAND_AVG` 높은 순)
    - **low_vibration**: 진동 적은 (`T_COM_SIL_AVG`, `T_COM_CVS` 높은 순)
    - **performance**: 퍼포먼스 (`GOODS_PFM_NM='SPORT'` + `T_HIGH_HAND_AVG` 높은 순)
    - **commute**: 출퇴근 (`SEASON_NM='사계절'` + `T_MILG_CVS` 높은 순)
    - **long_distance**: 장거리 (`T_COM_SIL_AVG`/`T_COM_CVS`/`T_MILG_CVS` 높은 순)
    - **urban**: 도심 주행 (`SEASON_NM='사계절'` + `GOODS_PFM_NM='COMFORT'`)
    - **family**: 가족용 (`GOODS_PFM_NM IN ('COMFORT','RUNFLAT')`)
    - **ev**: 전기차용 (`CAR_KND_NM='전기차'`)
    - **heavy_load**: 짐 많이 (`T_WGT_IDX`, `T_WGT_IDX_KG` 높은 순)
    - **weekend**: 주말 (`SEASON_NM='사계절'` + `PRC_GRD_NM='스탠다드'`, `T_TRAY_WARE` 높은 순)
    - **safe_kids**: 아이 안전 (`T_RLX_ISN_YN='O'` + 정숙·하중 높은 순)
    - **all_weather**: 눈길/비 전천후 (`WET`/`T_SNOW`/`T_ICE` 높은 순)
    - **warranty**: 워런티 가능 (`ET_DGTL_WRT_APLY_INFO.WRT_TGT_YN='Y'`, `WRT_GRTE_TERM` 긴 순)
    - **summer**: 여름용 (`SEASON_NM='여름'`, `WET`/`T_HIGH_HAND_AVG` 높은 순)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. tire_size가 없을 때만 사용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용). 입력 시 car_lnc_cd보다
            우선 적용
        season_nm (None | str | Unset): 계절 직교 필터. 값: '여름'/'겨울'/'사계절'/'올웨더'. '여름'/'겨울'/'사계절' 은
            PR_GOODS_BASE.SEASON_NM 매칭, '올웨더' 는 PR_PATTERN_BASE.ALLWEATHER_YN='Y' 매칭. 신규(동적) rcmd_type
            에만 적용됨.
        pfm_nm (None | str | Unset): 성능 등급 직교 필터. 값: 'SPORT'/'COMFORT'/'RUNFLAT'. 신규(동적) rcmd_type
            에만 적용됨.

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
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
        season_nm=season_nm,
        pfm_nm=pfm_nm,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
    season_nm: None | str | Unset = UNSET,
    pfm_nm: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    **기존 타입 (전용 SQL)**
    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    **신규 타입 (베이스 템플릿 + 설정 기반, `entr_yn=y` 시 제휴사 가격 자동 적용)**
    - **wet**: 빗길 성능 (`WET` 높은 순)
    - **snow**: 눈길/빙판 (`T_SNOW`, `T_ICE` 높은 순)
    - **high_speed**: 고속 주행 (`T_HIGHSPD` 높은 순)
    - **handling**: 핸들링 (`T_HIGH_HAND_AVG` 높은 순)
    - **low_vibration**: 진동 적은 (`T_COM_SIL_AVG`, `T_COM_CVS` 높은 순)
    - **performance**: 퍼포먼스 (`GOODS_PFM_NM='SPORT'` + `T_HIGH_HAND_AVG` 높은 순)
    - **commute**: 출퇴근 (`SEASON_NM='사계절'` + `T_MILG_CVS` 높은 순)
    - **long_distance**: 장거리 (`T_COM_SIL_AVG`/`T_COM_CVS`/`T_MILG_CVS` 높은 순)
    - **urban**: 도심 주행 (`SEASON_NM='사계절'` + `GOODS_PFM_NM='COMFORT'`)
    - **family**: 가족용 (`GOODS_PFM_NM IN ('COMFORT','RUNFLAT')`)
    - **ev**: 전기차용 (`CAR_KND_NM='전기차'`)
    - **heavy_load**: 짐 많이 (`T_WGT_IDX`, `T_WGT_IDX_KG` 높은 순)
    - **weekend**: 주말 (`SEASON_NM='사계절'` + `PRC_GRD_NM='스탠다드'`, `T_TRAY_WARE` 높은 순)
    - **safe_kids**: 아이 안전 (`T_RLX_ISN_YN='O'` + 정숙·하중 높은 순)
    - **all_weather**: 눈길/비 전천후 (`WET`/`T_SNOW`/`T_ICE` 높은 순)
    - **warranty**: 워런티 가능 (`ET_DGTL_WRT_APLY_INFO.WRT_TGT_YN='Y'`, `WRT_GRTE_TERM` 긴 순)
    - **summer**: 여름용 (`SEASON_NM='여름'`, `WET`/`T_HIGH_HAND_AVG` 높은 순)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. tire_size가 없을 때만 사용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용). 입력 시 car_lnc_cd보다
            우선 적용
        season_nm (None | str | Unset): 계절 직교 필터. 값: '여름'/'겨울'/'사계절'/'올웨더'. '여름'/'겨울'/'사계절' 은
            PR_GOODS_BASE.SEASON_NM 매칭, '올웨더' 는 PR_PATTERN_BASE.ALLWEATHER_YN='Y' 매칭. 신규(동적) rcmd_type
            에만 적용됨.
        pfm_nm (None | str | Unset): 성능 등급 직교 필터. 값: 'SPORT'/'COMFORT'/'RUNFLAT'. 신규(동적) rcmd_type
            에만 적용됨.

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
        car_lnc_cd=car_lnc_cd,
        tire_size=tire_size,
        season_nm=season_nm,
        pfm_nm=pfm_nm,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
    brand_cd: str,
    car_lnc_cd: None | str | Unset = UNSET,
    tire_size: None | str | Unset = UNSET,
    season_nm: None | str | Unset = UNSET,
    pfm_nm: None | str | Unset = UNSET,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    **기존 타입 (전용 SQL)**
    - **tstation**: 티스테이션 추천 (`TOT_SCR (if FST_DISP_YN='Y' then TOT_SCR = TOT_SCR*10)` 높은 순,
    `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    **신규 타입 (베이스 템플릿 + 설정 기반, `entr_yn=y` 시 제휴사 가격 자동 적용)**
    - **wet**: 빗길 성능 (`WET` 높은 순)
    - **snow**: 눈길/빙판 (`T_SNOW`, `T_ICE` 높은 순)
    - **high_speed**: 고속 주행 (`T_HIGHSPD` 높은 순)
    - **handling**: 핸들링 (`T_HIGH_HAND_AVG` 높은 순)
    - **low_vibration**: 진동 적은 (`T_COM_SIL_AVG`, `T_COM_CVS` 높은 순)
    - **performance**: 퍼포먼스 (`GOODS_PFM_NM='SPORT'` + `T_HIGH_HAND_AVG` 높은 순)
    - **commute**: 출퇴근 (`SEASON_NM='사계절'` + `T_MILG_CVS` 높은 순)
    - **long_distance**: 장거리 (`T_COM_SIL_AVG`/`T_COM_CVS`/`T_MILG_CVS` 높은 순)
    - **urban**: 도심 주행 (`SEASON_NM='사계절'` + `GOODS_PFM_NM='COMFORT'`)
    - **family**: 가족용 (`GOODS_PFM_NM IN ('COMFORT','RUNFLAT')`)
    - **ev**: 전기차용 (`CAR_KND_NM='전기차'`)
    - **heavy_load**: 짐 많이 (`T_WGT_IDX`, `T_WGT_IDX_KG` 높은 순)
    - **weekend**: 주말 (`SEASON_NM='사계절'` + `PRC_GRD_NM='스탠다드'`, `T_TRAY_WARE` 높은 순)
    - **safe_kids**: 아이 안전 (`T_RLX_ISN_YN='O'` + 정숙·하중 높은 순)
    - **all_weather**: 눈길/비 전천후 (`WET`/`T_SNOW`/`T_ICE` 높은 순)
    - **warranty**: 워런티 가능 (`ET_DGTL_WRT_APLY_INFO.WRT_TGT_YN='Y'`, `WRT_GRTE_TERM` 긴 순)
    - **summer**: 여름용 (`SEASON_NM='여름'`, `WET`/`T_HIGH_HAND_AVG` 높은 순)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.
        brand_cd (str): 각 브랜드(HK / LF / MC / PI / BS / CT / GY
        car_lnc_cd (None | str | Unset): 차량 런칭 코드. tire_size가 없을 때만 사용
        tire_size (None | str | Unset): 타이어 사이즈 문자열. 예: 245/45R18 (공백/소문자 허용). 입력 시 car_lnc_cd보다
            우선 적용
        season_nm (None | str | Unset): 계절 직교 필터. 값: '여름'/'겨울'/'사계절'/'올웨더'. '여름'/'겨울'/'사계절' 은
            PR_GOODS_BASE.SEASON_NM 매칭, '올웨더' 는 PR_PATTERN_BASE.ALLWEATHER_YN='Y' 매칭. 신규(동적) rcmd_type
            에만 적용됨.
        pfm_nm (None | str | Unset): 성능 등급 직교 필터. 값: 'SPORT'/'COMFORT'/'RUNFLAT'. 신규(동적) rcmd_type
            에만 적용됨.

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
            car_lnc_cd=car_lnc_cd,
            tire_size=tire_size,
            season_nm=season_nm,
            pfm_nm=pfm_nm,
        )
    ).parsed
