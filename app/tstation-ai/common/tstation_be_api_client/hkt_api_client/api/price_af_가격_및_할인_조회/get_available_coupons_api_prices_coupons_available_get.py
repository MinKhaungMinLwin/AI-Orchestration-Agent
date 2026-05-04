from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.available_coupon_response import AvailableCouponResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    lang_cd: str | Unset = "ko",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["lang_cd"] = lang_cd

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/prices/coupons/available",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AvailableCouponResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AvailableCouponResponse.from_dict(response.json())

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
) -> Response[AvailableCouponResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    lang_cd: str | Unset = "ko",
) -> Response[AvailableCouponResponse | HTTPValidationError]:
    """다운로드 가능 쿠폰 조회

     현재 사용자가 다운로드 가능한 쿠폰 목록을 조회합니다.

    Args:
        lang_cd (str | Unset): 언어 코드 (기본값: 'ko' 한국어) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AvailableCouponResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lang_cd=lang_cd,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    lang_cd: str | Unset = "ko",
) -> AvailableCouponResponse | HTTPValidationError | None:
    """다운로드 가능 쿠폰 조회

     현재 사용자가 다운로드 가능한 쿠폰 목록을 조회합니다.

    Args:
        lang_cd (str | Unset): 언어 코드 (기본값: 'ko' 한국어) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AvailableCouponResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        lang_cd=lang_cd,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    lang_cd: str | Unset = "ko",
) -> Response[AvailableCouponResponse | HTTPValidationError]:
    """다운로드 가능 쿠폰 조회

     현재 사용자가 다운로드 가능한 쿠폰 목록을 조회합니다.

    Args:
        lang_cd (str | Unset): 언어 코드 (기본값: 'ko' 한국어) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AvailableCouponResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lang_cd=lang_cd,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    lang_cd: str | Unset = "ko",
) -> AvailableCouponResponse | HTTPValidationError | None:
    """다운로드 가능 쿠폰 조회

     현재 사용자가 다운로드 가능한 쿠폰 목록을 조회합니다.

    Args:
        lang_cd (str | Unset): 언어 코드 (기본값: 'ko' 한국어) Default: 'ko'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AvailableCouponResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            lang_cd=lang_cd,
        )
    ).parsed
