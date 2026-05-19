from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.coupon_stacking_check_response import CouponStackingCheckResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    cpn_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["cpn_no"] = cpn_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/coupons/stacking-check",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CouponStackingCheckResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CouponStackingCheckResponse.from_dict(response.json())

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
) -> Response[CouponStackingCheckResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    cpn_no: str,
) -> Response[CouponStackingCheckResponse | HTTPValidationError]:
    """쿠폰 중복 적용 가능 여부 조회

     입력한 쿠폰 번호들 (2~5개) 의 `CC_CPN_BASE` 정보 (`CPN_TP_CD`, `CPN_DUP_USE_YN`) 를 조회한 뒤 DBA 가이드의 중복 적용 룰을 적용하여
    모든 2-쌍 조합의 판정 결과를 반환합니다.

    **룰 요약**:
    - (상품 10, 결제 20) 모두 Y → 중복 가능 / 한쪽이라도 N → 불가.
    - (10 or 20) + (서비스 30 or 플러스 40) → 항상 가능.
    - 그 외 조합 (가이드 명시 없음) → `can_stack=null` fallback.

    Args:
        cpn_no (str): 쿠폰 번호 목록 (2~5개). 예: ``[C72000953lIVn, C68000886MSJJ]`` 또는
            ``C72000953lIVn,C68000886MSJJ``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponStackingCheckResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        cpn_no=cpn_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    cpn_no: str,
) -> CouponStackingCheckResponse | HTTPValidationError | None:
    """쿠폰 중복 적용 가능 여부 조회

     입력한 쿠폰 번호들 (2~5개) 의 `CC_CPN_BASE` 정보 (`CPN_TP_CD`, `CPN_DUP_USE_YN`) 를 조회한 뒤 DBA 가이드의 중복 적용 룰을 적용하여
    모든 2-쌍 조합의 판정 결과를 반환합니다.

    **룰 요약**:
    - (상품 10, 결제 20) 모두 Y → 중복 가능 / 한쪽이라도 N → 불가.
    - (10 or 20) + (서비스 30 or 플러스 40) → 항상 가능.
    - 그 외 조합 (가이드 명시 없음) → `can_stack=null` fallback.

    Args:
        cpn_no (str): 쿠폰 번호 목록 (2~5개). 예: ``[C72000953lIVn, C68000886MSJJ]`` 또는
            ``C72000953lIVn,C68000886MSJJ``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponStackingCheckResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        cpn_no=cpn_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    cpn_no: str,
) -> Response[CouponStackingCheckResponse | HTTPValidationError]:
    """쿠폰 중복 적용 가능 여부 조회

     입력한 쿠폰 번호들 (2~5개) 의 `CC_CPN_BASE` 정보 (`CPN_TP_CD`, `CPN_DUP_USE_YN`) 를 조회한 뒤 DBA 가이드의 중복 적용 룰을 적용하여
    모든 2-쌍 조합의 판정 결과를 반환합니다.

    **룰 요약**:
    - (상품 10, 결제 20) 모두 Y → 중복 가능 / 한쪽이라도 N → 불가.
    - (10 or 20) + (서비스 30 or 플러스 40) → 항상 가능.
    - 그 외 조합 (가이드 명시 없음) → `can_stack=null` fallback.

    Args:
        cpn_no (str): 쿠폰 번호 목록 (2~5개). 예: ``[C72000953lIVn, C68000886MSJJ]`` 또는
            ``C72000953lIVn,C68000886MSJJ``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponStackingCheckResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        cpn_no=cpn_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    cpn_no: str,
) -> CouponStackingCheckResponse | HTTPValidationError | None:
    """쿠폰 중복 적용 가능 여부 조회

     입력한 쿠폰 번호들 (2~5개) 의 `CC_CPN_BASE` 정보 (`CPN_TP_CD`, `CPN_DUP_USE_YN`) 를 조회한 뒤 DBA 가이드의 중복 적용 룰을 적용하여
    모든 2-쌍 조합의 판정 결과를 반환합니다.

    **룰 요약**:
    - (상품 10, 결제 20) 모두 Y → 중복 가능 / 한쪽이라도 N → 불가.
    - (10 or 20) + (서비스 30 or 플러스 40) → 항상 가능.
    - 그 외 조합 (가이드 명시 없음) → `can_stack=null` fallback.

    Args:
        cpn_no (str): 쿠폰 번호 목록 (2~5개). 예: ``[C72000953lIVn, C68000886MSJJ]`` 또는
            ``C72000953lIVn,C68000886MSJJ``.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponStackingCheckResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            cpn_no=cpn_no,
        )
    ).parsed
