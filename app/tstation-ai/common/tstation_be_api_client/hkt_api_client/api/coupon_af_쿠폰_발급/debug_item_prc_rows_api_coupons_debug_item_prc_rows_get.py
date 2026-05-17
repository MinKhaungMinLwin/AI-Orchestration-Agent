from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.debug_item_prc_rows_api_coupons_debug_item_prc_rows_get_response_debug_item_prc_rows_api_coupons_debug_item_prc_rows_get import (
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    goods_no: str | Unset = "",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["goods_no"] = goods_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/coupons/_debug/item-prc-rows",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet.from_dict(
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
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
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
    goods_no: str | Unset = "",
) -> Response[
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
]:
    """[TEMP] PR_ITEM_PRC_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. goods_no 별 PR_ITEM_PRC_INFO 의 row 를 모든 컬럼과 함께 반환한다. 같은 goods_no 에 대해 여러 행이 나오는
    경우, 어떤 컬럼이 다른지 비교용.

    Args:
        goods_no (str | Unset): 상품 번호 (CSV/bracket, 1~20개) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    goods_no: str | Unset = "",
) -> (
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
    | None
):
    """[TEMP] PR_ITEM_PRC_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. goods_no 별 PR_ITEM_PRC_INFO 의 row 를 모든 컬럼과 함께 반환한다. 같은 goods_no 에 대해 여러 행이 나오는
    경우, 어떤 컬럼이 다른지 비교용.

    Args:
        goods_no (str | Unset): 상품 번호 (CSV/bracket, 1~20개) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        goods_no=goods_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    goods_no: str | Unset = "",
) -> Response[
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
]:
    """[TEMP] PR_ITEM_PRC_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. goods_no 별 PR_ITEM_PRC_INFO 의 row 를 모든 컬럼과 함께 반환한다. 같은 goods_no 에 대해 여러 행이 나오는
    경우, 어떤 컬럼이 다른지 비교용.

    Args:
        goods_no (str | Unset): 상품 번호 (CSV/bracket, 1~20개) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    goods_no: str | Unset = "",
) -> (
    DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet
    | HTTPValidationError
    | None
):
    """[TEMP] PR_ITEM_PRC_INFO raw row dump

     ⚠️ 진단용 임시 endpoint. goods_no 별 PR_ITEM_PRC_INFO 의 row 를 모든 컬럼과 함께 반환한다. 같은 goods_no 에 대해 여러 행이 나오는
    경우, 어떤 컬럼이 다른지 비교용.

    Args:
        goods_no (str | Unset): 상품 번호 (CSV/bracket, 1~20개) Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DebugItemPrcRowsApiCouponsDebugItemPrcRowsGetResponseDebugItemPrcRowsApiCouponsDebugItemPrcRowsGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            goods_no=goods_no,
        )
    ).parsed
