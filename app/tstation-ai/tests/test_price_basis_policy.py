from services.tstation.policies.price_basis_policy import has_price_basis, is_positive_number_like


def test_has_price_basis_accepts_shared_price_fields() -> None:
    assert has_price_basis({"finalPrice": "308,200"})
    assert has_price_basis({"cheapest_final_prc": 308200})
    assert has_price_basis({"paymentAmount": 308200.0})


def test_has_price_basis_rejects_empty_zero_and_non_numeric_values() -> None:
    assert not has_price_basis(None)
    assert not has_price_basis({"payment_amount": 0})
    assert not has_price_basis({"payment_amount": "0"})
    assert not has_price_basis({"finalPrice": "문의"})
    assert not is_positive_number_like(True)
