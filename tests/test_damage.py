# -*- coding: utf-8 -*-
"""
公式验证单元测试（使用标准库 unittest，无需第三方依赖）。

运行：
    python -m unittest test_damage -v
"""
import unittest

from genshin_dmg import damage


class TestResistance(unittest.TestCase):
    def test_positive_10pct(self):
        # 10% 抗性 -> 1 - 0.10 = 0.9
        self.assertAlmostEqual(damage.resistance_coefficient(0.10), 0.90)

    def test_negative(self):
        # 0 抗性
        self.assertAlmostEqual(damage.resistance_coefficient(0.0), 1.0)
        # -10% 抗性 -> 1 - (-0.10)/2 = 1.05
        self.assertAlmostEqual(damage.resistance_coefficient(-0.10), 1.05)
        # -40% 抗性（敌人被减抗后）-> 1 - (-0.4)/2 = 1.2
        self.assertAlmostEqual(damage.resistance_coefficient(-0.40), 1.20)

    def test_above_75pct(self):
        # 80% 抗性 -> 1/(4*0.8+1) = 1/4.2
        self.assertAlmostEqual(damage.resistance_coefficient(0.80), 1 / 4.2)
        # 边界 75% -> 1 - 0.75 = 0.25
        self.assertAlmostEqual(damage.resistance_coefficient(0.75), 0.25)


class TestDefense(unittest.TestCase):
    def test_equal_level(self):
        # 同等级 90 vs 90：190/380 = 0.5
        self.assertAlmostEqual(damage.defense_coefficient(90, 90), 0.5)

    def test_def_reduction_increases(self):
        # 减防作用在分母的敌人防御项，减防30%应提升伤害：
        # 190/(190+190*0.7) = 190/323
        v = damage.defense_coefficient(90, 90, def_reduction=0.30)
        self.assertAlmostEqual(v, 190 / (190 + 190 * 0.70))

    def test_ignore_increases(self):
        # 无视防御40%
        v = damage.defense_coefficient(90, 90, ignore_def=0.40)
        self.assertAlmostEqual(v, 190 / (190 + 190 * 0.60))

    def test_def_reduction_clamped_90(self):
        # 减防超过90%被截断到90%
        v = damage.defense_coefficient(90, 90, def_reduction=0.95)
        self.assertAlmostEqual(v, 190 / (190 + 190 * 0.10))

    def test_ignore_def_clamped_100(self):
        # 无视防御 100% → 敌人防御项为0 → 系数1
        v = damage.defense_coefficient(90, 90, ignore_def=1.5)
        self.assertAlmostEqual(v, 1.0)

    def test_reduction_and_ignore(self):
        # 减防30% + 无视防御40%（各自相乘作用在敌防御项）
        v = damage.defense_coefficient(90, 90, def_reduction=0.30,
                                       ignore_def=0.40)
        self.assertAlmostEqual(v, 190 / (190 + 190 * 0.7 * 0.6))


class TestAmplify(unittest.TestCase):
    def test_base_factor(self):
        # 无精通、无反应增伤：纯基础系数
        self.assertAlmostEqual(
            damage.amplify_coefficient(2.0, 0.0), 2.0
        )
        self.assertAlmostEqual(
            damage.amplify_coefficient(1.5, 0.0), 1.5
        )

    def test_reaction_name(self):
        self.assertAlmostEqual(
            damage.amplify_for_reaction("蒸发·水→火", 0.0), 2.0
        )
        self.assertAlmostEqual(
            damage.amplify_for_reaction("融化·冰→火", 0.0), 1.5
        )
        self.assertAlmostEqual(damage.amplify_for_reaction(None, 0.0), 1.0)

    def test_mastery_scaling(self):
        # 精通越高系数越大
        low = damage.amplify_coefficient(2.0, 100)
        high = damage.amplify_coefficient(2.0, 800)
        self.assertGreater(high, low)


class TestAggravate(unittest.TestCase):
    def test_aggravate(self):
        # 超激化，90 级，无精通无增益：1202.81 * 1.15
        self.assertAlmostEqual(
            damage.aggravate_value("超激化", 0.0, level=90),
            1202.81 * 1.15,
            places=2,
        )

    def test_mastery_term_is_1200(self):
        """精通项锁定为 5×EM/(EM+1200)（已确认口径，勿改成 +2000）。"""
        for em in (0, 50, 100, 200, 500, 1000, 2000):
            self.assertAlmostEqual(
                damage.aggravate_value("超激化", em, level=90),
                1202.81 * 1.15 * (1 + 5 * em / (em + 1200)),
                places=6,
                msg="EM=%s" % em,
            )

    def test_spread_bigger(self):
        self.assertGreater(
            damage.aggravate_value("蔓激化", 100, level=90),
            damage.aggravate_value("超激化", 100, level=90),
        )

    def test_level_changes_base(self):
        self.assertGreater(
            damage.aggravate_value("超激化", 0.0, level=110),
            damage.aggravate_value("超激化", 0.0, level=90),
        )


