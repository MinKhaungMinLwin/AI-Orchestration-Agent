from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.set_order_form_ai_response_data_type_0 import SetOrderFormAIResponseDataType0


T = TypeVar("T", bound="SetOrderFormAIResponse")


@_attrs_define
class SetOrderFormAIResponse:
    """
    Attributes:
        result (bool): 성공/실패 여부
        message (None | str | Unset): 실패시 메시지
        drt_pur_yn (None | str | Unset): 주문하기 여부
        data (None | SetOrderFormAIResponseDataType0 | Unset): 주문하기 페이지 이동에 필요한 데이터
    """

    result: bool
    message: None | str | Unset = UNSET
    drt_pur_yn: None | str | Unset = UNSET
    data: None | SetOrderFormAIResponseDataType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.set_order_form_ai_response_data_type_0 import SetOrderFormAIResponseDataType0

        result = self.result

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message

        drt_pur_yn: None | str | Unset
        if isinstance(self.drt_pur_yn, Unset):
            drt_pur_yn = UNSET
        else:
            drt_pur_yn = self.drt_pur_yn

        data: dict[str, Any] | None | Unset
        if isinstance(self.data, Unset):
            data = UNSET
        elif isinstance(self.data, SetOrderFormAIResponseDataType0):
            data = self.data.to_dict()
        else:
            data = self.data

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "result": result,
            }
        )
        if message is not UNSET:
            field_dict["message"] = message
        if drt_pur_yn is not UNSET:
            field_dict["drtPurYn"] = drt_pur_yn
        if data is not UNSET:
            field_dict["data"] = data

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.set_order_form_ai_response_data_type_0 import SetOrderFormAIResponseDataType0

        d = dict(src_dict)
        result = d.pop("result")

        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))

        def _parse_drt_pur_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        drt_pur_yn = _parse_drt_pur_yn(d.pop("drtPurYn", UNSET))

        def _parse_data(data: object) -> None | SetOrderFormAIResponseDataType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                data_type_0 = SetOrderFormAIResponseDataType0.from_dict(data)

                return data_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SetOrderFormAIResponseDataType0 | Unset, data)

        data = _parse_data(d.pop("data", UNSET))

        set_order_form_ai_response = cls(
            result=result,
            message=message,
            drt_pur_yn=drt_pur_yn,
            data=data,
        )

        set_order_form_ai_response.additional_properties = d
        return set_order_form_ai_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
