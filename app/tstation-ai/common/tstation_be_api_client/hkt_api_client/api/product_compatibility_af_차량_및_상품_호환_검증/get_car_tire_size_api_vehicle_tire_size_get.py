from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.car_tire_size_response import CarTireSizeResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    *,
    car_lnc_cd: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["car_lnc_cd"] = car_lnc_cd

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/vehicle/tire-size",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CarTireSizeResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CarTireSizeResponse.from_dict(response.json())

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
) -> Response[CarTireSizeResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    car_lnc_cd: str,
) -> Response[CarTireSizeResponse | HTTPValidationError]:
    """차량 타이어 사이즈 조회 (3단계)

     CAR_LNC_CD로 해당 차량의 전륜/후륜 타이어 사이즈를 반환합니다.

    Args:
        car_lnc_cd (str): 차량 출시 코드

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarTireSizeResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_lnc_cd=car_lnc_cd,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    car_lnc_cd: str,
) -> CarTireSizeResponse | HTTPValidationError | None:
    """차량 타이어 사이즈 조회 (3단계)

     CAR_LNC_CD로 해당 차량의 전륜/후륜 타이어 사이즈를 반환합니다.

    Args:
        car_lnc_cd (str): 차량 출시 코드

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarTireSizeResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        car_lnc_cd=car_lnc_cd,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    car_lnc_cd: str,
) -> Response[CarTireSizeResponse | HTTPValidationError]:
    """차량 타이어 사이즈 조회 (3단계)

     CAR_LNC_CD로 해당 차량의 전륜/후륜 타이어 사이즈를 반환합니다.

    Args:
        car_lnc_cd (str): 차량 출시 코드

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CarTireSizeResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        car_lnc_cd=car_lnc_cd,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    car_lnc_cd: str,
) -> CarTireSizeResponse | HTTPValidationError | None:
    """차량 타이어 사이즈 조회 (3단계)

     CAR_LNC_CD로 해당 차량의 전륜/후륜 타이어 사이즈를 반환합니다.

    Args:
        car_lnc_cd (str): 차량 출시 코드

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CarTireSizeResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            car_lnc_cd=car_lnc_cd,
        )
    ).parsed
