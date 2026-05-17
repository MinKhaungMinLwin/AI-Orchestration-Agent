from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.debug_aply_rows_api_coupons_debug_aply_rows_get_response_debug_aply_rows_api_coupons_debug_aply_rows_get import (
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    cpn_no: str | Unset = "",
    deal_no: str | Unset = "",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["cpn_no"] = cpn_no

    params["deal_no"] = deal_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/coupons/_debug/aply-rows",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError | None
):
    if response.status_code == 200:
        response_200 = DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet.from_dict(
            response.json()
        )

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
) -> Response[
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    cpn_no: str | Unset = "",
    deal_no: str | Unset = "",
) -> Response[
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError
]:
    """[TEMP] CC_CPN_APLY_INFO / CC_DEAL_CPN_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. cpn_no / deal_no 입력에 매칭되는 raw row 를 그대로 반환한다. 매핑 디버깅 후 제거 예정.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 (CSV/bracket, optional) Default: ''.
        deal_no (str | Unset): 기획전 번호 (CSV/bracket, optional) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        cpn_no=cpn_no,
        deal_no=deal_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    cpn_no: str | Unset = "",
    deal_no: str | Unset = "",
) -> (
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError | None
):
    """[TEMP] CC_CPN_APLY_INFO / CC_DEAL_CPN_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. cpn_no / deal_no 입력에 매칭되는 raw row 를 그대로 반환한다. 매핑 디버깅 후 제거 예정.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 (CSV/bracket, optional) Default: ''.
        deal_no (str | Unset): 기획전 번호 (CSV/bracket, optional) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        cpn_no=cpn_no,
        deal_no=deal_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    cpn_no: str | Unset = "",
    deal_no: str | Unset = "",
) -> Response[
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError
]:
    """[TEMP] CC_CPN_APLY_INFO / CC_DEAL_CPN_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. cpn_no / deal_no 입력에 매칭되는 raw row 를 그대로 반환한다. 매핑 디버깅 후 제거 예정.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 (CSV/bracket, optional) Default: ''.
        deal_no (str | Unset): 기획전 번호 (CSV/bracket, optional) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        cpn_no=cpn_no,
        deal_no=deal_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    cpn_no: str | Unset = "",
    deal_no: str | Unset = "",
) -> (
    DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError | None
):
    """[TEMP] CC_CPN_APLY_INFO / CC_DEAL_CPN_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. cpn_no / deal_no 입력에 매칭되는 raw row 를 그대로 반환한다. 매핑 디버깅 후 제거 예정.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 (CSV/bracket, optional) Default: ''.
        deal_no (str | Unset): 기획전 번호 (CSV/bracket, optional) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebugAplyRowsApiCouponsDebugAplyRowsGetResponseDebugAplyRowsApiCouponsDebugAplyRowsGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            cpn_no=cpn_no,
            deal_no=deal_no,
        )
    ).parsed
