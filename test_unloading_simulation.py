import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.unloading_simulation_engine import (
    run_unloading_simulation,
    CargoState,
    _boxes_overlap_xy,
    _is_blocking,
    _find_blocking_cargos,
    _check_deadlock,
    _identify_poorly_stacked_cargos
)


def test_boxes_overlap_xy():
    a = CargoState(
        packed_cargo_id=1, cargo_id=1, cargo_name="A",
        x=0, y=0, z=0, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=1
    )
    b = CargoState(
        packed_cargo_id=2, cargo_id=2, cargo_name="B",
        x=50, y=50, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )
    c = CargoState(
        packed_cargo_id=3, cargo_id=3, cargo_name="C",
        x=200, y=200, z=0, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=2
    )

    assert _boxes_overlap_xy(a, b) == True
    assert _boxes_overlap_xy(a, c) == False
    assert _boxes_overlap_xy(b, c) == False
    print("✓ test_boxes_overlap_xy passed")


def test_is_blocking():
    target = CargoState(
        packed_cargo_id=1, cargo_id=1, cargo_name="Target",
        x=0, y=0, z=0, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=1
    )

    later_overlapping = CargoState(
        packed_cargo_id=2, cargo_id=2, cargo_name="Blocker",
        x=50, y=50, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )

    earlier_overlapping = CargoState(
        packed_cargo_id=3, cargo_id=3, cargo_name="Earlier",
        x=50, y=50, z=100, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=2
    )

    non_overlapping = CargoState(
        packed_cargo_id=4, cargo_id=4, cargo_name="Far",
        x=200, y=200, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )

    assert _is_blocking(later_overlapping, target) == True
    assert _is_blocking(earlier_overlapping, target) == False
    assert _is_blocking(non_overlapping, target) == False
    assert _is_blocking(target, later_overlapping) == False
    print("✓ test_is_blocking passed")


def test_find_blocking_cargos():
    target = CargoState(
        packed_cargo_id=1, cargo_id=1, cargo_name="Target",
        x=0, y=0, z=0, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=1
    )

    blocker1 = CargoState(
        packed_cargo_id=2, cargo_id=2, cargo_name="Blocker1",
        x=50, y=50, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )

    blocker2 = CargoState(
        packed_cargo_id=3, cargo_id=3, cargo_name="Blocker2",
        x=25, y=25, z=200, length=100, width=100, height=100, weight=10,
        stop_order=3, unload_order=1
    )

    all_cargos = [target, blocker1, blocker2]
    blockers = _find_blocking_cargos(target, all_cargos)

    assert len(blockers) == 2
    assert blocker1 in blockers
    assert blocker2 in blockers
    print("✓ test_find_blocking_cargos passed")


def test_identify_poorly_stacked_cargos():
    earlier = CargoState(
        packed_cargo_id=1, cargo_id=1, cargo_name="Earlier",
        x=0, y=0, z=0, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=1
    )

    later_on_top = CargoState(
        packed_cargo_id=2, cargo_id=2, cargo_name="LaterOnTop",
        x=50, y=50, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )

    later_aside = CargoState(
        packed_cargo_id=3, cargo_id=3, cargo_name="LaterAside",
        x=200, y=200, z=100, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=2
    )

    all_cargos = [earlier, later_on_top, later_aside]
    poorly_stacked = _identify_poorly_stacked_cargos(all_cargos)

    assert len(poorly_stacked) == 1
    assert 2 in poorly_stacked
    assert 3 not in poorly_stacked
    print("✓ test_identify_poorly_stacked_cargos passed")


def test_check_deadlock():
    current_stop = 1

    missed_unload_on_top = CargoState(
        packed_cargo_id=1, cargo_id=1, cargo_name="MissedUnload",
        x=0, y=0, z=100, length=100, width=100, height=100, weight=10,
        stop_order=1, unload_order=1,
        is_removed=False
    )

    future_accessible = CargoState(
        packed_cargo_id=2, cargo_id=2, cargo_name="FutureOK",
        x=200, y=200, z=0, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=1
    )

    future_blocked_by_missed = CargoState(
        packed_cargo_id=3, cargo_id=3, cargo_name="FutureBlocked",
        x=0, y=0, z=0, length=100, width=100, height=100, weight=10,
        stop_order=2, unload_order=2
    )

    remaining = [missed_unload_on_top, future_accessible, future_blocked_by_missed]

    has_deadlock, deadlock_ids = _check_deadlock(remaining, current_stop)

    assert has_deadlock == True
    assert 3 in deadlock_ids
    print("✓ test_check_deadlock passed")


