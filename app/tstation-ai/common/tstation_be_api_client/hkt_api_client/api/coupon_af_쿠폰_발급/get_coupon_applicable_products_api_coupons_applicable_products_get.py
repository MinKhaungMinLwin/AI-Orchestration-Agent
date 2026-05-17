from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.coupon_deal_applicable_products_response import CouponDealApplicableProductsResponse
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
        "url": "/api/coupons/applicable-products",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CouponDealApplicableProductsResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CouponDealApplicableProductsResponse.from_dict(response.json())

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
) -> Response[CouponDealApplicableProductsResponse | HTTPValidationError]:
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
) -> Response[CouponDealApplicableProductsResponse | HTTPValidationError]:
    """쿠폰/기획전 기준 적용 상품 조회

     쿠폰 번호(cpn_no) 와/또는 기획전 번호(deal_no) 에 매핑된 적용 가능한 상품 목록을 각각의 키별로 그룹핑해 반환합니다. cpn_no, deal_no 모두
    ``[C1,C2]`` 또는 ``C1,C2`` 형식의 단일 쿼리 문자열로 전달하며 각각 최대 10/10 개까지 허용됩니다. 양쪽 모두 비어 있으면 200 OK + 빈 배열을
    반환합니다. deal_no 는 CC_DEAL_CPN_INFO 를 통해 매핑된 쿠폰 → CC_CPN_APLY_INFO 의 상품으로 join 됩니다.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 목록 (0~10개). 예: ``[C0000001234, C0000005678]`` 또는
            ``C0000001234,C0000005678``. 빈 문자열/``[]`` 허용. Default: ''.
        deal_no (str | Unset): 기획전 번호 목록 (0~10개). 예: ``[D0000001234, D0000005678]`` 또는
            ``D0000001234,D0000005678``. 빈 문자열/``[]`` 허용. Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponDealApplicableProductsResponse | HTTPValidationError]
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
) -> CouponDealApplicableProductsResponse | HTTPValidationError | None:
    """쿠폰/기획전 기준 적용 상품 조회

     쿠폰 번호(cpn_no) 와/또는 기획전 번호(deal_no) 에 매핑된 적용 가능한 상품 목록을 각각의 키별로 그룹핑해 반환합니다. cpn_no, deal_no 모두
    ``[C1,C2]`` 또는 ``C1,C2`` 형식의 단일 쿼리 문자열로 전달하며 각각 최대 10/10 개까지 허용됩니다. 양쪽 모두 비어 있으면 200 OK + 빈 배열을
    반환합니다. deal_no 는 CC_DEAL_CPN_INFO 를 통해 매핑된 쿠폰 → CC_CPN_APLY_INFO 의 상품으로 join 됩니다.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 목록 (0~10개). 예: ``[C0000001234, C0000005678]`` 또는
            ``C0000001234,C0000005678``. 빈 문자열/``[]`` 허용. Default: ''.
        deal_no (str | Unset): 기획전 번호 목록 (0~10개). 예: ``[D0000001234, D0000005678]`` 또는
            ``D0000001234,D0000005678``. 빈 문자열/``[]`` 허용. Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponDealApplicableProductsResponse | HTTPValidationError
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
) -> Response[CouponDealApplicableProductsResponse | HTTPValidationError]:
    """쿠폰/기획전 기준 적용 상품 조회

     쿠폰 번호(cpn_no) 와/또는 기획전 번호(deal_no) 에 매핑된 적용 가능한 상품 목록을 각각의 키별로 그룹핑해 반환합니다. cpn_no, deal_no 모두
    ``[C1,C2]`` 또는 ``C1,C2`` 형식의 단일 쿼리 문자열로 전달하며 각각 최대 10/10 개까지 허용됩니다. 양쪽 모두 비어 있으면 200 OK + 빈 배열을
    반환합니다. deal_no 는 CC_DEAL_CPN_INFO 를 통해 매핑된 쿠폰 → CC_CPN_APLY_INFO 의 상품으로 join 됩니다.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 목록 (0~10개). 예: ``[C0000001234, C0000005678]`` 또는
            ``C0000001234,C0000005678``. 빈 문자열/``[]`` 허용. Default: ''.
        deal_no (str | Unset): 기획전 번호 목록 (0~10개). 예: ``[D0000001234, D0000005678]`` 또는
            ``D0000001234,D0000005678``. 빈 문자열/``[]`` 허용. Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CouponDealApplicableProductsResponse | HTTPValidationError]
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
) -> CouponDealApplicableProductsResponse | HTTPValidationError | None:
    """쿠폰/기획전 기준 적용 상품 조회

     쿠폰 번호(cpn_no) 와/또는 기획전 번호(deal_no) 에 매핑된 적용 가능한 상품 목록을 각각의 키별로 그룹핑해 반환합니다. cpn_no, deal_no 모두
    ``[C1,C2]`` 또는 ``C1,C2`` 형식의 단일 쿼리 문자열로 전달하며 각각 최대 10/10 개까지 허용됩니다. 양쪽 모두 비어 있으면 200 OK + 빈 배열을
    반환합니다. deal_no 는 CC_DEAL_CPN_INFO 를 통해 매핑된 쿠폰 → CC_CPN_APLY_INFO 의 상품으로 join 됩니다.

    Args:
        cpn_no (str | Unset): 쿠폰 번호 목록 (0~10개). 예: ``[C0000001234, C0000005678]`` 또는
            ``C0000001234,C0000005678``. 빈 문자열/``[]`` 허용. Default: ''.
        deal_no (str | Unset): 기획전 번호 목록 (0~10개). 예: ``[D0000001234, D0000005678]`` 또는
            ``D0000001234,D0000005678``. 빈 문자열/``[]`` 허용. Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CouponDealApplicableProductsResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            cpn_no=cpn_no,
            deal_no=deal_no,
        )
    ).parsed
