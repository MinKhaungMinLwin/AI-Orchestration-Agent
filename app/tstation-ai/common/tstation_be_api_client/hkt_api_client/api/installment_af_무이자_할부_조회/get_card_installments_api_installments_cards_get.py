from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.card_installment_list_response import CardInstallmentListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    tgt_amt: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_tgt_amt: int | None | Unset
    if isinstance(tgt_amt, Unset):
        json_tgt_amt = UNSET
    else:
        json_tgt_amt = tgt_amt
    params["tgt_amt"] = json_tgt_amt

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/installments/cards",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CardInstallmentListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CardInstallmentListResponse.from_dict(response.json())

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
) -> Response[CardInstallmentListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    tgt_amt: int | None | Unset = UNSET,
) -> Response[CardInstallmentListResponse | HTTPValidationError]:
    """진행중 무이자 할부 카드 목록 조회

     진행중인 카드사별 무이자 할부 정보를 반환합니다. 각 row 는 (카드사, 결제유형, 기준금액) 단위이며, 가능한 개월수(2~24)는 months 리스트로 집계됩니다.
    tgt_amt 를 주면 그 금액 이상부터 적용되는 기준금액 행만 반환합니다 (TGT_AMT <= tgt_amt). AI 응답에서 payment_type 은 사용자에게 노출하지
    마세요 — 실제 결제는 챗봇 밖에서 진행됩니다.

    Args:
        tgt_amt (int | None | Unset): 결제 예상 금액 (원). 지정하면 NDI.TGT_AMT <= tgt_amt 인 행만 반환. 미지정 시 전체
            진행중 카드.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CardInstallmentListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tgt_amt=tgt_amt,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    tgt_amt: int | None | Unset = UNSET,
) -> CardInstallmentListResponse | HTTPValidationError | None:
    """진행중 무이자 할부 카드 목록 조회

     진행중인 카드사별 무이자 할부 정보를 반환합니다. 각 row 는 (카드사, 결제유형, 기준금액) 단위이며, 가능한 개월수(2~24)는 months 리스트로 집계됩니다.
    tgt_amt 를 주면 그 금액 이상부터 적용되는 기준금액 행만 반환합니다 (TGT_AMT <= tgt_amt). AI 응답에서 payment_type 은 사용자에게 노출하지
    마세요 — 실제 결제는 챗봇 밖에서 진행됩니다.

    Args:
        tgt_amt (int | None | Unset): 결제 예상 금액 (원). 지정하면 NDI.TGT_AMT <= tgt_amt 인 행만 반환. 미지정 시 전체
            진행중 카드.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CardInstallmentListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        tgt_amt=tgt_amt,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    tgt_amt: int | None | Unset = UNSET,
) -> Response[CardInstallmentListResponse | HTTPValidationError]:
    """진행중 무이자 할부 카드 목록 조회

     진행중인 카드사별 무이자 할부 정보를 반환합니다. 각 row 는 (카드사, 결제유형, 기준금액) 단위이며, 가능한 개월수(2~24)는 months 리스트로 집계됩니다.
    tgt_amt 를 주면 그 금액 이상부터 적용되는 기준금액 행만 반환합니다 (TGT_AMT <= tgt_amt). AI 응답에서 payment_type 은 사용자에게 노출하지
    마세요 — 실제 결제는 챗봇 밖에서 진행됩니다.

    Args:
        tgt_amt (int | None | Unset): 결제 예상 금액 (원). 지정하면 NDI.TGT_AMT <= tgt_amt 인 행만 반환. 미지정 시 전체
            진행중 카드.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CardInstallmentListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tgt_amt=tgt_amt,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    tgt_amt: int | None | Unset = UNSET,
) -> CardInstallmentListResponse | HTTPValidationError | None:
    """진행중 무이자 할부 카드 목록 조회

     진행중인 카드사별 무이자 할부 정보를 반환합니다. 각 row 는 (카드사, 결제유형, 기준금액) 단위이며, 가능한 개월수(2~24)는 months 리스트로 집계됩니다.
    tgt_amt 를 주면 그 금액 이상부터 적용되는 기준금액 행만 반환합니다 (TGT_AMT <= tgt_amt). AI 응답에서 payment_type 은 사용자에게 노출하지
    마세요 — 실제 결제는 챗봇 밖에서 진행됩니다.

    Args:
        tgt_amt (int | None | Unset): 결제 예상 금액 (원). 지정하면 NDI.TGT_AMT <= tgt_amt 인 행만 반환. 미지정 시 전체
            진행중 카드.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CardInstallmentListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            tgt_amt=tgt_amt,
        )
    ).parsed
