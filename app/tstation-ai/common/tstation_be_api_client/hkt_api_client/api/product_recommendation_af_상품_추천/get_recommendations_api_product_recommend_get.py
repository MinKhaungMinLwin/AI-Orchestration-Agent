from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rcmd_type import RcmdType
from ...models.recommendation_response import RecommendationResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_rcmd_type = rcmd_type.value
    params["rcmd_type"] = json_rcmd_type

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/recommend",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | RecommendationResponse | None:
    if response.status_code == 200:
        response_200 = RecommendationResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | RecommendationResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`FST_DISP_YN='Y'`, `TOT_SCR*10` 높은 순, `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecommendationResponse]
    """

    kwargs = _get_kwargs(
        rcmd_type=rcmd_type,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`FST_DISP_YN='Y'`, `TOT_SCR*10` 높은 순, `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecommendationResponse
    """

    return sync_detailed(
        client=client,
        rcmd_type=rcmd_type,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
) -> Response[HTTPValidationError | RecommendationResponse]:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`FST_DISP_YN='Y'`, `TOT_SCR*10` 높은 순, `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecommendationResponse]
    """

    kwargs = _get_kwargs(
        rcmd_type=rcmd_type,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    rcmd_type: RcmdType,
    limit: int | Unset = 10,
) -> HTTPValidationError | RecommendationResponse | None:
    """상품 추천

     추천 타입(rcmd_type)에 따라 상위 N개 상품을 반환합니다.

    - **tstation**: 티스테이션 추천 (`FST_DISP_YN='Y'`, `TOT_SCR*10` 높은 순, `PR_GOODS_RCMD_SUM`)
    - **discount**: 최고 할인율 (`EXTRA_FVR_SALE_PER` 높은 순, `PR_GOODS_DSCNT_PRC_INFO`)
    - **value**: 가성비 Good (할인가 20만 원 이하, 수명·연비 높은 순, `PR_GOODS_DSCNT_PRC_INFO` + `PR_GOODS_RCMD_SUM`)

    Args:
        rcmd_type (RcmdType):
        limit (int | Unset): 반환할 상품 수 (기본 10, 최대 100) Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecommendationResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            rcmd_type=rcmd_type,
            limit=limit,
        )
    ).parsed
