from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.store_install_availability_request import StoreInstallAvailabilityRequest
from ...models.store_install_availability_response import StoreInstallAvailabilityResponse
from ...types import Response


def _get_kwargs(
    *,
    body: StoreInstallAvailabilityRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/store/install-availability",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | StoreInstallAvailabilityResponse | None:
    if response.status_code == 200:
        response_200 = StoreInstallAvailabilityResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | StoreInstallAvailabilityResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: StoreInstallAvailabilityRequest,
) -> Response[HTTPValidationError | StoreInstallAvailabilityResponse]:
    """매장별 가장 빠른 장착 가능 일정 통합 조회

     매장 ID 목록과 상품/수량을 입력하면 BE가 물류 재고, 매장 재고, 스케줄 mode를 계산해 매장별 가장 빠른 장착 가능 슬롯과 전체 가능 슬롯을 반환합니다. goods_no가
    없으면 재고 판단 없이 단순 방문 예약 범위(general)로 조회합니다.

    Args:
        body (StoreInstallAvailabilityRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreInstallAvailabilityResponse]
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
    body: StoreInstallAvailabilityRequest,
) -> HTTPValidationError | StoreInstallAvailabilityResponse | None:
    """매장별 가장 빠른 장착 가능 일정 통합 조회

     매장 ID 목록과 상품/수량을 입력하면 BE가 물류 재고, 매장 재고, 스케줄 mode를 계산해 매장별 가장 빠른 장착 가능 슬롯과 전체 가능 슬롯을 반환합니다. goods_no가
    없으면 재고 판단 없이 단순 방문 예약 범위(general)로 조회합니다.

    Args:
        body (StoreInstallAvailabilityRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreInstallAvailabilityResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: StoreInstallAvailabilityRequest,
) -> Response[HTTPValidationError | StoreInstallAvailabilityResponse]:
    """매장별 가장 빠른 장착 가능 일정 통합 조회

     매장 ID 목록과 상품/수량을 입력하면 BE가 물류 재고, 매장 재고, 스케줄 mode를 계산해 매장별 가장 빠른 장착 가능 슬롯과 전체 가능 슬롯을 반환합니다. goods_no가
    없으면 재고 판단 없이 단순 방문 예약 범위(general)로 조회합니다.

    Args:
        body (StoreInstallAvailabilityRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | StoreInstallAvailabilityResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: StoreInstallAvailabilityRequest,
) -> HTTPValidationError | StoreInstallAvailabilityResponse | None:
    """매장별 가장 빠른 장착 가능 일정 통합 조회

     매장 ID 목록과 상품/수량을 입력하면 BE가 물류 재고, 매장 재고, 스케줄 mode를 계산해 매장별 가장 빠른 장착 가능 슬롯과 전체 가능 슬롯을 반환합니다. goods_no가
    없으면 재고 판단 없이 단순 방문 예약 범위(general)로 조회합니다.

    Args:
        body (StoreInstallAvailabilityRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | StoreInstallAvailabilityResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