def test_full_simulation():
    packed_cargos = [
        {"id": 1, "cargo_id": 101, "cargo_name": "货A-站1",
         "x": 0, "y": 0, "z": 0, "length": 1000, "width": 1000, "height": 1000, "weight": 100},
        {"id": 2, "cargo_id": 102, "cargo_name": "货B-站2",
         "x": 0, "y": 0, "z": 1000, "length": 1000, "width": 1000, "height": 1000, "weight": 100},
        {"id": 3, "cargo_id": 103, "cargo_name": "货C-站3",
         "x": 1000, "y": 0, "z": 0, "length": 1000, "width": 1000, "height": 1000, "weight": 100},
        {"id": 4, "cargo_id": 104, "cargo_name": "货D-站1",
         "x": 1000, "y": 1000, "z": 0, "length": 1000, "width": 1000, "height": 1000, "weight": 100},
    ]

    stops = [
        {"id": 1, "stop_order": 1, "stop_name": "站点1"},
        {"id": 2, "stop_order": 2, "stop_name": "站点2"},
        {"id": 3, "stop_order": 3, "stop_name": "站点3"},
    ]

    cargo_assignments = [
        {"packed_cargo_id": 1, "stop_order": 1, "unload_order": 1},
        {"packed_cargo_id": 2, "stop_order": 2, "unload_order": 1},
        {"packed_cargo_id": 3, "stop_order": 3, "unload_order": 1},
        {"packed_cargo_id": 4, "stop_order": 1, "unload_order": 2},
    ]

    result = run_unloading_simulation(packed_cargos, stops, cargo_assignments)

    assert result.total_cargos == 4
    assert result.total_stops == 3
    assert result.total_rehandle_count >= 2

    stop1 = result.stop_results[0]
    assert stop1.stop_order == 1
    assert stop1.unload_count == 2
    assert stop1.rehandle_count >= 2

    has_rehandle_out = any(m.move_type == "rehandle_out" for m in stop1.moves)
    has_rehandle_in = any(m.move_type == "rehandle_in" for m in stop1.moves)
    assert has_rehandle_out == True
    assert has_rehandle_in == True

    assert len(result.poorly_stacked_cargo_ids) >= 1

    print("✓ test_full_simulation passed")
    print(f"  总返搬次数: {result.total_rehandle_count}")
    print(f"  最糟糕站点: 第{result.worst_stop_order}站, 返搬{result.worst_stop_rehandle_count}次")
    print(f"  死局: {'是' if result.has_deadlock else '否'}")
    print(f"  不合理堆叠货物: {result.poorly_stacked_cargo_ids}")


def test_deadlock_scenario():
    packed_cargos = [
        {"id": 1, "cargo_id": 101, "cargo_name": "货A-站1",
         "x": 0, "y": 0, "z": 0, "length": 1000, "width": 1000, "height": 400, "weight": 100},
        {"id": 2, "cargo_id": 102, "cargo_name": "货B-站2",
         "x": 0, "y": 0, "z": 400, "length": 1000, "width": 1000, "height": 400, "weight": 100},
        {"id": 3, "cargo_id": 103, "cargo_name": "货C-站3",
         "x": 0, "y": 0, "z": 800, "length": 1000, "width": 1000, "height": 400, "weight": 100},
        {"id": 4, "cargo_id": 104, "cargo_name": "货D-站4",
         "x": 0, "y": 0, "z": 1200, "length": 1000, "width": 1000, "height": 400, "weight": 100},
    ]

    stops = [
        {"id": 1, "stop_order": 1, "stop_name": "站点1"},
        {"id": 2, "stop_order": 2, "stop_name": "站点2"},
        {"id": 3, "stop_order": 3, "stop_name": "站点3"},
        {"id": 4, "stop_order": 4, "stop_name": "站点4"},
    ]

    cargo_assignments = [
        {"packed_cargo_id": 1, "stop_order": 1, "unload_order": 1},
        {"packed_cargo_id": 2, "stop_order": 2, "unload_order": 1},
        {"packed_cargo_id": 3, "stop_order": 3, "unload_order": 1},
        {"packed_cargo_id": 4, "stop_order": 4, "unload_order": 1},
    ]

    result = run_unloading_simulation(packed_cargos, stops, cargo_assignments)

    assert result.has_deadlock == True
    assert result.deadlock_stop_order == 1

    print("✓ test_deadlock_scenario passed")
    print(f"  死局发生在第{result.deadlock_stop_order}站")
    print(f"  死局货物ID: {result.deadlock_cargo_ids}")
    print(f"  总返搬次数: {result.total_rehandle_count}")


def run_all_tests():
    print("=" * 60)
    print("多站点卸货推演模块 - 单元测试")
    print("=" * 60)
    print()

    try:
        test_boxes_overlap_xy()
        test_is_blocking()
        test_find_blocking_cargos()
        test_identify_poorly_stacked_cargos()
        test_check_deadlock()
        test_full_simulation()
        test_deadlock_scenario()

        print()
        print("=" * 60)
        print("✅ 所有测试通过!")
        print("=" * 60)
        return True
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
