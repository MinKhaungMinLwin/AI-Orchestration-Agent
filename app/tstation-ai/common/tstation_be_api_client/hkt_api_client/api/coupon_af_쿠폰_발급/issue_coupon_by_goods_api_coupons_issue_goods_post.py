from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.coupon_issue_response import CouponIssueResponse
from ...models.goods_coupon_issue_request import GoodsCouponIssueRequest
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: GoodsCouponIssueRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/coupons/issue/goods",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CouponIssueResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CouponIssueResponse.from_dict(response.json())

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
) -> Response[CouponIssueResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: GoodsCouponIssueRequest,
) -> Response[CouponIssueResponse | HTTPValidationError]:
    """상품번호 기반 쿠폰 발급

     상품번호(goodsNo)에 해당하는 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰)을 발급합니다. 회원번호와 제휴사번호는 JWT 에서 자동으로 채워집니다.

    Args:
        body (GoodsCouponIssueRequest): 상품번호 기반 발급 — 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰) 묶음 발급.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponIssueResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: GoodsCouponIssueRequest,
) -> CouponIssueResponse | HTTPValidationError | None:
    """상품번호 기반 쿠폰 발급

     상품번호(goodsNo)에 해당하는 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰)을 발급합니다. 회원번호와 제휴사번호는 JWT 에서 자동으로 채워집니다.

    Args:
        body (GoodsCouponIssueRequest): 상품번호 기반 발급 — 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰) 묶음 발급.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponIssueResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: GoodsCouponIssueRequest,
) -> Response[CouponIssueResponse | HTTPValidationError]:
    """상품번호 기반 쿠폰 발급

     상품번호(goodsNo)에 해당하는 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰)을 발급합니다. 회원번호와 제휴사번호는 JWT 에서 자동으로 채워집니다.

    Args:
        body (GoodsCouponIssueRequest): 상품번호 기반 발급 — 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰) 묶음 발급.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponIssueResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: GoodsCouponIssueRequest,
) -> CouponIssueResponse | HTTPValidationError | None:
    """상품번호 기반 쿠폰 발급

     상품번호(goodsNo)에 해당하는 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰)을 발급합니다. 회원번호와 제휴사번호는 JWT 에서 자동으로 채워집니다.

    Args:
        body (GoodsCouponIssueRequest): 상품번호 기반 발급 — 최저가 혜택 쿠폰(상품쿠폰 + 결제쿠폰) 묶음 발급.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponIssueResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
