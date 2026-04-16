from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.car_trim_response import CarTrimResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    car_model_det: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["car_model_det"] = car_model_det

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/vehicle/trims",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CarTrimResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CarTrimResponse.from_dict(response.json())

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
) -> Response[CarTrimResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    car_model_det: str,
) -> Response[CarTrimResponse | HTTPValidationError]:
    """차종 트림 목록 조회 (2단계)

     CAR_MODEL_DET로 해당 모델의 세부 트림(연식/차량명/출시코드) 목록을 반환합니다.

    Args:
        car_model_det (str): 차량 상세 모델명 (예: '더 뉴 K7(VG)')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarTrimResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_model_det=car_model_det,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    car_model_det: str,
) -> CarTrimResponse | HTTPValidationError | None:
    """차종 트림 목록 조회 (2단계)

     CAR_MODEL_DET로 해당 모델의 세부 트림(연식/차량명/출시코드) 목록을 반환합니다.

    Args:
        car_model_det (str): 차량 상세 모델명 (예: '더 뉴 K7(VG)')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarTrimResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        car_model_det=car_model_det,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    car_model_det: str,
) -> Response[CarTrimResponse | HTTPValidationError]:
    """차종 트림 목록 조회 (2단계)

     CAR_MODEL_DET로 해당 모델의 세부 트림(연식/차량명/출시코드) 목록을 반환합니다.

    Args:
        car_model_det (str): 차량 상세 모델명 (예: '더 뉴 K7(VG)')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarTrimResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_model_det=car_model_det,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    car_model_det: str,
) -> CarTrimResponse | HTTPValidationError | None:
    """차종 트림 목록 조회 (2단계)

     CAR_MODEL_DET로 해당 모델의 세부 트림(연식/차량명/출시코드) 목록을 반환합니다.

    Args:
        car_model_det (str): 차량 상세 모델명 (예: '더 뉴 K7(VG)')

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarTrimResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            car_model_det=car_model_det,
        )
    ).parsed
