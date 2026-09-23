from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.favorite_store_list_response import FavoriteStoreListResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/member/favorite-stores",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FavoriteStoreListResponse | None:
    if response.status_code == 200:
        response_200 = FavoriteStoreListResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[FavoriteStoreListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[FavoriteStoreListResponse]:
    """회원 단골매장 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 기준으로 ET_MBR_MYSHOP_INFO 에서 MYSHOP_INFO_STS_CD='100' (단골) 상태인 매장을 조회합니다. 폐점/비활성
    매장 (SHOP_STAT_SCT_CD != '100' 또는 SMART_SHOP_STAT_SCT_CD = '300') 은 제외됩니다. 응답은 매장 목록(/api/store/list)
    과 동일한 StoreListItem 모양에 단골 등록 일시(favored_at) 만 추가된 형태이며, 매장명 가나다 순으로 정렬됩니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FavoriteStoreListResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> FavoriteStoreListResponse | None:
    """회원 단골매장 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 기준으로 ET_MBR_MYSHOP_INFO 에서 MYSHOP_INFO_STS_CD='100' (단골) 상태인 매장을 조회합니다. 폐점/비활성
    매장 (SHOP_STAT_SCT_CD != '100' 또는 SMART_SHOP_STAT_SCT_CD = '300') 은 제외됩니다. 응답은 매장 목록(/api/store/list)
    과 동일한 StoreListItem 모양에 단골 등록 일시(favored_at) 만 추가된 형태이며, 매장명 가나다 순으로 정렬됩니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FavoriteStoreListResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[FavoriteStoreListResponse]:
    """회원 단골매장 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 기준으로 ET_MBR_MYSHOP_INFO 에서 MYSHOP_INFO_STS_CD='100' (단골) 상태인 매장을 조회합니다. 폐점/비활성
    매장 (SHOP_STAT_SCT_CD != '100' 또는 SMART_SHOP_STAT_SCT_CD = '300') 은 제외됩니다. 응답은 매장 목록(/api/store/list)
    과 동일한 StoreListItem 모양에 단골 등록 일시(favored_at) 만 추가된 형태이며, 매장명 가나다 순으로 정렬됩니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FavoriteStoreListResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> FavoriteStoreListResponse | None:
    """회원 단골매장 목록 조회

     JWT 토큰의 회원번호(MBR_NO) 기준으로 ET_MBR_MYSHOP_INFO 에서 MYSHOP_INFO_STS_CD='100' (단골) 상태인 매장을 조회합니다. 폐점/비활성
    매장 (SHOP_STAT_SCT_CD != '100' 또는 SMART_SHOP_STAT_SCT_CD = '300') 은 제외됩니다. 응답은 매장 목록(/api/store/list)
    과 동일한 StoreListItem 모양에 단골 등록 일시(favored_at) 만 추가된 형태이며, 매장명 가나다 순으로 정렬됩니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FavoriteStoreListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
