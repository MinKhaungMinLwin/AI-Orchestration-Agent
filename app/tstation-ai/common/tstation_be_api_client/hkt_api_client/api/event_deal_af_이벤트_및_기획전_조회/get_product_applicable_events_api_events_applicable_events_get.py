from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_applicable_events_response import ProductApplicableEventsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    goods_no: str,
    lang_cd: str | Unset = "ko",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["goods_no"] = goods_no

    params["lang_cd"] = lang_cd

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/events/applicable-events",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductApplicableEventsResponse | None:
    if response.status_code == 200:
        response_200 = ProductApplicableEventsResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductApplicableEventsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    goods_no: str,
    lang_cd: str | Unset = "ko",
) -> Response[HTTPValidationError | ProductApplicableEventsResponse]:
    """상품 적용 가능 이벤트 조회

     특정 상품(goods_no)에 적용 가능한 진행 중 이벤트 목록을 반환합니다. CC_EVT_APLY_INFO 의 50(상품 단위) / 80(패턴 단위) 매핑을 모두 검사하며, 전시
    기간(SYSDATE BETWEEN) + DISP_YN='Y' + EVT_PRGS_STAT_CD='10' 조건을 만족하는 이벤트만 포함합니다. 결과는 EVT_STRT_DTIME
    내림차순 정렬.

    Args:
        goods_no (str): 상품 번호 (예: G000000317693)
        lang_cd (str | Unset): 이벤트명 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductApplicableEventsResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
        lang_cd=lang_cd,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    goods_no: str,
    lang_cd: str | Unset = "ko",
) -> HTTPValidationError | ProductApplicableEventsResponse | None:
    """상품 적용 가능 이벤트 조회

     특정 상품(goods_no)에 적용 가능한 진행 중 이벤트 목록을 반환합니다. CC_EVT_APLY_INFO 의 50(상품 단위) / 80(패턴 단위) 매핑을 모두 검사하며, 전시
    기간(SYSDATE BETWEEN) + DISP_YN='Y' + EVT_PRGS_STAT_CD='10' 조건을 만족하는 이벤트만 포함합니다. 결과는 EVT_STRT_DTIME
    내림차순 정렬.

    Args:
        goods_no (str): 상품 번호 (예: G000000317693)
        lang_cd (str | Unset): 이벤트명 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductApplicableEventsResponse
    """

    return sync_detailed(
        client=client,
        goods_no=goods_no,
        lang_cd=lang_cd,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    goods_no: str,
    lang_cd: str | Unset = "ko",
) -> Response[HTTPValidationError | ProductApplicableEventsResponse]:
    """상품 적용 가능 이벤트 조회

     특정 상품(goods_no)에 적용 가능한 진행 중 이벤트 목록을 반환합니다. CC_EVT_APLY_INFO 의 50(상품 단위) / 80(패턴 단위) 매핑을 모두 검사하며, 전시
    기간(SYSDATE BETWEEN) + DISP_YN='Y' + EVT_PRGS_STAT_CD='10' 조건을 만족하는 이벤트만 포함합니다. 결과는 EVT_STRT_DTIME
    내림차순 정렬.

    Args:
        goods_no (str): 상품 번호 (예: G000000317693)
        lang_cd (str | Unset): 이벤트명 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductApplicableEventsResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
        lang_cd=lang_cd,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    goods_no: str,
    lang_cd: str | Unset = "ko",
) -> HTTPValidationError | ProductApplicableEventsResponse | None:
    """상품 적용 가능 이벤트 조회

     특정 상품(goods_no)에 적용 가능한 진행 중 이벤트 목록을 반환합니다. CC_EVT_APLY_INFO 의 50(상품 단위) / 80(패턴 단위) 매핑을 모두 검사하며, 전시
    기간(SYSDATE BETWEEN) + DISP_YN='Y' + EVT_PRGS_STAT_CD='10' 조건을 만족하는 이벤트만 포함합니다. 결과는 EVT_STRT_DTIME
    내림차순 정렬.

    Args:
        goods_no (str): 상품 번호 (예: G000000317693)
        lang_cd (str | Unset): 이벤트명 언어 코드 (기본값: ko) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductApplicableEventsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no=goods_no,
            lang_cd=lang_cd,
        )
    ).parsed
