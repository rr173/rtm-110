"""
专项测试：费用分摊尾差对齐验证
验证在各种比例下，货物分摊总额与箱费用总额精确到分完全一致。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.cost_allocation_engine import _allocate_with_rounding_adjustment, _round2


def test_exact_alignment_simple_ratio():
    """测试简单比例：12:1:1:1 的情况（用户反馈的场景）"""
    print("\n" + "=" * 70)
    print("TEST 1: 12:1:1:1 比例分摊 (用户反馈的场景)")
    print("=" * 70)

    total_amount = 1000.00
    items = [
        {"name": "大件A", "volume_cbm": 12.0},
        {"name": "小件B", "volume_cbm": 1.0},
        {"name": "小件C", "volume_cbm": 1.0},
        {"name": "小件D", "volume_cbm": 1.0},
    ]

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    sum_alloc = _round2(sum(it["allocated"] for it in items))
    diff = _round2(abs(sum_alloc - total_amount))

    print(f"  待分摊总额: {total_amount:.2f}")
    print(f"  比例: 12 : 1 : 1 : 1")
    for it in items:
        ratio = it["volume_cbm"] / 15.0 * 100
        precise = total_amount * ratio / 100
        print(f"    {it['name']:8s}: 体积占比 {ratio:5.1f}%  精确值 {precise:7.2f}  "
              f"分摊值 {it['allocated']:7.2f}")

    print(f"  ───────────────────────────")
    print(f"  分摊总额: {sum_alloc:.2f}")
    print(f"  原始总额: {total_amount:.2f}")
    print(f"  差额: {diff:.2f}")

    assert diff == 0.0, f"尾差对齐失败: 差额 {diff} 元"
    print(f"  ✅ 分摊总额与原始总额精确一致")


def test_exact_alignment_many_small_items():
    """测试大量小件分摊：100件各占1%"""
    print("\n" + "=" * 70)
    print("TEST 2: 100件货物平均分摊 (大量小件场景)")
    print("=" * 70)

    total_amount = 999.99
    items = [{"name": f"货{i:03d}", "volume_cbm": 1.0} for i in range(100)]

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    sum_alloc = _round2(sum(it["allocated"] for it in items))
    diff = _round2(abs(sum_alloc - total_amount))

    print(f"  待分摊总额: {total_amount:.2f}")
    print(f"  货物数量: 100件, 平均体积占比 1%")
    print(f"  精确单件分摊: {total_amount / 100:.4f}")
    print(f"  分摊值范围: {min(it['allocated'] for it in items):.2f} ~ {max(it['allocated'] for it in items):.2f}")
    print(f"  分摊总额: {sum_alloc:.2f}")
    print(f"  原始总额: {total_amount:.2f}")
    print(f"  差额: {diff:.6f}")

    assert diff == 0.0, f"尾差对齐失败: 差额 {diff} 元"
    print(f"  ✅ 分摊总额与原始总额精确一致")


def test_exact_alignment_odd_total():
    """测试除不尽的总额：100元分给3件"""
    print("\n" + "=" * 70)
    print("TEST 3: 100元分给3件 (经典除不尽场景)")
    print("=" * 70)

    total_amount = 100.00
    items = [
        {"name": "货A", "volume_cbm": 1.0},
        {"name": "货B", "volume_cbm": 1.0},
        {"name": "货C", "volume_cbm": 1.0},
    ]

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    sum_alloc = _round2(sum(it["allocated"] for it in items))
    diff = _round2(abs(sum_alloc - total_amount))

    print(f"  待分摊总额: {total_amount:.2f}")
    print(f"  比例: 1:1:1")
    for it in items:
        print(f"    {it['name']}: {it['allocated']:.2f}")
    print(f"  ─────────")
    print(f"  分摊总额: {sum_alloc:.2f}")
    print(f"  差额: {diff:.2f}")

    assert diff == 0.0, f"尾差对齐失败: 差额 {diff} 元"
    print(f"  ✅ 分摊总额与原始总额精确一致")
    print(f"  💡 尾差由排在最前/体积最大的货物承担，合理")


def test_exact_alignment_unbalanced():
    """测试极端不平衡比例：99.9% vs 0.1%"""
    print("\n" + "=" * 70)
    print("TEST 4: 极端比例 99.9% vs 0.1%")
    print("=" * 70)

    total_amount = 1234.56
    items = [
        {"name": "巨无霸", "volume_cbm": 999.0},
        {"name": "小不点", "volume_cbm": 1.0},
    ]

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    sum_alloc = _round2(sum(it["allocated"] for it in items))
    diff = _round2(abs(sum_alloc - total_amount))

    print(f"  待分摊总额: {total_amount:.2f}")
    for it in items:
        ratio = it["volume_cbm"] / 1000.0 * 100
        print(f"    {it['name']:8s}: 占比 {ratio:5.2f}%  分摊 {it['allocated']:.2f}")
    print(f"  ───────────────────────")
    print(f"  分摊总额: {sum_alloc:.2f}")
    print(f"  差额: {diff:.2f}")

    assert diff == 0.0, f"尾差对齐失败: 差额 {diff} 元"
    print(f"  ✅ 分摊总额与原始总额精确一致")


def test_exact_alignment_zero():
    """测试零总额分摊"""
    print("\n" + "=" * 70)
    print("TEST 5: 零总额分摊 (边缘情况)")
    print("=" * 70)

    total_amount = 0.0
    items = [
        {"name": "货A", "volume_cbm": 1.0},
        {"name": "货B", "volume_cbm": 2.0},
    ]

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    sum_alloc = _round2(sum(it["allocated"] for it in items))

    print(f"  待分摊总额: {total_amount:.2f}")
    for it in items:
        print(f"    {it['name']}: {it['allocated']:.2f}")
    print(f"  分摊总额: {sum_alloc:.2f}")

    assert sum_alloc == 0.0, "零总额分摊结果应该都是0"
    print(f"  ✅ 零总额分摊正确")


def test_exact_alignment_empty():
    """测试空列表分摊"""
    print("\n" + "=" * 70)
    print("TEST 6: 空列表分摊 (边缘情况)")
    print("=" * 70)

    total_amount = 100.0
    items = []

    _allocate_with_rounding_adjustment(total_amount, items, "volume_cbm", "allocated")

    assert len(items) == 0
    print(f"  空列表输入, 不报错 ✅")


def test_multiple_cost_components():
    """测试多项费用独立分摊后，总计也对齐"""
    print("\n" + "=" * 70)
    print("TEST 7: 多项费用独立分摊后汇总对齐 (模拟真实场景)")
    print("=" * 70)

    items = [
        {"name": "货A", "volume_cbm": 12.0},
        {"name": "货B", "volume_cbm": 1.0},
        {"name": "货C", "volume_cbm": 1.0},
        {"name": "货D", "volume_cbm": 1.0},
    ]

    base_freight = 1000.00
    overweight = 123.45
    reefer = 200.00
    hazard = 300.00
    total = _round2(base_freight + overweight + reefer + hazard)

    print(f"  箱费用明细:")
    print(f"    基础运费:   {base_freight:.2f}")
    print(f"    超重附加费: {overweight:.2f}")
    print(f"    冷藏附加费: {reefer:.2f}")
    print(f"    危险品附加: {hazard:.2f}")
    print(f"    ──────────────────")
    print(f"    箱总费用:   {total:.2f}")

    _allocate_with_rounding_adjustment(base_freight, items, "volume_cbm", "alloc_base")
    _allocate_with_rounding_adjustment(overweight, items, "volume_cbm", "alloc_overweight")

    reefer_items = items[:1]
    _allocate_with_rounding_adjustment(reefer, reefer_items, "volume_cbm", "alloc_reefer")
    for it in items[1:]:
        it["alloc_reefer"] = 0.0

    hazard_items = items[2:3]
    _allocate_with_rounding_adjustment(hazard, hazard_items, "volume_cbm", "alloc_hazard")
    for i, it in enumerate(items):
        if i != 2:
            it["alloc_hazard"] = 0.0

    print(f"\n  各货物分摊明细:")
    sum_base = sum_overweight = sum_reefer = sum_hazard = sum_total = 0.0
    for it in items:
        t = _round2(it["alloc_base"] + it["alloc_overweight"] + it["alloc_reefer"] + it["alloc_hazard"])
        it["total"] = t
        sum_base = _round2(sum_base + it["alloc_base"])
        sum_overweight = _round2(sum_overweight + it["alloc_overweight"])
        sum_reefer = _round2(sum_reefer + it["alloc_reefer"])
        sum_hazard = _round2(sum_hazard + it["alloc_hazard"])
        sum_total = _round2(sum_total + t)
        print(f"    {it['name']}: 基础{it['alloc_base']:7.2f} 超重{it['alloc_overweight']:6.2f} "
              f"冷藏{it['alloc_reefer']:6.2f} 危险品{it['alloc_hazard']:6.2f} → 合计 {t:7.2f}")

    print(f"  ───────────────────────────────────────────────────────────")
    print(f"  分摊合计: 基础{sum_base:7.2f} 超重{sum_overweight:6.2f} "
          f"冷藏{sum_reefer:6.2f} 危险品{sum_hazard:6.2f} → 合计 {sum_total:7.2f}")
    print(f"  箱费用:   基础{base_freight:7.2f} 超重{overweight:6.2f} "
          f"冷藏{reefer:6.2f} 危险品{hazard:6.2f} → 合计 {total:7.2f}")

    diff_base = _round2(abs(sum_base - base_freight))
    diff_ov = _round2(abs(sum_overweight - overweight))
    diff_rf = _round2(abs(sum_reefer - reefer))
    diff_hz = _round2(abs(sum_hazard - hazard))
    diff_total = _round2(abs(sum_total - total))

    print(f"\n  差额校验:")
    print(f"    基础运费差额:   {diff_base:.2f} {'✅' if diff_base == 0 else '❌'}")
    print(f"    超重附加费差额: {diff_ov:.2f} {'✅' if diff_ov == 0 else '❌'}")
    print(f"    冷藏附加费差额: {diff_rf:.2f} {'✅' if diff_rf == 0 else '❌'}")
    print(f"    危险品附加差额: {diff_hz:.2f} {'✅' if diff_hz == 0 else '❌'}")
    print(f"    总费用差额:     {diff_total:.2f} {'✅' if diff_total == 0 else '❌'}")

    assert diff_base == 0.0
    assert diff_ov == 0.0
    assert diff_rf == 0.0
    assert diff_hz == 0.0
    assert diff_total == 0.0
    print(f"  ✅ 所有费用项分摊总额与箱费用总额完全一致")


if __name__ == "__main__":
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + "           费用分摊尾差对齐 - 专项测试套件" + " " * 28 + "║")
    print("╚" + "═" * 68 + "╝")

    tests = [
        ("12:1:1:1比例", test_exact_alignment_simple_ratio),
        ("100件平均分摊", test_exact_alignment_many_small_items),
        ("100元分3件", test_exact_alignment_odd_total),
        ("极端比例99.9%", test_exact_alignment_unbalanced),
        ("零总额分摊", test_exact_alignment_zero),
        ("空列表分摊", test_exact_alignment_empty),
        ("多费用项汇总对齐", test_multiple_cost_components),
    ]

    passed = 0
    failed = 0
    failed_tests = []

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            failed_tests.append((name, str(e)))
            import traceback
            traceback.print_exc()

    print("\n\n" + "=" * 70)
    print("📋 测试汇总报告")
    print("=" * 70)
    print(f"  总计: {passed + failed} 项 | ✅ 通过: {passed} | ❌ 失败: {failed}")
    if failed_tests:
        print(f"\n  ❌ 失败测试详情:")
        for name, err in failed_tests:
            print(f"    - {name}: {err}")
    print("=" * 70)

    if failed > 0:
        print("\n❌ 尾差对齐测试未全部通过!")
        exit(1)
    else:
        print("\n🎉 所有尾差对齐测试通过!分摊总额与箱费用精确到分完全一致。")
        exit(0)
