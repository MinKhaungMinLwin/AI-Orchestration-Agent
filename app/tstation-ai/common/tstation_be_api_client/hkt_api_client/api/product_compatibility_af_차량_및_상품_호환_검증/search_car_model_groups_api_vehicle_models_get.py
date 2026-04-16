from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.car_model_group_response import CarModelGroupResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    keyword: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["keyword"] = keyword

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/vehicle/models",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CarModelGroupResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CarModelGroupResponse.from_dict(response.json())

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
) -> Response[CarModelGroupResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    keyword: str,
) -> Response[CarModelGroupResponse | HTTPValidationError]:
    """차종 모델 그룹 검색 (1단계)

     차량 모델명 키워드로 CAR_MODEL_DET 그룹별 요약을 반환합니다. 각 그룹에 연식 범위(year_from~year_to)와 트림 수(trim_count)가 포함됩니다.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: 'K7', '소나타')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarModelGroupResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    keyword: str,
) -> CarModelGroupResponse | HTTPValidationError | None:
    """차종 모델 그룹 검색 (1단계)

     차량 모델명 키워드로 CAR_MODEL_DET 그룹별 요약을 반환합니다. 각 그룹에 연식 범위(year_from~year_to)와 트림 수(trim_count)가 포함됩니다.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: 'K7', '소나타')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarModelGroupResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        keyword=keyword,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    keyword: str,
) -> Response[CarModelGroupResponse | HTTPValidationError]:
    """차종 모델 그룹 검색 (1단계)

     차량 모델명 키워드로 CAR_MODEL_DET 그룹별 요약을 반환합니다. 각 그룹에 연식 범위(year_from~year_to)와 트림 수(trim_count)가 포함됩니다.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: 'K7', '소나타')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarModelGroupResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        keyword=keyword,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    keyword: str,
) -> CarModelGroupResponse | HTTPValidationError | None:
    """차종 모델 그룹 검색 (1단계)

     차량 모델명 키워드로 CAR_MODEL_DET 그룹별 요약을 반환합니다. 각 그룹에 연식 범위(year_from~year_to)와 트림 수(trim_count)가 포함됩니다.

    Args:
        keyword (str): 검색할 차량 모델명 키워드 (예: 'K7', '소나타')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarModelGroupResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            keyword=keyword,
        )
    ).parsed
