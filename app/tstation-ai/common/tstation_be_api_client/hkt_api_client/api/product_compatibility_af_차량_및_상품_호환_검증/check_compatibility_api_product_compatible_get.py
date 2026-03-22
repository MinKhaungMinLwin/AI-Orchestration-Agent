from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.compatibility_response import CompatibilityResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    car_no: None | str | Unset = UNSET,
    car_nm: None | str | Unset = UNSET,
    goods_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_car_no: None | str | Unset
    if isinstance(car_no, Unset):
        json_car_no = UNSET
    else:
        json_car_no = car_no
    params["car_no"] = json_car_no

    json_car_nm: None | str | Unset
    if isinstance(car_nm, Unset):
        json_car_nm = UNSET
    else:
        json_car_nm = car_nm
    params["car_nm"] = json_car_nm

    params["goods_no"] = goods_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/product/compatible",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CompatibilityResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CompatibilityResponse.from_dict(response.json())

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
) -> Response[CompatibilityResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    car_no: None | str | Unset = UNSET,
    car_nm: None | str | Unset = UNSET,
    goods_no: str,
) -> Response[CompatibilityResponse | HTTPValidationError]:
    """차량-상품 타이어 호환 검증

     차량번호(CAR_NO)로 VW_ET_MBR_CAR_INFO에서 전/후륜 타이어 사이즈를 조회하거나 차량정보(CAR_NM)로 PR_CAR_BASE + PR_CAR_ATTR에서
    전/후륜 타이어 사이즈를 조회하고, 상품번호(GOODS_NO)로 PR_GOODS_BASE에서 타이어 스펙(단면폭/편평비/인치)을 조회하여 호환 여부를 반환합니다. 카젠 API 연동
    전까지 내부 DB 정보를 우선 활용합니다.

    Args:
        car_no (None | str | Unset): 차량 번호
        car_nm (None | str | Unset): 차량 정보
        goods_no (str): 상품 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CompatibilityResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_no=car_no,
        car_nm=car_nm,
        goods_no=goods_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    car_no: None | str | Unset = UNSET,
    car_nm: None | str | Unset = UNSET,
    goods_no: str,
) -> CompatibilityResponse | HTTPValidationError | None:
    """차량-상품 타이어 호환 검증

     차량번호(CAR_NO)로 VW_ET_MBR_CAR_INFO에서 전/후륜 타이어 사이즈를 조회하거나 차량정보(CAR_NM)로 PR_CAR_BASE + PR_CAR_ATTR에서
    전/후륜 타이어 사이즈를 조회하고, 상품번호(GOODS_NO)로 PR_GOODS_BASE에서 타이어 스펙(단면폭/편평비/인치)을 조회하여 호환 여부를 반환합니다. 카젠 API 연동
    전까지 내부 DB 정보를 우선 활용합니다.

    Args:
        car_no (None | str | Unset): 차량 번호
        car_nm (None | str | Unset): 차량 정보
        goods_no (str): 상품 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CompatibilityResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        car_no=car_no,
        car_nm=car_nm,
        goods_no=goods_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    car_no: None | str | Unset = UNSET,
    car_nm: None | str | Unset = UNSET,
    goods_no: str,
) -> Response[CompatibilityResponse | HTTPValidationError]:
    """차량-상품 타이어 호환 검증

     차량번호(CAR_NO)로 VW_ET_MBR_CAR_INFO에서 전/후륜 타이어 사이즈를 조회하거나 차량정보(CAR_NM)로 PR_CAR_BASE + PR_CAR_ATTR에서
    전/후륜 타이어 사이즈를 조회하고, 상품번호(GOODS_NO)로 PR_GOODS_BASE에서 타이어 스펙(단면폭/편평비/인치)을 조회하여 호환 여부를 반환합니다. 카젠 API 연동
    전까지 내부 DB 정보를 우선 활용합니다.

    Args:
        car_no (None | str | Unset): 차량 번호
        car_nm (None | str | Unset): 차량 정보
        goods_no (str): 상품 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CompatibilityResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_no=car_no,
        car_nm=car_nm,
        goods_no=goods_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    car_no: None | str | Unset = UNSET,
    car_nm: None | str | Unset = UNSET,
    goods_no: str,
) -> CompatibilityResponse | HTTPValidationError | None:
    """차량-상품 타이어 호환 검증

     차량번호(CAR_NO)로 VW_ET_MBR_CAR_INFO에서 전/후륜 타이어 사이즈를 조회하거나 차량정보(CAR_NM)로 PR_CAR_BASE + PR_CAR_ATTR에서
    전/후륜 타이어 사이즈를 조회하고, 상품번호(GOODS_NO)로 PR_GOODS_BASE에서 타이어 스펙(단면폭/편평비/인치)을 조회하여 호환 여부를 반환합니다. 카젠 API 연동
    전까지 내부 DB 정보를 우선 활용합니다.

    Args:
        car_no (None | str | Unset): 차량 번호
        car_nm (None | str | Unset): 차량 정보
        goods_no (str): 상품 번호

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CompatibilityResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            car_no=car_no,
            car_nm=car_nm,
            goods_no=goods_no,
        )
    ).parsed
