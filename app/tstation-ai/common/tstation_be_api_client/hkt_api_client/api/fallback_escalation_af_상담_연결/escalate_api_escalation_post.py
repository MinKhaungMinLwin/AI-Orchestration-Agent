from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.escalation_request import EscalationRequest
from ...models.escalation_response import EscalationResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: EscalationRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/escalation",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> EscalationResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = EscalationResponse.from_dict(response.json())

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
) -> Response[EscalationResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: EscalationRequest,
) -> Response[EscalationResponse | HTTPValidationError]:
    """상담 연결 분기 처리

     대화량과 문의 유형에 따라 3가지 분기로 처리합니다.

    - **with_summary**: 대화 메시지 수 ≥ 기준치(`ESCALATION_MSG_THRESHOLD`, 기본 3)이고 요약(`summary`)이 있는 경우 — 요약을
    `summary` 쿼리 파라미터로 URL 인코딩하여 전달
    - **direct**: 대화량이 적거나 요약이 없는 경우 — 요약 없이 상담 페이지로 바로 전달
    - **policy**: `inq_type_cd`가 정책 테이블에 등록된 경우 — 지정 채널(call/email 등)로 분기

    **summary URL 파라미터 규격**: `summary` 키, URL 인코딩(percent-encoding) 적용, 예)
    `?inq_type_cd=ORDER&mbr_no=M001&summary=%EB%B0%B0%EC%86%A1+...`

    Args:
        body (EscalationRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscalationResponse | HTTPValidationError]
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
    body: EscalationRequest,
) -> EscalationResponse | HTTPValidationError | None:
    """상담 연결 분기 처리

     대화량과 문의 유형에 따라 3가지 분기로 처리합니다.

    - **with_summary**: 대화 메시지 수 ≥ 기준치(`ESCALATION_MSG_THRESHOLD`, 기본 3)이고 요약(`summary`)이 있는 경우 — 요약을
    `summary` 쿼리 파라미터로 URL 인코딩하여 전달
    - **direct**: 대화량이 적거나 요약이 없는 경우 — 요약 없이 상담 페이지로 바로 전달
    - **policy**: `inq_type_cd`가 정책 테이블에 등록된 경우 — 지정 채널(call/email 등)로 분기

    **summary URL 파라미터 규격**: `summary` 키, URL 인코딩(percent-encoding) 적용, 예)
    `?inq_type_cd=ORDER&mbr_no=M001&summary=%EB%B0%B0%EC%86%A1+...`

    Args:
        body (EscalationRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscalationResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: EscalationRequest,
) -> Response[EscalationResponse | HTTPValidationError]:
    """상담 연결 분기 처리

     대화량과 문의 유형에 따라 3가지 분기로 처리합니다.

    - **with_summary**: 대화 메시지 수 ≥ 기준치(`ESCALATION_MSG_THRESHOLD`, 기본 3)이고 요약(`summary`)이 있는 경우 — 요약을
    `summary` 쿼리 파라미터로 URL 인코딩하여 전달
    - **direct**: 대화량이 적거나 요약이 없는 경우 — 요약 없이 상담 페이지로 바로 전달
    - **policy**: `inq_type_cd`가 정책 테이블에 등록된 경우 — 지정 채널(call/email 등)로 분기

    **summary URL 파라미터 규격**: `summary` 키, URL 인코딩(percent-encoding) 적용, 예)
    `?inq_type_cd=ORDER&mbr_no=M001&summary=%EB%B0%B0%EC%86%A1+...`

    Args:
        body (EscalationRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[EscalationResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: EscalationRequest,
) -> EscalationResponse | HTTPValidationError | None:
    """상담 연결 분기 처리

     대화량과 문의 유형에 따라 3가지 분기로 처리합니다.

    - **with_summary**: 대화 메시지 수 ≥ 기준치(`ESCALATION_MSG_THRESHOLD`, 기본 3)이고 요약(`summary`)이 있는 경우 — 요약을
    `summary` 쿼리 파라미터로 URL 인코딩하여 전달
    - **direct**: 대화량이 적거나 요약이 없는 경우 — 요약 없이 상담 페이지로 바로 전달
    - **policy**: `inq_type_cd`가 정책 테이블에 등록된 경우 — 지정 채널(call/email 등)로 분기

    **summary URL 파라미터 규격**: `summary` 키, URL 인코딩(percent-encoding) 적용, 예)
    `?inq_type_cd=ORDER&mbr_no=M001&summary=%EB%B0%B0%EC%86%A1+...`

    Args:
        body (EscalationRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        EscalationResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
