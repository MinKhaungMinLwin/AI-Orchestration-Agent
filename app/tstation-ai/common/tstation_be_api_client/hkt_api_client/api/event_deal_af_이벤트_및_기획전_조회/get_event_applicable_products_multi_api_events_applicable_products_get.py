from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.multi_event_applicable_products_response import MultiEventApplicableProductsResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    evt_no: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["evt_no"] = evt_no

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/events/applicable-products",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MultiEventApplicableProductsResponse | None:
    if response.status_code == 200:
        response_200 = MultiEventApplicableProductsResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MultiEventApplicableProductsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    evt_no: str,
) -> Response[HTTPValidationError | MultiEventApplicableProductsResponse]:
    """다중 이벤트 적용 가능 상품 조회

     여러 이벤트에 적용 가능한 상품 목록을 이벤트별로 그룹핑해 반환합니다. 한 번에 최대 10개의 이벤트까지 조회 가능합니다. evt_no 는 ``[E0001, E0002]`` 또는
    ``E0001,E0002`` 형식의 단일 쿼리 문자열로 전달합니다. 결과는 evt_no IN (...) 한 번의 쿼리로 처리되어, 단일 이벤트 N회 호출보다 round-trip
    비용이 낮습니다.

    Args:
        evt_no (str): 이벤트 번호 목록 (1~10개). 예: ``[E000001234, E000005678]`` 또는
            ``E000001234,E000005678``

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MultiEventApplicableProductsResponse]
    """

    kwargs = _get_kwargs(
        evt_no=evt_no,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    evt_no: str,
) -> HTTPValidationError | MultiEventApplicableProductsResponse | None:
    """다중 이벤트 적용 가능 상품 조회

     여러 이벤트에 적용 가능한 상품 목록을 이벤트별로 그룹핑해 반환합니다. 한 번에 최대 10개의 이벤트까지 조회 가능합니다. evt_no 는 ``[E0001, E0002]`` 또는
    ``E0001,E0002`` 형식의 단일 쿼리 문자열로 전달합니다. 결과는 evt_no IN (...) 한 번의 쿼리로 처리되어, 단일 이벤트 N회 호출보다 round-trip
    비용이 낮습니다.

    Args:
        evt_no (str): 이벤트 번호 목록 (1~10개). 예: ``[E000001234, E000005678]`` 또는
            ``E000001234,E000005678``

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MultiEventApplicableProductsResponse
    """

    return sync_detailed(
        client=client,
        evt_no=evt_no,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    evt_no: str,
) -> Response[HTTPValidationError | MultiEventApplicableProductsResponse]:
    """다중 이벤트 적용 가능 상품 조회

     여러 이벤트에 적용 가능한 상품 목록을 이벤트별로 그룹핑해 반환합니다. 한 번에 최대 10개의 이벤트까지 조회 가능합니다. evt_no 는 ``[E0001, E0002]`` 또는
    ``E0001,E0002`` 형식의 단일 쿼리 문자열로 전달합니다. 결과는 evt_no IN (...) 한 번의 쿼리로 처리되어, 단일 이벤트 N회 호출보다 round-trip
    비용이 낮습니다.

    Args:
        evt_no (str): 이벤트 번호 목록 (1~10개). 예: ``[E000001234, E000005678]`` 또는
            ``E000001234,E000005678``

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MultiEventApplicableProductsResponse]
    """

    kwargs = _get_kwargs(
        evt_no=evt_no,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    evt_no: str,
) -> HTTPValidationError | MultiEventApplicableProductsResponse | None:
    """다중 이벤트 적용 가능 상품 조회

     여러 이벤트에 적용 가능한 상품 목록을 이벤트별로 그룹핑해 반환합니다. 한 번에 최대 10개의 이벤트까지 조회 가능합니다. evt_no 는 ``[E0001, E0002]`` 또는
    ``E0001,E0002`` 형식의 단일 쿼리 문자열로 전달합니다. 결과는 evt_no IN (...) 한 번의 쿼리로 처리되어, 단일 이벤트 N회 호출보다 round-trip
    비용이 낮습니다.

    Args:
        evt_no (str): 이벤트 번호 목록 (1~10개). 예: ``[E000001234, E000005678]`` 또는
            ``E000001234,E000005678``

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MultiEventApplicableProductsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            evt_no=evt_no,
        )
    ).parsed
