"""Synthetic arithmetic checks only; not market evidence or production certification."""
import unittest
from decimal import Decimal
from research_math import (dec, cp_swap_exact_input, cp_immediate_round_trip,
    multiplicative_break_even_return, expectancy_r, capped_spot_long_quantity,
    priority_fee_lamports, raw_to_display, holder_hhi)


class ResearchMathTests(unittest.TestCase):
    def test_large_exit_does_not_equal_marginal_mark(self):
        out = cp_swap_exact_input('1000000','10000','1000000','30')['amount_out']
        self.assertEqual(out.quantize(Decimal('0.01')), Decimal('4992.49'))
        self.assertLess(out, Decimal('10000'))

    def test_zero_fee_roundtrip_restores_initial_quote(self):
        r = cp_immediate_round_trip('10000','1000000','1000','0')
        self.assertLess(abs(r['quote_returned']-Decimal('1000')),Decimal('1e-40'))

    def test_roundtrip_with_fees_loses_quote(self):
        r = cp_immediate_round_trip('10000','1000000','1000','30')
        self.assertGreater(r['quote_loss'],0)
        self.assertLess(r['quote_returned'],r['quote_input'])

    def test_product_increases_when_input_fee_retained(self):
        r = cp_swap_exact_input('100','1000','10','30')
        self.assertGreater(r['reserve_in_after']*r['reserve_out_after'],Decimal('100000'))

    def test_output_increases_but_average_output_rate_declines_with_size(self):
        small=cp_swap_exact_input('100','1000','1','30')['amount_out']
        large=cp_swap_exact_input('100','1000','10','30')['amount_out']
        self.assertGreater(large,small)
        self.assertLess(large/10,small)

    def test_higher_fee_reduces_output(self):
        a=cp_swap_exact_input('100','1000','10','30')['amount_out']
        b=cp_swap_exact_input('100','1000','10','100')['amount_out']
        self.assertLess(b,a)

    def test_zero_input(self):
        self.assertEqual(cp_swap_exact_input('10','20','0','30')['amount_out'],0)

    def test_invalid_pool_inputs(self):
        for args in [('0','1','1','0'),('1','0','1','0'),('1','1','-1','0'),('1','1','1','10000')]:
            with self.subTest(args=args),self.assertRaises(ValueError): cp_swap_exact_input(*args)

    def test_no_float_bool_or_nonfinite_inputs(self):
        for value in [0.1,True,None]:
            with self.subTest(value=value),self.assertRaises(TypeError): dec(value)
        for value in ['NaN','Infinity','-Infinity']:
            with self.subTest(value=value),self.assertRaises(ValueError): dec(value)

    def test_break_even_is_multiplicative(self):
        g=multiplicative_break_even_return('200','200')
        self.assertEqual(g.quantize(Decimal('0.000001')),Decimal('0.041233'))
        self.assertGreater(g,Decimal('0.04'))

    def test_hypothetical_expectancy_after_costs(self):
        self.assertEqual(expectancy_r('0.45','1.8','1','0.30'),Decimal('-0.04'))
        with self.assertRaises(ValueError): expectancy_r('1.1','1','1','0')

    def test_total_loss_cap_dominates_stop_sizing(self):
        r=capped_spot_long_quantity('10000','0.005','0.01','0.008','0','100','50000')
        self.assertEqual(r['planned_loss_cap_quantity'],25000)
        self.assertEqual(r['quantity'],10000)
        self.assertEqual(r['acquisition_notional'],100)

    def test_liquidity_cap_and_step_rounding(self):
        r=capped_spot_long_quantity('10000','0.005','0.01','0.008','0','100','123.9','10')
        self.assertEqual(r['quantity'],120)
        self.assertLessEqual(r['quantity'],r['stressed_exit_cap_quantity'])

    def test_no_exit_capacity_means_zero_quantity(self):
        r=capped_spot_long_quantity('10000','0.005','0.01','0.008','0','100','0')
        self.assertEqual(r['quantity'],0)

    def test_cash_cap_prevents_unlevered_overspend(self):
        r=capped_spot_long_quantity('100','1','1','0.99','0','1000','10000','1','0.1')
        self.assertLessEqual(r['acquisition_notional'],100)
        self.assertEqual(r['quantity'],90)

    def test_invalid_long_stop(self):
        with self.assertRaises(ValueError):
            capped_spot_long_quantity('100','0.01','1','1','0','10','10')

    def test_priority_fee_rounds_up_and_scales(self):
        self.assertEqual(priority_fee_lamports(200000,1001),201)
        self.assertEqual(priority_fee_lamports(1,1),1)
        self.assertEqual(priority_fee_lamports(200000,0),0)
        with self.assertRaises(ValueError): priority_fee_lamports(True,1)

    def test_raw_units_are_exact_for_large_values(self):
        self.assertEqual(raw_to_display('1000001',6),Decimal('1.000001'))
        self.assertEqual(raw_to_display('123456789012345678901234567890123456789',18),
                         Decimal('123456789012345678901.234567890123456789'))
        for raw in ['1.2','1e6','-1','１２']:
            with self.subTest(raw=raw),self.assertRaises(ValueError): raw_to_display(raw,6)

    def test_hhi_concentration(self):
        self.assertEqual(holder_hhi(['1']),1)
        self.assertEqual(holder_hhi(['0.5','0.5']),Decimal('0.50'))
        with self.assertRaises(ValueError): holder_hhi(['0.4','0.4'])


if __name__ == '__main__':
    unittest.main()
