from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.maintenance_dday_response import MaintenanceDdayResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    mbr_car_reg_seq: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_mbr_car_reg_seq: None | str | Unset
    if isinstance(mbr_car_reg_seq, Unset):
        json_mbr_car_reg_seq = UNSET
    else:
        json_mbr_car_reg_seq = mbr_car_reg_seq
    params["mbr_car_reg_seq"] = json_mbr_car_reg_seq

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/maintenance-dday",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MaintenanceDdayResponse | None:
    if response.status_code == 200:
        response_200 = MaintenanceDdayResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MaintenanceDdayResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | MaintenanceDdayResponse]:
    """회원 등록차량 정비 D-day 매트릭스 조회

     JWT 회원번호 기준으로 등록차량 × 7개 정비 항목 (얼라인먼트/all my T 무상점검/엔진오일/실내필터/와이퍼/타이어/배터리) 에 대한 만기일·D-day 매트릭스를 반환한다.
    ST_NOTI_DDAY_INFO 행이 있으면 NOTI_EXP_DT 사용, 없으면 차량등록일 + NOTI_MSG_TRNS_STD 개월 (ADD_MONTHS) fallback. 동일
    차량·항목에 다행이 있을 경우 SYS_REG_DTIME 최신 1행만 사용. mbr_car_reg_seq 가 주어지면 해당 차량만, 없으면 등록차량 전체 매트릭스 반환.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 차량 등록 시퀀스. 미지정 시 회원의 모든 등록차량 매트릭스 반환.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceDdayResponse]
    """

    kwargs = _get_kwargs(
        mbr_car_reg_seq=mbr_car_reg_seq,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
) -> HTTPValidationError | MaintenanceDdayResponse | None:
    """회원 등록차량 정비 D-day 매트릭스 조회

     JWT 회원번호 기준으로 등록차량 × 7개 정비 항목 (얼라인먼트/all my T 무상점검/엔진오일/실내필터/와이퍼/타이어/배터리) 에 대한 만기일·D-day 매트릭스를 반환한다.
    ST_NOTI_DDAY_INFO 행이 있으면 NOTI_EXP_DT 사용, 없으면 차량등록일 + NOTI_MSG_TRNS_STD 개월 (ADD_MONTHS) fallback. 동일
    차량·항목에 다행이 있을 경우 SYS_REG_DTIME 최신 1행만 사용. mbr_car_reg_seq 가 주어지면 해당 차량만, 없으면 등록차량 전체 매트릭스 반환.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 차량 등록 시퀀스. 미지정 시 회원의 모든 등록차량 매트릭스 반환.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceDdayResponse
    """

    return sync_detailed(
        client=client,
        mbr_car_reg_seq=mbr_car_reg_seq,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | MaintenanceDdayResponse]:
    """회원 등록차량 정비 D-day 매트릭스 조회

     JWT 회원번호 기준으로 등록차량 × 7개 정비 항목 (얼라인먼트/all my T 무상점검/엔진오일/실내필터/와이퍼/타이어/배터리) 에 대한 만기일·D-day 매트릭스를 반환한다.
    ST_NOTI_DDAY_INFO 행이 있으면 NOTI_EXP_DT 사용, 없으면 차량등록일 + NOTI_MSG_TRNS_STD 개월 (ADD_MONTHS) fallback. 동일
    차량·항목에 다행이 있을 경우 SYS_REG_DTIME 최신 1행만 사용. mbr_car_reg_seq 가 주어지면 해당 차량만, 없으면 등록차량 전체 매트릭스 반환.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 차량 등록 시퀀스. 미지정 시 회원의 모든 등록차량 매트릭스 반환.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceDdayResponse]
    """

    kwargs = _get_kwargs(
        mbr_car_reg_seq=mbr_car_reg_seq,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
) -> HTTPValidationError | MaintenanceDdayResponse | None:
    """회원 등록차량 정비 D-day 매트릭스 조회

     JWT 회원번호 기준으로 등록차량 × 7개 정비 항목 (얼라인먼트/all my T 무상점검/엔진오일/실내필터/와이퍼/타이어/배터리) 에 대한 만기일·D-day 매트릭스를 반환한다.
    ST_NOTI_DDAY_INFO 행이 있으면 NOTI_EXP_DT 사용, 없으면 차량등록일 + NOTI_MSG_TRNS_STD 개월 (ADD_MONTHS) fallback. 동일
    차량·항목에 다행이 있을 경우 SYS_REG_DTIME 최신 1행만 사용. mbr_car_reg_seq 가 주어지면 해당 차량만, 없으면 등록차량 전체 매트릭스 반환.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 차량 등록 시퀀스. 미지정 시 회원의 모든 등록차량 매트릭스 반환.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceDdayResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            mbr_car_reg_seq=mbr_car_reg_seq,
        )
    ).parsed
