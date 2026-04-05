from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.message_create import MessageCreate
from ...models.message_response import MessageResponse
from ...types import Response


def _get_kwargs(
    *,
    body: MessageCreate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/messages",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MessageResponse | None:
    if response.status_code == 201:
        response_201 = MessageResponse.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | MessageResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: MessageCreate,
) -> Response[HTTPValidationError | MessageResponse]:
    """새 메시지 저장 및 어시스턴트 응답 처리

     사용자 메시지를 status='received'로 저장합니다. 이후 Agent/LLM 호출 결과를 어시스턴트 메시지로 status='completed'와 함께 삽입합니다. LLM
    호출 실패 시 사용자 메시지 status를 'failed'로 업데이트합니다.

    Args:
        body (MessageCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MessageResponse]
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
    body: MessageCreate,
) -> HTTPValidationError | MessageResponse | None:
    """새 메시지 저장 및 어시스턴트 응답 처리

     사용자 메시지를 status='received'로 저장합니다. 이후 Agent/LLM 호출 결과를 어시스턴트 메시지로 status='completed'와 함께 삽입합니다. LLM
    호출 실패 시 사용자 메시지 status를 'failed'로 업데이트합니다.

    Args:
        body (MessageCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MessageResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: MessageCreate,
) -> Response[HTTPValidationError | MessageResponse]:
    """새 메시지 저장 및 어시스턴트 응답 처리

     사용자 메시지를 status='received'로 저장합니다. 이후 Agent/LLM 호출 결과를 어시스턴트 메시지로 status='completed'와 함께 삽입합니다. LLM
    호출 실패 시 사용자 메시지 status를 'failed'로 업데이트합니다.

    Args:
        body (MessageCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MessageResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: MessageCreate,
) -> HTTPValidationError | MessageResponse | None:
    """새 메시지 저장 및 어시스턴트 응답 처리

     사용자 메시지를 status='received'로 저장합니다. 이후 Agent/LLM 호출 결과를 어시스턴트 메시지로 status='completed'와 함께 삽입합니다. LLM
    호출 실패 시 사용자 메시지 status를 'failed'로 업데이트합니다.

    Args:
        body (MessageCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MessageResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
