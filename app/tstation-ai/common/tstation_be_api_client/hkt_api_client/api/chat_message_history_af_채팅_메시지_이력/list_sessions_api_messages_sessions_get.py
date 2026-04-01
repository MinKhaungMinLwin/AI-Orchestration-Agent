from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.session_list_response import SessionListResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/messages/sessions",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> SessionListResponse | None:
    if response.status_code == 200:
        response_200 = SessionListResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[SessionListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[SessionListResponse]:
    """사용자 세션 목록 조회

     인증된 사용자(user_id)의 모든 채팅 세션을 마지막 메시지 일시 내림차순으로 반환합니다. 각 세션의 마지막 메시지 시각(last_message_at)과 메시지
    수(msg_count)를 포함합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SessionListResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> SessionListResponse | None:
    """사용자 세션 목록 조회

     인증된 사용자(user_id)의 모든 채팅 세션을 마지막 메시지 일시 내림차순으로 반환합니다. 각 세션의 마지막 메시지 시각(last_message_at)과 메시지
    수(msg_count)를 포함합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SessionListResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[SessionListResponse]:
    """사용자 세션 목록 조회

     인증된 사용자(user_id)의 모든 채팅 세션을 마지막 메시지 일시 내림차순으로 반환합니다. 각 세션의 마지막 메시지 시각(last_message_at)과 메시지
    수(msg_count)를 포함합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SessionListResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> SessionListResponse | None:
    """사용자 세션 목록 조회

     인증된 사용자(user_id)의 모든 채팅 세션을 마지막 메시지 일시 내림차순으로 반환합니다. 각 세션의 마지막 메시지 시각(last_message_at)과 메시지
    수(msg_count)를 포함합니다.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SessionListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
