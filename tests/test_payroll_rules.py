"""Tests for payroll calculation rules."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.payroll.rules import (
    server_val, foh_split, t30, kitchen_pool, sushi_pool,
    server_net_tip, distribute_by_hours, distribute_weighted,
    base_pay, overtime_pay, total_pay, parse_dollar, parse_hours,
)


class TestServerVal:
    def test_basic(self):
        assert server_val(1000.0) == 60.0

    def test_zero_sub(self):
        assert server_val(0.0) == 0.0

    def test_custom_rate(self):
        assert server_val(1000.0, rate=0.05) == 50.0

    def test_rounding(self):
        # 390.33 * 0.06 = 23.4198 → rounds to 23.42
        assert server_val(390.33) == 23.42


class TestFohSplit:
    def test_split_ratio(self):
        cashier, pool = foh_split(300.0)
        assert cashier == 200.0
        assert pool == 100.0

    def test_zero(self):
        cashier, pool = foh_split(0.0)
        assert cashier == 0.0
        assert pool == 0.0

    def test_sum_equals_total(self):
        tip = 123.45
        cashier, pool = foh_split(tip)
        assert abs(cashier + pool - tip) < 0.02  # allow 1-cent rounding


class TestT30:
    def test_basic(self):
        # 606.01 * 2/3 = 404.00667 ≈ 404.01; cashier_paid=0 → T30=404.01
        result = t30(606.01, 0.0)
        assert result == 404.01

    def test_with_cashier(self):
        result = t30(300.0, 50.0)
        assert result == 150.0   # 300 * 2/3 = 200 - 50

    def test_negative_allowed(self):
        # If cashier_paid > FOH×2/3, T30 can be negative
        result = t30(60.0, 100.0)
        assert result == -60.0


class TestKitchenPool:
    def test_m22_zero(self):
        # When M22=0, E89 = T30 only
        assert kitchen_pool(2612.44, 404.01, m22=0.0) == 404.01

    def test_m22_nonzero(self):
        result = kitchen_pool(1000.0, 100.0, m22=0.5)
        assert result == 600.0   # 1000*0.5 + 100

    def test_zero_inputs(self):
        assert kitchen_pool(0.0, 0.0) == 0.0


class TestSushiPool:
    def test_all_zero(self):
        assert sushi_pool(0.0, 0.0, 0.0, 0.0) == 0.0

    def test_direct_only(self):
        assert sushi_pool(1000.0, 0.0, 0.0, 50.0) == 50.0

    def test_full_formula(self):
        result = sushi_pool(1000.0, 0.1, 20.0, 30.0)
        assert result == 150.0   # 1000*0.1 + 20 + 30


class TestServerNetTip:
    def test_basic(self):
        assert server_net_tip(100.0, 0.0, 60.0) == 40.0

    def test_with_gratuity(self):
        assert server_net_tip(100.0, 20.0, 60.0) == 60.0

    def test_zero_val(self):
        assert server_net_tip(100.0, 50.0, 0.0) == 150.0


class TestDistributeByHours:
    def test_equal_hours(self):
        result = distribute_by_hours(100.0, {"A": 10.0, "B": 10.0})
        assert result["A"] == 50.0
        assert result["B"] == 50.0

    def test_unequal_hours(self):
        result = distribute_by_hours(90.0, {"A": 30.0, "B": 60.0})
        assert result["A"] == 30.0
        assert result["B"] == 60.0

    def test_empty_hours(self):
        result = distribute_by_hours(100.0, {})
        assert result == {}

    def test_zero_pool(self):
        result = distribute_by_hours(0.0, {"A": 10.0})
        assert result["A"] == 0.0


class TestDistributeWeighted:
    def test_equal_weights(self):
        result = distribute_weighted(100.0, {"A": 15.0, "B": 15.0})
        assert result["A"] == 50.0
        assert result["B"] == 50.0

    def test_different_multipliers(self):
        # A: 10h × 1.5 = 15; B: 10h × 1.0 = 10 → total = 25
        weights = {"A": 15.0, "B": 10.0}
        result = distribute_weighted(50.0, weights)
        assert result["A"] == 30.0   # 15/25 * 50
        assert result["B"] == 20.0   # 10/25 * 50


class TestPayComponents:
    def test_base_pay(self):
        assert base_pay(40.0, 15.0) == 600.0

    def test_overtime_pay(self):
        assert overtime_pay(5.0, 15.0) == 112.50

    def test_total_pay_with_tips(self):
        result = total_pay(base=600.0, ot=112.5, tip=200.0, kitchen=50.0)
        assert result == 962.5

    def test_deduction_reduces_total(self):
        result = total_pay(base=600.0, deduction=50.0)
        assert result == 550.0


class TestParseDollar:
    def test_dollar_sign(self):
        assert parse_dollar("$1,234.56") == 1234.56

    def test_plain_number(self):
        assert parse_dollar("123.45") == 123.45

    def test_empty(self):
        assert parse_dollar("") == 0.0

    def test_dash(self):
        assert parse_dollar("-") == 0.0

    def test_em_dash(self):
        assert parse_dollar("—") == 0.0

    def test_negative(self):
        assert parse_dollar("-50.00") == -50.0

    def test_comma_only(self):
        assert parse_dollar("1,000") == 1000.0


class TestParseHours:
    def test_float_string(self):
        assert parse_hours("40.50") == 40.5

    def test_int_string(self):
        assert parse_hours("40") == 40.0

    def test_empty(self):
        assert parse_hours("") == 0.0

    def test_invalid(self):
        assert parse_hours("N/A") == 0.0
