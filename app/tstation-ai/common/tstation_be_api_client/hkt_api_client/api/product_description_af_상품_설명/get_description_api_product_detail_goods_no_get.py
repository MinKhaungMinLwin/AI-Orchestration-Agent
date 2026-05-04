from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.product_desc_response import ProductDescResponse
from ...types import Response


def _get_kwargs(
    goods_no: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/detail/{goods_no}".format(
            goods_no=quote(str(goods_no), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ProductDescResponse | None:
    if response.status_code == 200:
        response_200 = ProductDescResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ProductDescResponse]:
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
) -> Response[HTTPValidationError | ProductDescResponse]:
    """상품 설명 조회

     상품 번호로 PR_GOODS_BASE → PR_PATTERN_BASE를 조인하여 특장점(PC_PROD_REMARK_DESC), 기술력(PC_PROD_TECH_DESC),
    슬로건(SLOGAN)을 조회하고, PR_PTRN_IMG_INFO에서 이미지 및 썸네일 경로 목록을 반환합니다.

    Args:
        goods_no (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductDescResponse]
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
) -> HTTPValidationError | ProductDescResponse | None:
    """상품 설명 조회

     상품 번호로 PR_GOODS_BASE → PR_PATTERN_BASE를 조인하여 특장점(PC_PROD_REMARK_DESC), 기술력(PC_PROD_TECH_DESC),
    슬로건(SLOGAN)을 조회하고, PR_PTRN_IMG_INFO에서 이미지 및 썸네일 경로 목록을 반환합니다.

    Args:
        goods_no (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductDescResponse
    """

    return sync_detailed(
        goods_no=goods_no,
        client=client,
    ).parsed


async def asyncio_detailed(
    goods_no: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | ProductDescResponse]:
    """상품 설명 조회

     상품 번호로 PR_GOODS_BASE → PR_PATTERN_BASE를 조인하여 특장점(PC_PROD_REMARK_DESC), 기술력(PC_PROD_TECH_DESC),
    슬로건(SLOGAN)을 조회하고, PR_PTRN_IMG_INFO에서 이미지 및 썸네일 경로 목록을 반환합니다.

    Args:
        goods_no (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ProductDescResponse]
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
) -> HTTPValidationError | ProductDescResponse | None:
    """상품 설명 조회

     상품 번호로 PR_GOODS_BASE → PR_PATTERN_BASE를 조인하여 특장점(PC_PROD_REMARK_DESC), 기술력(PC_PROD_TECH_DESC),
    슬로건(SLOGAN)을 조회하고, PR_PTRN_IMG_INFO에서 이미지 및 썸네일 경로 목록을 반환합니다.

    Args:
        goods_no (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ProductDescResponse
    """

    return (
        await asyncio_detailed(
            goods_no=goods_no,
            client=client,
        )
    ).parsed
