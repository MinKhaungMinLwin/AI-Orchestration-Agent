from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.reservation_list_response import ReservationListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    sct_cd: None | str | Unset = "100",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_sct_cd: None | str | Unset
    if isinstance(sct_cd, Unset):
        json_sct_cd = UNSET
    else:
        json_sct_cd = sct_cd
    params["sct_cd"] = json_sct_cd

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/reservations/",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ReservationListResponse | None:
    if response.status_code == 200:
        response_200 = ReservationListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ReservationListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    sct_cd: None | str | Unset = "100",
) -> Response[HTTPValidationError | ReservationListResponse]:
    """매장 방문 예약 조회

     인증된 회원(MBR_NO) 본인의 매장 방문 예약 목록을 `ET_SHOP_RSV_INFO` 에서 조회합니다.

    **매장예약구분 (`SHOP_RSV_SCT_CD` [SHOP001])**
    - `100`: 방문예약 (단순 매장 방문 예약 — 노출 기본값)
    - `200`: 구매후방문예약 (`ORD_NO` 함께 존재)
    - `300`: 오프라인예약

    **예약 상태 라벨 그룹 (`SHOP_VST_RSV_STS_CD` [SHOP002])**
    - 예약대기: `100`/`110`/`120`/`400`/`410`/`420`/`430`/`440`
    - 예약완료: `130`/`140`
    - 서비스완료: `300`
    - 서비스취소: `900`/`910`/`920`/`930`/`950`/`960`

    주문취소된 구매후방문예약은 `OP_ORD_DTL_INFO.ORD_DTL_SCT_CD='20'` 기준으로 제외합니다.

    `sct_cd` 파라미터로 종류를 필터링할 수 있습니다 (기본: `100` 단순 방문예약만, `all` 지정 시 전체 노출). 매장명/전화번호는 `VW_ET_SHOP_INFO`
    LEFT JOIN. 정렬은 방문예약일시 내림차순.

    Args:
        sct_cd (None | str | Unset): 매장예약구분 필터. 값: '100'(방문예약, 기본) / '200'(구매후방문예약) /
            '300'(오프라인예약) / 'all'(전체 노출) Default: '100'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReservationListResponse]
    """

    kwargs = _get_kwargs(
        sct_cd=sct_cd,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    sct_cd: None | str | Unset = "100",
) -> HTTPValidationError | ReservationListResponse | None:
    """매장 방문 예약 조회

     인증된 회원(MBR_NO) 본인의 매장 방문 예약 목록을 `ET_SHOP_RSV_INFO` 에서 조회합니다.

    **매장예약구분 (`SHOP_RSV_SCT_CD` [SHOP001])**
    - `100`: 방문예약 (단순 매장 방문 예약 — 노출 기본값)
    - `200`: 구매후방문예약 (`ORD_NO` 함께 존재)
    - `300`: 오프라인예약

    **예약 상태 라벨 그룹 (`SHOP_VST_RSV_STS_CD` [SHOP002])**
    - 예약대기: `100`/`110`/`120`/`400`/`410`/`420`/`430`/`440`
    - 예약완료: `130`/`140`
    - 서비스완료: `300`
    - 서비스취소: `900`/`910`/`920`/`930`/`950`/`960`

    주문취소된 구매후방문예약은 `OP_ORD_DTL_INFO.ORD_DTL_SCT_CD='20'` 기준으로 제외합니다.

    `sct_cd` 파라미터로 종류를 필터링할 수 있습니다 (기본: `100` 단순 방문예약만, `all` 지정 시 전체 노출). 매장명/전화번호는 `VW_ET_SHOP_INFO`
    LEFT JOIN. 정렬은 방문예약일시 내림차순.

    Args:
        sct_cd (None | str | Unset): 매장예약구분 필터. 값: '100'(방문예약, 기본) / '200'(구매후방문예약) /
            '300'(오프라인예약) / 'all'(전체 노출) Default: '100'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReservationListResponse
    """

    return sync_detailed(
        client=client,
        sct_cd=sct_cd,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    sct_cd: None | str | Unset = "100",
) -> Response[HTTPValidationError | ReservationListResponse]:
    """매장 방문 예약 조회

     인증된 회원(MBR_NO) 본인의 매장 방문 예약 목록을 `ET_SHOP_RSV_INFO` 에서 조회합니다.

    **매장예약구분 (`SHOP_RSV_SCT_CD` [SHOP001])**
    - `100`: 방문예약 (단순 매장 방문 예약 — 노출 기본값)
    - `200`: 구매후방문예약 (`ORD_NO` 함께 존재)
    - `300`: 오프라인예약

    **예약 상태 라벨 그룹 (`SHOP_VST_RSV_STS_CD` [SHOP002])**
    - 예약대기: `100`/`110`/`120`/`400`/`410`/`420`/`430`/`440`
    - 예약완료: `130`/`140`
    - 서비스완료: `300`
    - 서비스취소: `900`/`910`/`920`/`930`/`950`/`960`

    주문취소된 구매후방문예약은 `OP_ORD_DTL_INFO.ORD_DTL_SCT_CD='20'` 기준으로 제외합니다.

    `sct_cd` 파라미터로 종류를 필터링할 수 있습니다 (기본: `100` 단순 방문예약만, `all` 지정 시 전체 노출). 매장명/전화번호는 `VW_ET_SHOP_INFO`
    LEFT JOIN. 정렬은 방문예약일시 내림차순.

    Args:
        sct_cd (None | str | Unset): 매장예약구분 필터. 값: '100'(방문예약, 기본) / '200'(구매후방문예약) /
            '300'(오프라인예약) / 'all'(전체 노출) Default: '100'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReservationListResponse]
    """

    kwargs = _get_kwargs(
        sct_cd=sct_cd,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    sct_cd: None | str | Unset = "100",
) -> HTTPValidationError | ReservationListResponse | None:
    """매장 방문 예약 조회

     인증된 회원(MBR_NO) 본인의 매장 방문 예약 목록을 `ET_SHOP_RSV_INFO` 에서 조회합니다.

    **매장예약구분 (`SHOP_RSV_SCT_CD` [SHOP001])**
    - `100`: 방문예약 (단순 매장 방문 예약 — 노출 기본값)
    - `200`: 구매후방문예약 (`ORD_NO` 함께 존재)
    - `300`: 오프라인예약

    **예약 상태 라벨 그룹 (`SHOP_VST_RSV_STS_CD` [SHOP002])**
    - 예약대기: `100`/`110`/`120`/`400`/`410`/`420`/`430`/`440`
    - 예약완료: `130`/`140`
    - 서비스완료: `300`
    - 서비스취소: `900`/`910`/`920`/`930`/`950`/`960`

    주문취소된 구매후방문예약은 `OP_ORD_DTL_INFO.ORD_DTL_SCT_CD='20'` 기준으로 제외합니다.

    `sct_cd` 파라미터로 종류를 필터링할 수 있습니다 (기본: `100` 단순 방문예약만, `all` 지정 시 전체 노출). 매장명/전화번호는 `VW_ET_SHOP_INFO`
    LEFT JOIN. 정렬은 방문예약일시 내림차순.

    Args:
        sct_cd (None | str | Unset): 매장예약구분 필터. 값: '100'(방문예약, 기본) / '200'(구매후방문예약) /
            '300'(오프라인예약) / 'all'(전체 노출) Default: '100'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReservationListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            sct_cd=sct_cd,
        )
    ).parsed