class TestTransformative(unittest.TestCase):
    def test_overload_base(self):
        # 超载 90 级无精通：1202.81 * 2.75
        self.assertAlmostEqual(
            damage.transformative_damage("超载", 0.0, level=90),
            1202.81 * 2.75,
            places=2,
        )

    def test_unknown_reaction_raises(self):
        with self.assertRaises(ValueError):
            damage.transformative_damage("不存在", 0.0)

    def test_all_rates_present(self):
        for name in damage.TRANSFORM_RATE:
            v = damage.transformative_damage(name, 0.0, level=90)
            self.assertGreater(v, 0)


class TestNormalDamage(unittest.TestCase):
    def test_simple_direct(self):
        # 攻击力 1000 × 倍率 2.0 = 2000，无任何加成，
        # 10% 抗性，同等级防御(0.5)，不暴击。
        r = damage.normal_damage(
            1000 * 2.0,
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=False,
        )
        # 2000 * 1 * 0.9 * 0.5 * 1 = 900
        self.assertAlmostEqual(r["damage"], 900.0)

    def test_increase_and_crit(self):
        r = damage.normal_damage(
            2000,
            inc_bonus=0.466,      # 46.6% 增伤
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=True,
            crit_damage=1.50,     # 150% 暴伤
        )
        expect = 2000 * (1 + 0.466) * 0.9 * 0.5 * (1 + 1.5)
        self.assertAlmostEqual(r["damage"], expect)

    def test_amplify_layer(self):
        # 蒸发水→火（2.0），精通 0：最终再乘 2.0
        r = damage.normal_damage(
            2000,
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=False,
            amplify_base=damage.AMPLIFY_BASE_FACTOR["蒸发·水→火"],
            elemental_mastery=0.0,
        )
        self.assertAlmostEqual(r["damage"], 2000 * 0.9 * 0.5 * 2.0)

    def test_no_initials_drops_amplify(self):
        # 命中护盾（无数值）：不计算蒸发融化系数
        base = damage.normal_damage(
            2000,
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=False,
            amplify_base=2.0,
            elemental_mastery=0.0,
            has_initials=False,
        )
        self.assertAlmostEqual(base["amp_coeff"], 1.0)

    def test_expected_value(self):
        r = damage.normal_damage(
            2000,
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=True,
            crit_rate=0.5,
            crit_damage=1.0,
        )
        # 期望 = 未暴击 * (1 + 0.5*1) = 未暴击 * 1.5
        noncrit = damage.normal_damage(
            2000,
            resistance=0.10,
            char_level=90,
            enemy_level=90,
            crit=False,
        )["damage"]
        self.assertAlmostEqual(r["expected"], noncrit * 1.5)


class TestCrystallize(unittest.TestCase):
    def test_base(self):
        # 无精通：1851.06
        self.assertAlmostEqual(damage.crystallize_shield(0.0), 1851.06)


class TestEffectiveStat(unittest.TestCase):
    def test_big_and_flat(self):
        # 白值1000，大攻击46.6%，小攻击311：1000*1.466+311
        self.assertAlmostEqual(
            damage.effective_stat(1000, 0.466, 311), 1777.0, places=6
        )

    def test_flat_only(self):
        self.assertAlmostEqual(damage.effective_stat(1000, 0.0, 311), 1311.0)

    def test_zero(self):
        self.assertAlmostEqual(damage.effective_stat(0, 0.5, 100), 100.0)


class TestCritRateCap(unittest.TestCase):
    def test_capped_at_100(self):
        base = dict(
            resistance=0.10, char_level=90, enemy_level=90,
            crit=True, crit_damage=1.5,
        )
        a = damage.normal_damage(2000, crit_rate=1.5, **base)
        b = damage.normal_damage(2000, crit_rate=1.0, **base)
        # 有效暴击率封顶100%，150%与100%期望相同
        self.assertAlmostEqual(a["expected"], b["expected"])
        self.assertAlmostEqual(a["crit_rate_cap"], 1.0)

    def test_below_100_unchanged(self):
        base = dict(resistance=0.10, char_level=90, enemy_level=90,
                    crit=True, crit_damage=1.5)
        r = damage.normal_damage(2000, crit_rate=0.6, **base)
        self.assertAlmostEqual(r["crit_rate_cap"], 0.6)
        self.assertAlmostEqual(
            r["expected"], r["after_def"] * (1 + 0.6 * 1.5))


