from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.maintenance_history_response import MaintenanceHistoryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    mbr_car_reg_seq: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_mbr_car_reg_seq: None | str | Unset
    if isinstance(mbr_car_reg_seq, Unset):
        json_mbr_car_reg_seq = UNSET
    else:
        json_mbr_car_reg_seq = mbr_car_reg_seq
    params["mbr_car_reg_seq"] = json_mbr_car_reg_seq

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/maintenance-history",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MaintenanceHistoryResponse | None:
    if response.status_code == 200:
        response_200 = MaintenanceHistoryResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MaintenanceHistoryResponse]:
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
    limit: int | Unset = 5,
) -> Response[HTTPValidationError | MaintenanceHistoryResponse]:
    """회원 최근 정비이력 조회

     JWT 회원번호 기준으로 최근 5년 내 오프라인 정비 완료 이력과 온라인 주문 장착 완료 이력을 통합해 정비/장착일 내림차순으로 반환합니다.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 회원 차량 등록/통합 시퀀스. 미지정 시 회원 인증 차량 전체.
        limit (int | Unset): 반환할 최대 이력 수. 기본 5건. Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceHistoryResponse]
    """

    kwargs = _get_kwargs(
        mbr_car_reg_seq=mbr_car_reg_seq,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> HTTPValidationError | MaintenanceHistoryResponse | None:
    """회원 최근 정비이력 조회

     JWT 회원번호 기준으로 최근 5년 내 오프라인 정비 완료 이력과 온라인 주문 장착 완료 이력을 통합해 정비/장착일 내림차순으로 반환합니다.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 회원 차량 등록/통합 시퀀스. 미지정 시 회원 인증 차량 전체.
        limit (int | Unset): 반환할 최대 이력 수. 기본 5건. Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceHistoryResponse
    """

    return sync_detailed(
        client=client,
        mbr_car_reg_seq=mbr_car_reg_seq,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> Response[HTTPValidationError | MaintenanceHistoryResponse]:
    """회원 최근 정비이력 조회

     JWT 회원번호 기준으로 최근 5년 내 오프라인 정비 완료 이력과 온라인 주문 장착 완료 이력을 통합해 정비/장착일 내림차순으로 반환합니다.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 회원 차량 등록/통합 시퀀스. 미지정 시 회원 인증 차량 전체.
        limit (int | Unset): 반환할 최대 이력 수. 기본 5건. Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceHistoryResponse]
    """

    kwargs = _get_kwargs(
        mbr_car_reg_seq=mbr_car_reg_seq,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    mbr_car_reg_seq: None | str | Unset = UNSET,
    limit: int | Unset = 5,
) -> HTTPValidationError | MaintenanceHistoryResponse | None:
    """회원 최근 정비이력 조회

     JWT 회원번호 기준으로 최근 5년 내 오프라인 정비 완료 이력과 온라인 주문 장착 완료 이력을 통합해 정비/장착일 내림차순으로 반환합니다.

    Args:
        mbr_car_reg_seq (None | str | Unset): 조회 대상 회원 차량 등록/통합 시퀀스. 미지정 시 회원 인증 차량 전체.
        limit (int | Unset): 반환할 최대 이력 수. 기본 5건. Default: 5.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceHistoryResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            mbr_car_reg_seq=mbr_car_reg_seq,
            limit=limit,
        )
    ).parsed
