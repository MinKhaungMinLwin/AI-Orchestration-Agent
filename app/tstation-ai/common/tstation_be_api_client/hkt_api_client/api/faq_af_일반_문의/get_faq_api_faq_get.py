from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.faq_list_response import FaqListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    lrcl_cd: None | str | Unset = UNSET,
    mdcl_cd: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_lrcl_cd: None | str | Unset
    if isinstance(lrcl_cd, Unset):
        json_lrcl_cd = UNSET
    else:
        json_lrcl_cd = lrcl_cd
    params["lrcl_cd"] = json_lrcl_cd

    json_mdcl_cd: None | str | Unset
    if isinstance(mdcl_cd, Unset):
        json_mdcl_cd = UNSET
    else:
        json_mdcl_cd = mdcl_cd
    params["mdcl_cd"] = json_mdcl_cd

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/faq",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FaqListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FaqListResponse.from_dict(response.json())

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
) -> Response[FaqListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    lrcl_cd: None | str | Unset = UNSET,
    mdcl_cd: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> Response[FaqListResponse | HTTPValidationError]:
    """FAQ 목록 조회

     CS_CUST_INQ_MGMT_INFO에서 FAQ 데이터(INQ_TYPE_CD='FAQ')만 조회합니다. 1:1 문의 내역은 개인정보 보호를 위해 제외됩니다.
    lrcl_cd(대분류), mdcl_cd(중분류)로 필터링할 수 있습니다.

    Args:
        lrcl_cd (None | str | Unset): 대분류 코드 필터 (LRCL_CD)
        mdcl_cd (None | str | Unset): 중분류 코드 필터 (MDCL_CD)
        limit (int | Unset): 반환할 FAQ 수 (기본 50, 최대 200) Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FaqListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lrcl_cd=lrcl_cd,
        mdcl_cd=mdcl_cd,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    lrcl_cd: None | str | Unset = UNSET,
    mdcl_cd: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> FaqListResponse | HTTPValidationError | None:
    """FAQ 목록 조회

     CS_CUST_INQ_MGMT_INFO에서 FAQ 데이터(INQ_TYPE_CD='FAQ')만 조회합니다. 1:1 문의 내역은 개인정보 보호를 위해 제외됩니다.
    lrcl_cd(대분류), mdcl_cd(중분류)로 필터링할 수 있습니다.

    Args:
        lrcl_cd (None | str | Unset): 대분류 코드 필터 (LRCL_CD)
        mdcl_cd (None | str | Unset): 중분류 코드 필터 (MDCL_CD)
        limit (int | Unset): 반환할 FAQ 수 (기본 50, 최대 200) Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FaqListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        lrcl_cd=lrcl_cd,
        mdcl_cd=mdcl_cd,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    lrcl_cd: None | str | Unset = UNSET,
    mdcl_cd: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> Response[FaqListResponse | HTTPValidationError]:
    """FAQ 목록 조회

     CS_CUST_INQ_MGMT_INFO에서 FAQ 데이터(INQ_TYPE_CD='FAQ')만 조회합니다. 1:1 문의 내역은 개인정보 보호를 위해 제외됩니다.
    lrcl_cd(대분류), mdcl_cd(중분류)로 필터링할 수 있습니다.

    Args:
        lrcl_cd (None | str | Unset): 대분류 코드 필터 (LRCL_CD)
        mdcl_cd (None | str | Unset): 중분류 코드 필터 (MDCL_CD)
        limit (int | Unset): 반환할 FAQ 수 (기본 50, 최대 200) Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FaqListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        lrcl_cd=lrcl_cd,
        mdcl_cd=mdcl_cd,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    lrcl_cd: None | str | Unset = UNSET,
    mdcl_cd: None | str | Unset = UNSET,
    limit: int | Unset = 50,
) -> FaqListResponse | HTTPValidationError | None:
    """FAQ 목록 조회

     CS_CUST_INQ_MGMT_INFO에서 FAQ 데이터(INQ_TYPE_CD='FAQ')만 조회합니다. 1:1 문의 내역은 개인정보 보호를 위해 제외됩니다.
    lrcl_cd(대분류), mdcl_cd(중분류)로 필터링할 수 있습니다.

    Args:
        lrcl_cd (None | str | Unset): 대분류 코드 필터 (LRCL_CD)
        mdcl_cd (None | str | Unset): 중분류 코드 필터 (MDCL_CD)
        limit (int | Unset): 반환할 FAQ 수 (기본 50, 최대 200) Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FaqListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            lrcl_cd=lrcl_cd,
            mdcl_cd=mdcl_cd,
            limit=limit,
        )
    ).parsed
