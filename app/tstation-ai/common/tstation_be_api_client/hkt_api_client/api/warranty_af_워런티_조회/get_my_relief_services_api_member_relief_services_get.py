from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.member_relief_service_list_response import MemberReliefServiceListResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/relief-services",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> MemberReliefServiceListResponse | None:
    if response.status_code == 200:
        response_200 = MemberReliefServiceListResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[MemberReliefServiceListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[MemberReliefServiceListResponse]:
    """회원 안심서비스 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 VW_ET_MBR_RELIEF_MAST_INFO 의 안심서비스 가입/보상 이력을 조회합니다. JOIN_DTIME 이 있는 이력만
    가입일자시간 내림차순으로 반환합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberReliefServiceListResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> MemberReliefServiceListResponse | None:
    """회원 안심서비스 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 VW_ET_MBR_RELIEF_MAST_INFO 의 안심서비스 가입/보상 이력을 조회합니다. JOIN_DTIME 이 있는 이력만
    가입일자시간 내림차순으로 반환합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberReliefServiceListResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[MemberReliefServiceListResponse]:
    """회원 안심서비스 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 VW_ET_MBR_RELIEF_MAST_INFO 의 안심서비스 가입/보상 이력을 조회합니다. JOIN_DTIME 이 있는 이력만
    가입일자시간 내림차순으로 반환합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberReliefServiceListResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> MemberReliefServiceListResponse | None:
    """회원 안심서비스 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 VW_ET_MBR_RELIEF_MAST_INFO 의 안심서비스 가입/보상 이력을 조회합니다. JOIN_DTIME 이 있는 이력만
    가입일자시간 내림차순으로 반환합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberReliefServiceListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
