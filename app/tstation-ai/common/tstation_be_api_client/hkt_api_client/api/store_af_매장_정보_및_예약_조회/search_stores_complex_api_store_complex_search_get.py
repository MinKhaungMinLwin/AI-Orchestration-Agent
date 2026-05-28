from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.store_complex_search_response import StoreComplexSearchResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    region_code: None | str | Unset = UNSET,
    store_nm: None | str | Unset = UNSET,
    xpos: float | None | Unset = UNSET,
    ypos: float | None | Unset = UNSET,
    radius_km: float | Unset = 20.0,
    svc_codes: list[str] | None | Unset = UNSET,
    all_my_t_only: bool | Unset = False,
    imported_car_only: bool | Unset = False,
    ev_specialty_only: bool | Unset = False,
    ev_charge_available_only: bool | Unset = False,
    installable_only: bool | Unset = False,
    chl_sct_cd: None | str | Unset = UNSET,
    cal_day: None | str | Unset = UNSET,
    open_only: bool | Unset = False,
    time_after_hour: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_region_code: None | str | Unset
    if isinstance(region_code, Unset):
        json_region_code = UNSET
    else:
        json_region_code = region_code
    params["region_code"] = json_region_code

    json_store_nm: None | str | Unset
    if isinstance(store_nm, Unset):
        json_store_nm = UNSET
    else:
        json_store_nm = store_nm
    params["store_nm"] = json_store_nm

    json_xpos: float | None | Unset
    if isinstance(xpos, Unset):
        json_xpos = UNSET
    else:
        json_xpos = xpos
    params["xpos"] = json_xpos

    json_ypos: float | None | Unset
    if isinstance(ypos, Unset):
        json_ypos = UNSET
    else:
        json_ypos = ypos
    params["ypos"] = json_ypos

    params["radius_km"] = radius_km

    json_svc_codes: list[str] | None | Unset
    if isinstance(svc_codes, Unset):
        json_svc_codes = UNSET
    elif isinstance(svc_codes, list):
        json_svc_codes = svc_codes

    else:
        json_svc_codes = svc_codes
    params["svc_codes"] = json_svc_codes

    params["all_my_t_only"] = all_my_t_only

    params["imported_car_only"] = imported_car_only

    params["ev_specialty_only"] = ev_specialty_only

    params["ev_charge_available_only"] = ev_charge_available_only

    params["installable_only"] = installable_only

    json_chl_sct_cd: None | str | Unset
    if isinstance(chl_sct_cd, Unset):
        json_chl_sct_cd = UNSET
    else:
        json_chl_sct_cd = chl_sct_cd
    params["chl_sct_cd"] = json_chl_sct_cd

    json_cal_day: None | str | Unset
    if isinstance(cal_day, Unset):
        json_cal_day = UNSET
    else:
        json_cal_day = cal_day
    params["cal_day"] = json_cal_day

    params["open_only"] = open_only

    json_time_after_hour: int | None | Unset
    if isinstance(time_after_hour, Unset):
        json_time_after_hour = UNSET
    else:
        json_time_after_hour = time_after_hour
    params["time_after_hour"] = json_time_after_hour

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
        "url": "/api/store/complex-search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreComplexSearchResponse | None:
    if response.status_code == 200:
        response_200 = StoreComplexSearchResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | StoreComplexSearchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    region_code: None | str | Unset = UNSET,
    store_nm: None | str | Unset = UNSET,
    xpos: float | None | Unset = UNSET,
    ypos: float | None | Unset = UNSET,
    radius_km: float | Unset = 20.0,
    svc_codes: list[str] | None | Unset = UNSET,
    all_my_t_only: bool | Unset = False,
    imported_car_only: bool | Unset = False,
    ev_specialty_only: bool | Unset = False,
    ev_charge_available_only: bool | Unset = False,
    installable_only: bool | Unset = False,
    chl_sct_cd: None | str | Unset = UNSET,
    cal_day: None | str | Unset = UNSET,
    open_only: bool | Unset = False,
    time_after_hour: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | StoreComplexSearchResponse]:
    """매장 복합 검색

     지역/매장명/좌표 조건에 특화 서비스, 서비스 코드, 특정 날짜 영업 여부, 예약 가능 시간 조건을 함께 적용해 매장을 검색합니다. `cal_day`가 있으면
    `is_open_on_cal_day`와 `available_slots`를 별도로 반환합니다.

    Args:
        region_code (None | str | Unset): 지역 검색어
        store_nm (None | str | Unset): 매장명 명칭 검색
        xpos (float | None | Unset): X 좌표 (경도, place-search 결과의 x 값)
        ypos (float | None | Unset): Y 좌표 (위도, place-search 결과의 y 값)
        radius_km (float | Unset): 좌표 검색 반경 (km), 기본값 20km Default: 20.0.
        svc_codes (list[str] | None | Unset): 서비스 구분 코드 목록. 하나라도 보유한 매장 반환.
        all_my_t_only (bool | Unset): True 이면 all my T 매장만 조회 Default: False.
        imported_car_only (bool | Unset): True 이면 수입차 특화점만 조회 Default: False.
        ev_specialty_only (bool | Unset): True 이면 전기차 특화점만 조회 Default: False.
        ev_charge_available_only (bool | Unset): True 이면 전기차 충전 가능 매장만 조회 Default: False.
        installable_only (bool | Unset): True 이면 온라인 주문 장착 가능 매장만 조회 Default: False.
        chl_sct_cd (None | str | Unset): 채널 구분 코드. F=T'Station, S=The Tire Shop
        cal_day (None | str | Unset): 영업/예약 조회 날짜 (YYYYMMDD)
        open_only (bool | Unset): True 이면 cal_day 기준 예약 가능 슬롯이 있는 매장만 반환 Default: False.
        time_after_hour (int | None | Unset): cal_day 기준 이 시각 이후 예약 가능 슬롯이 있는 매장만 반환
        sort_by (None | str | Unset): 정렬 기준: rating, review_count, distance. 미지정 시 기존 매장 목록 정렬과
            동일.
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreComplexSearchResponse]
    """

    kwargs = _get_kwargs(
        region_code=region_code,
        store_nm=store_nm,
        xpos=xpos,
        ypos=ypos,
        radius_km=radius_km,
        svc_codes=svc_codes,
        all_my_t_only=all_my_t_only,
        imported_car_only=imported_car_only,
        ev_specialty_only=ev_specialty_only,
        ev_charge_available_only=ev_charge_available_only,
        installable_only=installable_only,
        chl_sct_cd=chl_sct_cd,
        cal_day=cal_day,
        open_only=open_only,
        time_after_hour=time_after_hour,
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
    region_code: None | str | Unset = UNSET,
    store_nm: None | str | Unset = UNSET,
    xpos: float | None | Unset = UNSET,
    ypos: float | None | Unset = UNSET,
    radius_km: float | Unset = 20.0,
    svc_codes: list[str] | None | Unset = UNSET,
    all_my_t_only: bool | Unset = False,
    imported_car_only: bool | Unset = False,
    ev_specialty_only: bool | Unset = False,
    ev_charge_available_only: bool | Unset = False,
    installable_only: bool | Unset = False,
    chl_sct_cd: None | str | Unset = UNSET,
    cal_day: None | str | Unset = UNSET,
    open_only: bool | Unset = False,
    time_after_hour: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | StoreComplexSearchResponse | None:
    """매장 복합 검색

     지역/매장명/좌표 조건에 특화 서비스, 서비스 코드, 특정 날짜 영업 여부, 예약 가능 시간 조건을 함께 적용해 매장을 검색합니다. `cal_day`가 있으면
    `is_open_on_cal_day`와 `available_slots`를 별도로 반환합니다.

    Args:
        region_code (None | str | Unset): 지역 검색어
        store_nm (None | str | Unset): 매장명 명칭 검색
        xpos (float | None | Unset): X 좌표 (경도, place-search 결과의 x 값)
        ypos (float | None | Unset): Y 좌표 (위도, place-search 결과의 y 값)
        radius_km (float | Unset): 좌표 검색 반경 (km), 기본값 20km Default: 20.0.
        svc_codes (list[str] | None | Unset): 서비스 구분 코드 목록. 하나라도 보유한 매장 반환.
        all_my_t_only (bool | Unset): True 이면 all my T 매장만 조회 Default: False.
        imported_car_only (bool | Unset): True 이면 수입차 특화점만 조회 Default: False.
        ev_specialty_only (bool | Unset): True 이면 전기차 특화점만 조회 Default: False.
        ev_charge_available_only (bool | Unset): True 이면 전기차 충전 가능 매장만 조회 Default: False.
        installable_only (bool | Unset): True 이면 온라인 주문 장착 가능 매장만 조회 Default: False.
        chl_sct_cd (None | str | Unset): 채널 구분 코드. F=T'Station, S=The Tire Shop
        cal_day (None | str | Unset): 영업/예약 조회 날짜 (YYYYMMDD)
        open_only (bool | Unset): True 이면 cal_day 기준 예약 가능 슬롯이 있는 매장만 반환 Default: False.
        time_after_hour (int | None | Unset): cal_day 기준 이 시각 이후 예약 가능 슬롯이 있는 매장만 반환
        sort_by (None | str | Unset): 정렬 기준: rating, review_count, distance. 미지정 시 기존 매장 목록 정렬과
            동일.
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreComplexSearchResponse
    """

    return sync_detailed(
        client=client,
        region_code=region_code,
        store_nm=store_nm,
        xpos=xpos,
        ypos=ypos,
        radius_km=radius_km,
        svc_codes=svc_codes,
        all_my_t_only=all_my_t_only,
        imported_car_only=imported_car_only,
        ev_specialty_only=ev_specialty_only,
        ev_charge_available_only=ev_charge_available_only,
        installable_only=installable_only,
        chl_sct_cd=chl_sct_cd,
        cal_day=cal_day,
        open_only=open_only,
        time_after_hour=time_after_hour,
        sort_by=sort_by,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    region_code: None | str | Unset = UNSET,
    store_nm: None | str | Unset = UNSET,
    xpos: float | None | Unset = UNSET,
    ypos: float | None | Unset = UNSET,
    radius_km: float | Unset = 20.0,
    svc_codes: list[str] | None | Unset = UNSET,
    all_my_t_only: bool | Unset = False,
    imported_car_only: bool | Unset = False,
    ev_specialty_only: bool | Unset = False,
    ev_charge_available_only: bool | Unset = False,
    installable_only: bool | Unset = False,
    chl_sct_cd: None | str | Unset = UNSET,
    cal_day: None | str | Unset = UNSET,
    open_only: bool | Unset = False,
    time_after_hour: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[HTTPValidationError | StoreComplexSearchResponse]:
    """매장 복합 검색

     지역/매장명/좌표 조건에 특화 서비스, 서비스 코드, 특정 날짜 영업 여부, 예약 가능 시간 조건을 함께 적용해 매장을 검색합니다. `cal_day`가 있으면
    `is_open_on_cal_day`와 `available_slots`를 별도로 반환합니다.

    Args:
        region_code (None | str | Unset): 지역 검색어
        store_nm (None | str | Unset): 매장명 명칭 검색
        xpos (float | None | Unset): X 좌표 (경도, place-search 결과의 x 값)
        ypos (float | None | Unset): Y 좌표 (위도, place-search 결과의 y 값)
        radius_km (float | Unset): 좌표 검색 반경 (km), 기본값 20km Default: 20.0.
        svc_codes (list[str] | None | Unset): 서비스 구분 코드 목록. 하나라도 보유한 매장 반환.
        all_my_t_only (bool | Unset): True 이면 all my T 매장만 조회 Default: False.
        imported_car_only (bool | Unset): True 이면 수입차 특화점만 조회 Default: False.
        ev_specialty_only (bool | Unset): True 이면 전기차 특화점만 조회 Default: False.
        ev_charge_available_only (bool | Unset): True 이면 전기차 충전 가능 매장만 조회 Default: False.
        installable_only (bool | Unset): True 이면 온라인 주문 장착 가능 매장만 조회 Default: False.
        chl_sct_cd (None | str | Unset): 채널 구분 코드. F=T'Station, S=The Tire Shop
        cal_day (None | str | Unset): 영업/예약 조회 날짜 (YYYYMMDD)
        open_only (bool | Unset): True 이면 cal_day 기준 예약 가능 슬롯이 있는 매장만 반환 Default: False.
        time_after_hour (int | None | Unset): cal_day 기준 이 시각 이후 예약 가능 슬롯이 있는 매장만 반환
        sort_by (None | str | Unset): 정렬 기준: rating, review_count, distance. 미지정 시 기존 매장 목록 정렬과
            동일.
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreComplexSearchResponse]
    """

    kwargs = _get_kwargs(
        region_code=region_code,
        store_nm=store_nm,
        xpos=xpos,
        ypos=ypos,
        radius_km=radius_km,
        svc_codes=svc_codes,
        all_my_t_only=all_my_t_only,
        imported_car_only=imported_car_only,
        ev_specialty_only=ev_specialty_only,
        ev_charge_available_only=ev_charge_available_only,
        installable_only=installable_only,
        chl_sct_cd=chl_sct_cd,
        cal_day=cal_day,
        open_only=open_only,
        time_after_hour=time_after_hour,
        sort_by=sort_by,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    region_code: None | str | Unset = UNSET,
    store_nm: None | str | Unset = UNSET,
    xpos: float | None | Unset = UNSET,
    ypos: float | None | Unset = UNSET,
    radius_km: float | Unset = 20.0,
    svc_codes: list[str] | None | Unset = UNSET,
    all_my_t_only: bool | Unset = False,
    imported_car_only: bool | Unset = False,
    ev_specialty_only: bool | Unset = False,
    ev_charge_available_only: bool | Unset = False,
    installable_only: bool | Unset = False,
    chl_sct_cd: None | str | Unset = UNSET,
    cal_day: None | str | Unset = UNSET,
    open_only: bool | Unset = False,
    time_after_hour: int | None | Unset = UNSET,
    sort_by: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> HTTPValidationError | StoreComplexSearchResponse | None:
    """매장 복합 검색

     지역/매장명/좌표 조건에 특화 서비스, 서비스 코드, 특정 날짜 영업 여부, 예약 가능 시간 조건을 함께 적용해 매장을 검색합니다. `cal_day`가 있으면
    `is_open_on_cal_day`와 `available_slots`를 별도로 반환합니다.

    Args:
        region_code (None | str | Unset): 지역 검색어
        store_nm (None | str | Unset): 매장명 명칭 검색
        xpos (float | None | Unset): X 좌표 (경도, place-search 결과의 x 값)
        ypos (float | None | Unset): Y 좌표 (위도, place-search 결과의 y 값)
        radius_km (float | Unset): 좌표 검색 반경 (km), 기본값 20km Default: 20.0.
        svc_codes (list[str] | None | Unset): 서비스 구분 코드 목록. 하나라도 보유한 매장 반환.
        all_my_t_only (bool | Unset): True 이면 all my T 매장만 조회 Default: False.
        imported_car_only (bool | Unset): True 이면 수입차 특화점만 조회 Default: False.
        ev_specialty_only (bool | Unset): True 이면 전기차 특화점만 조회 Default: False.
        ev_charge_available_only (bool | Unset): True 이면 전기차 충전 가능 매장만 조회 Default: False.
        installable_only (bool | Unset): True 이면 온라인 주문 장착 가능 매장만 조회 Default: False.
        chl_sct_cd (None | str | Unset): 채널 구분 코드. F=T'Station, S=The Tire Shop
        cal_day (None | str | Unset): 영업/예약 조회 날짜 (YYYYMMDD)
        open_only (bool | Unset): True 이면 cal_day 기준 예약 가능 슬롯이 있는 매장만 반환 Default: False.
        time_after_hour (int | None | Unset): cal_day 기준 이 시각 이후 예약 가능 슬롯이 있는 매장만 반환
        sort_by (None | str | Unset): 정렬 기준: rating, review_count, distance. 미지정 시 기존 매장 목록 정렬과
            동일.
        limit (int | Unset): 반환할 최대 매장 수 Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreComplexSearchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            region_code=region_code,
            store_nm=store_nm,
            xpos=xpos,
            ypos=ypos,
            radius_km=radius_km,
            svc_codes=svc_codes,
            all_my_t_only=all_my_t_only,
            imported_car_only=imported_car_only,
            ev_specialty_only=ev_specialty_only,
            ev_charge_available_only=ev_charge_available_only,
            installable_only=installable_only,
            chl_sct_cd=chl_sct_cd,
            cal_day=cal_day,
            open_only=open_only,
            time_after_hour=time_after_hour,
            sort_by=sort_by,
            limit=limit,
        )
    ).parsed
