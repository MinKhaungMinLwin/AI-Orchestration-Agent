from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.set_order_form_ai_request import SetOrderFormAIRequest
from ...models.set_order_form_ai_response import SetOrderFormAIResponse
from ...types import Response


def _get_kwargs(
    *,
    body: SetOrderFormAIRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/quick-order/order/setOrderFormAI.do",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> SetOrderFormAIResponse | None:
    if response.status_code == 200:
        response_200 = SetOrderFormAIResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[SetOrderFormAIResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: SetOrderFormAIRequest,
) -> Response[SetOrderFormAIResponse]:
    """AI 퀵쇼핑/장바구니등록 API

     티스테이션 사이트에서 자바스크립트로 실행되는 퀵쇼핑/장바구니 등록 API. 로그인 필수.

    Args:
        body (SetOrderFormAIRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SetOrderFormAIResponse]
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
    body: SetOrderFormAIRequest,
) -> SetOrderFormAIResponse | None:
    """AI 퀵쇼핑/장바구니등록 API

     티스테이션 사이트에서 자바스크립트로 실행되는 퀵쇼핑/장바구니 등록 API. 로그인 필수.

    Args:
        body (SetOrderFormAIRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SetOrderFormAIResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: SetOrderFormAIRequest,
) -> Response[SetOrderFormAIResponse]:
    """AI 퀵쇼핑/장바구니등록 API

     티스테이션 사이트에서 자바스크립트로 실행되는 퀵쇼핑/장바구니 등록 API. 로그인 필수.

    Args:
        body (SetOrderFormAIRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[SetOrderFormAIResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: SetOrderFormAIRequest,
) -> SetOrderFormAIResponse | None:
    """AI 퀵쇼핑/장바구니등록 API

     티스테이션 사이트에서 자바스크립트로 실행되는 퀵쇼핑/장바구니 등록 API. 로그인 필수.

    Args:
        body (SetOrderFormAIRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        SetOrderFormAIResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