class TestMonthDirect(unittest.TestCase):
    def test_react(self):
        # 直伤月感电：3×属性×倍率，无EM，抗性10%，暴伤100%(×2)
        v = damage.month_direct("月感电", 1000, 2.0)
        self.assertAlmostEqual(v, 3 * 1000 * 2.0 * 0.9 * 2.0)

    def test_crystal_coeff(self):
        v = damage.month_direct("月结晶", 1000, 2.0, crit=False)
        self.assertAlmostEqual(v, 1.6 * 1000 * 2.0 * 0.9)

    def test_unknown(self):
        with self.assertRaises(ValueError):
            damage.month_direct("不存在", 1, 1)


class TestMonthReaction(unittest.TestCase):
    def test_electro(self):
        # 1446.85×1.8×0.9×2
        v = damage.month_reaction("月感电", level=90)
        self.assertAlmostEqual(v, 1446.85 * 1.8 * 0.9 * 2.0, places=3)

    def test_crystal(self):
        v = damage.month_reaction("月结晶", level=90, crit=False)
        self.assertAlmostEqual(v, 1446.85 * 0.96 * 0.9, places=3)

    def test_level100(self):
        # 100级基准 1674.81
        v = damage.month_reaction("月感电", level=100, crit=False)
        self.assertAlmostEqual(v, 1674.81 * 1.8 * 0.9, places=3)

    def test_bloom_not_reaction(self):
        with self.assertRaises(ValueError):
            damage.month_reaction("月绽放")


class TestDistribute(unittest.TestCase):
    def test_month_weights(self):
        dmg = damage.distribute_damages([2604.33, 2000, 1500, 1000])
        expect = 2604.33 + 0.5 * 2000 + (1 / 12) * 1500 + (1 / 12) * 1000
        self.assertAlmostEqual(dmg, expect, places=3)

    def test_unsorted_auto_sorted(self):
        self.assertAlmostEqual(
            damage.distribute_damages([1000, 2604.33]),
            damage.distribute_damages([2604.33, 1000]),
        )

    def test_fewer_roles(self):
        # 少于4个角色：缺省补0
        dmg = damage.distribute_damages([1000, 800])
        self.assertAlmostEqual(dmg, 1000 + 0.5 * 800)


class TestStar(unittest.TestCase):
    def test_supercond_rate_table(self):
        self.assertAlmostEqual(
            damage.star_superconduct_direct(0, 1000, 2.0, crit=False),
            1.0 * 2000 * 0.9,
        )
        self.assertAlmostEqual(
            damage.star_superconduct_direct(1, 1000, 2.0, crit=False),
            1.45 * 2000 * 0.9,
        )
        self.assertAlmostEqual(
            damage.star_superconduct_direct(12, 1000, 2.0, crit=False),
            2.0 * 2000 * 0.9,
        )

    def test_supercond_uniform_step(self):
        # hit 1 起等步长：每层 +0.05，1.45 → 2.00
        rates = [damage.STAR_SUPERCOND_RATE[i] for i in range(1, 13)]
        steps = [round(b - a, 10) for a, b in zip(rates, rates[1:])]
        self.assertEqual(steps, [0.05] * 11)
        self.assertAlmostEqual(rates[0], 1.45)
        self.assertAlmostEqual(rates[-1], 2.0)

    def test_supercond_clamp(self):
        # 超过12 clamp到12；负数clamp到0
        self.assertAlmostEqual(
            damage.star_superconduct_direct(99, 1000, 2.0, crit=False),
            damage.star_superconduct_direct(12, 1000, 2.0, crit=False),
        )

    def test_swirl_wind(self):
        v = damage.star_swirl_reaction("风", level=90, crit=False)
        self.assertAlmostEqual(v, 1446.85 * 0.75 * 0.9, places=3)

    def test_swirl_ice_by_vortex(self):
        v2 = damage.star_swirl_reaction("冰", vortex_count=2, level=90, crit=False)
        v3 = damage.star_swirl_reaction("冰", vortex_count=3, level=90, crit=False)
        self.assertAlmostEqual(v2, 1446.85 * 2.0 * 0.9, places=3)
        self.assertAlmostEqual(v3, 1446.85 * 3.0 * 0.9, places=3)

    def test_swirl_direct(self):
        v = damage.star_swirl_direct(1000, 2.0, crit=False)
        self.assertAlmostEqual(v, 1.0 * 2000 * 0.9)

    def test_swirl_bad_subtype(self):
        with self.assertRaises(ValueError):
            damage.star_swirl_reaction("火")

    def test_em_increases(self):
        self.assertGreater(
            damage.month_reaction("月感电", elemental_mastery=300, level=90),
            damage.month_reaction("月感电", level=90),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
