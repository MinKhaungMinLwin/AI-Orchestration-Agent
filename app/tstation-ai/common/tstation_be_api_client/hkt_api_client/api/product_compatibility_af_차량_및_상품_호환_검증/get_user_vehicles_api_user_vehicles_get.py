from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.user_vehicle_lookup_response import UserVehicleLookupResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    car_no: str,
    owner_nm: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["car_no"] = car_no

    params["owner_nm"] = owner_nm

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/user/vehicles",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UserVehicleLookupResponse | None:
    if response.status_code == 200:
        response_200 = UserVehicleLookupResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | UserVehicleLookupResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    car_no: str,
    owner_nm: str,
) -> Response[HTTPValidationError | UserVehicleLookupResponse]:
    """Get User Vehicles

    Args:
        car_no (str): 자동차 등록번호
        owner_nm (str): 소유자 이름

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserVehicleLookupResponse]
    """

    kwargs = _get_kwargs(
        car_no=car_no,
        owner_nm=owner_nm,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    car_no: str,
    owner_nm: str,
) -> HTTPValidationError | UserVehicleLookupResponse | None:
    """Get User Vehicles

    Args:
        car_no (str): 자동차 등록번호
        owner_nm (str): 소유자 이름

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserVehicleLookupResponse
    """

    return sync_detailed(
        client=client,
        car_no=car_no,
        owner_nm=owner_nm,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    car_no: str,
    owner_nm: str,
) -> Response[HTTPValidationError | UserVehicleLookupResponse]:
    """Get User Vehicles

    Args:
        car_no (str): 자동차 등록번호
        owner_nm (str): 소유자 이름

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserVehicleLookupResponse]
    """

    kwargs = _get_kwargs(
        car_no=car_no,
        owner_nm=owner_nm,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    car_no: str,
    owner_nm: str,
) -> HTTPValidationError | UserVehicleLookupResponse | None:
    """Get User Vehicles

    Args:
        car_no (str): 자동차 등록번호
        owner_nm (str): 소유자 이름

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserVehicleLookupResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            car_no=car_no,
            owner_nm=owner_nm,
        )
    ).parsed
