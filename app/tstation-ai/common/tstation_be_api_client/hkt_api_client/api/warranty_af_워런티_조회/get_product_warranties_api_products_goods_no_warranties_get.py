from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_warranties_response import ProductWarrantiesResponse
from ...types import Response


def _get_kwargs(
    goods_no: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/products/{goods_no}/warranties".format(
            goods_no=quote(str(goods_no), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductWarrantiesResponse | None:
    if response.status_code == 200:
        response_200 = ProductWarrantiesResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductWarrantiesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    goods_no: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | ProductWarrantiesResponse]:
    """상품에 적용 가능한 워런티 종류 조회

     상품번호(GOODS_NO) 로 패턴 코드(PR_GOODS_BASE.PTRN_CD) 를 찾고, ET_DGTL_WRT_APLY_INFO 에서 WRT_TGT_YN='Y' 인 적용 가능
    워런티 목록을 반환합니다. WRT_TP_CD='20' + PLPR_YN='Y' 행은 응답에서 '안심서비스' / '안심플러스' 2건으로 분리됩니다. 상품이 존재하지 않으면
    ptrn_cd=null, warranties=[].

    Args:
        goods_no (str): 상품 번호 (PR_GOODS_BASE.GOODS_NO)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductWarrantiesResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    goods_no: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | ProductWarrantiesResponse | None:
    """상품에 적용 가능한 워런티 종류 조회

     상품번호(GOODS_NO) 로 패턴 코드(PR_GOODS_BASE.PTRN_CD) 를 찾고, ET_DGTL_WRT_APLY_INFO 에서 WRT_TGT_YN='Y' 인 적용 가능
    워런티 목록을 반환합니다. WRT_TP_CD='20' + PLPR_YN='Y' 행은 응답에서 '안심서비스' / '안심플러스' 2건으로 분리됩니다. 상품이 존재하지 않으면
    ptrn_cd=null, warranties=[].

    Args:
        goods_no (str): 상품 번호 (PR_GOODS_BASE.GOODS_NO)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductWarrantiesResponse
    """

    return sync_detailed(
        goods_no=goods_no,
        client=client,
    ).parsed


async def asyncio_detailed(
    goods_no: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | ProductWarrantiesResponse]:
    """상품에 적용 가능한 워런티 종류 조회

     상품번호(GOODS_NO) 로 패턴 코드(PR_GOODS_BASE.PTRN_CD) 를 찾고, ET_DGTL_WRT_APLY_INFO 에서 WRT_TGT_YN='Y' 인 적용 가능
    워런티 목록을 반환합니다. WRT_TP_CD='20' + PLPR_YN='Y' 행은 응답에서 '안심서비스' / '안심플러스' 2건으로 분리됩니다. 상품이 존재하지 않으면
    ptrn_cd=null, warranties=[].

    Args:
        goods_no (str): 상품 번호 (PR_GOODS_BASE.GOODS_NO)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductWarrantiesResponse]
    """

    kwargs = _get_kwargs(
        goods_no=goods_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    goods_no: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | ProductWarrantiesResponse | None:
    """상품에 적용 가능한 워런티 종류 조회

     상품번호(GOODS_NO) 로 패턴 코드(PR_GOODS_BASE.PTRN_CD) 를 찾고, ET_DGTL_WRT_APLY_INFO 에서 WRT_TGT_YN='Y' 인 적용 가능
    워런티 목록을 반환합니다. WRT_TP_CD='20' + PLPR_YN='Y' 행은 응답에서 '안심서비스' / '안심플러스' 2건으로 분리됩니다. 상품이 존재하지 않으면
    ptrn_cd=null, warranties=[].

    Args:
        goods_no (str): 상품 번호 (PR_GOODS_BASE.GOODS_NO)

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductWarrantiesResponse
    """

    return (
        await asyncio_detailed(
            goods_no=goods_no,
            client=client,
        )
    ).parsed
