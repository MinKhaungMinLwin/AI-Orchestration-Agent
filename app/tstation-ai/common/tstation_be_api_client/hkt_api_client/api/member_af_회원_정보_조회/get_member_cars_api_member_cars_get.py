from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.member_car_list_response import MemberCarListResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    mbr_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["mbr_no"] = mbr_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/cars",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MemberCarListResponse | None:
    if response.status_code == 200:
        response_200 = MemberCarListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MemberCarListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    mbr_no: str,
) -> Response[HTTPValidationError | MemberCarListResponse]:
    """회원 등록 차량 정보 조회

     회원번호(mbr_no)에 등록된 차량 정보를 조회합니다.

    Args:
        mbr_no (str): 회원 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MemberCarListResponse]
    """

    kwargs = _get_kwargs(
        mbr_no=mbr_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    mbr_no: str,
) -> HTTPValidationError | MemberCarListResponse | None:
    """회원 등록 차량 정보 조회

     회원번호(mbr_no)에 등록된 차량 정보를 조회합니다.

    Args:
        mbr_no (str): 회원 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MemberCarListResponse
    """

    return sync_detailed(
        client=client,
        mbr_no=mbr_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mbr_no: str,
) -> Response[HTTPValidationError | MemberCarListResponse]:
    """회원 등록 차량 정보 조회

     회원번호(mbr_no)에 등록된 차량 정보를 조회합니다.

    Args:
        mbr_no (str): 회원 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MemberCarListResponse]
    """

    kwargs = _get_kwargs(
        mbr_no=mbr_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    mbr_no: str,
) -> HTTPValidationError | MemberCarListResponse | None:
    """회원 등록 차량 정보 조회

     회원번호(mbr_no)에 등록된 차량 정보를 조회합니다.

    Args:
        mbr_no (str): 회원 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MemberCarListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            mbr_no=mbr_no,
        )
    ).parsed
