from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.member_warranty_list_response import MemberWarrantyListResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/warranties",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> MemberWarrantyListResponse | None:
    if response.status_code == 200:
        response_200 = MemberWarrantyListResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[MemberWarrantyListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[MemberWarrantyListResponse]:
    """회원 보유 워런티 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 ET_DGTL_WRT_REG_INFO 의 가입 이력을 조회합니다. WRT_PRGS_STAT_CD IN ('200', '300',
    '400') 만 반환 ('100' 가입대기 제외). 가입일자(WRT_REG_DATE) 내림차순. 보유 워런티가 없으면 빈 리스트.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberWarrantyListResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> MemberWarrantyListResponse | None:
    """회원 보유 워런티 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 ET_DGTL_WRT_REG_INFO 의 가입 이력을 조회합니다. WRT_PRGS_STAT_CD IN ('200', '300',
    '400') 만 반환 ('100' 가입대기 제외). 가입일자(WRT_REG_DATE) 내림차순. 보유 워런티가 없으면 빈 리스트.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberWarrantyListResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[MemberWarrantyListResponse]:
    """회원 보유 워런티 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 ET_DGTL_WRT_REG_INFO 의 가입 이력을 조회합니다. WRT_PRGS_STAT_CD IN ('200', '300',
    '400') 만 반환 ('100' 가입대기 제외). 가입일자(WRT_REG_DATE) 내림차순. 보유 워런티가 없으면 빈 리스트.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[MemberWarrantyListResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> MemberWarrantyListResponse | None:
    """회원 보유 워런티 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 로 ET_DGTL_WRT_REG_INFO 의 가입 이력을 조회합니다. WRT_PRGS_STAT_CD IN ('200', '300',
    '400') 만 반환 ('100' 가입대기 제외). 가입일자(WRT_REG_DATE) 내림차순. 보유 워런티가 없으면 빈 리스트.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        MemberWarrantyListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
