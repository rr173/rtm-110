import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.packing.algorithm import Box
from app.packing.split_engine import ContainerSpec, split_cargos_into_boxes


def test_split_basic():
    print("=== 测试1: 基本分箱功能 ===")

    containers = [
        ContainerSpec(
            id=1,
            name="20尺标准箱",
            length=5898.0,
            width=2352.0,
            height=2393.0,
            max_weight=28200.0
        ),
        ContainerSpec(
            id=2,
            name="40尺高箱",
            length=12032.0,
            width=2352.0,
            height=2698.0,
            max_weight=26580.0
        ),
    ]

    boxes = []
    for i in range(50):
        boxes.append(Box(
            cargo_id=i + 1,
            cargo_name=f"货物{i + 1}",
            length=500.0,
            width=400.0,
            height=300.0,
            weight=10.0,
            can_rotate_horizontal=True,
            can_flip=True,
            max_top_load=50.0
        ))

    print(f"货物数量: {len(boxes)}")
    print(f"单个货物体积: {500*400*300 / 1e9:.3f} m³")
    print(f"总体积: {len(boxes) * 500*400*300 / 1e9:.3f} m³")
    print(f"20尺箱容积: {containers[0].volume / 1e9:.3f} m³")
    print(f"40尺箱容积: {containers[1].volume / 1e9:.3f} m³")

    result = split_cargos_into_boxes(boxes, containers)

    print(f"\n分箱结果:")
    print(f"  总箱数: {result['total_boxes']}")
    print(f"  总货物数: {result['total_cargos']}")
    print(f"  已装入货物数: {result['placed_cargos_count']}")
    print(f"  未装入货物数: {len(result['unplaced_cargos'])}")
    print(f"  总重量: {result['total_weight']:.1f} kg")
    print(f"  平均体积利用率: {result['average_volume_utilization'] * 100:.1f}%")
    print(f"  推荐: {result['recommendation']}")

    print(f"\n箱型使用情况:")
    for usage in result['container_usage']:
        print(f"  {usage['container_name']}: {usage['count']} 个")

    print(f"\n各箱详情:")
    for box in result['boxes']:
        print(f"  箱{box['box_index']} ({box['container_name']}): "
              f"装入{box['placed_count']}件, "
              f"利用率{box['volume_utilization'] * 100:.1f}%, "
              f"重量{box['total_weight']:.1f}kg")

    print("\n测试1完成！\n")


def test_split_single_container():
    print("=== 测试2: 单箱型分箱 ===")

    containers = [
        ContainerSpec(
            id=1,
            name="小箱子",
            length=1000.0,
            width=1000.0,
            height=1000.0,
            max_weight=1000.0
        ),
    ]

    boxes = []
    for i in range(20):
        boxes.append(Box(
            cargo_id=i + 1,
            cargo_name=f"小货{i + 1}",
            length=300.0,
            width=300.0,
            height=300.0,
            weight=10.0,
            can_rotate_horizontal=True,
            can_flip=True,
            max_top_load=50.0
        ))

    print(f"货物数量: {len(boxes)}")
    print(f"每个小箱容积: {containers[0].volume / 1e6:.1f} L")

    result = split_cargos_into_boxes(boxes, containers)

    print(f"\n分箱结果:")
    print(f"  总箱数: {result['total_boxes']}")
    print(f"  已装入: {result['placed_cargos_count']} 件")
    print(f"  平均利用率: {result['average_volume_utilization'] * 100:.1f}%")

    print(f"\n各箱详情:")
    for box in result['boxes']:
        print(f"  箱{box['box_index']}: 装入{box['placed_count']}件, "
              f"利用率{box['volume_utilization'] * 100:.1f}%")

    print("\n测试2完成！\n")


def test_split_with_unplaceable():
    print("=== 测试3: 有超大件货物 ===")

    containers = [
        ContainerSpec(
            id=1,
            name="小箱子",
            length=500.0,
            width=500.0,
            height=500.0,
            max_weight=1000.0
        ),
    ]

    boxes = []
    for i in range(5):
        boxes.append(Box(
            cargo_id=i + 1,
            cargo_name=f"正常货物{i + 1}",
            length=200.0,
            width=200.0,
            height=200.0,
            weight=10.0,
            can_rotate_horizontal=True,
            can_flip=True,
            max_top_load=50.0
        ))

    boxes.append(Box(
        cargo_id=100,
        cargo_name="超大货物",
        length=800.0,
        width=800.0,
        height=800.0,
        weight=500.0,
        can_rotate_horizontal=True,
        can_flip=True,
        max_top_load=0.0
    ))

    print(f"货物数量: {len(boxes)}")
    print(f"包含1件超大货物 (800x800x800)，箱子尺寸 500x500x500")

    result = split_cargos_into_boxes(boxes, containers)

    print(f"\n分箱结果:")
    print(f"  总箱数: {result['total_boxes']}")
    print(f"  已装入: {result['placed_cargos_count']} 件")
    print(f"  未装入: {len(result['unplaced_cargos'])} 种")

    if result['unplaced_cargos']:
        for uc in result['unplaced_cargos']:
            print(f"    - {uc['cargo_name']}: {uc['reason']}")

    print("\n测试3完成！\n")


def test_split_empty():
    print("=== 测试4: 空货物 ===")

    containers = [
        ContainerSpec(id=1, name="测试箱", length=1000, width=1000, height=1000, max_weight=1000),
    ]

    result = split_cargos_into_boxes([], containers)
    print(f"空货物分箱结果: 总箱数={result['total_boxes']}, 推荐={result['recommendation']}")

    result = split_cargos_into_boxes([], [])
    print(f"空货物+空箱型: 总箱数={result['total_boxes']}, 推荐={result['recommendation']}")

    print("\n测试4完成！\n")


if __name__ == "__main__":
    test_split_basic()
    test_split_single_container()
    test_split_with_unplaceable()
    test_split_empty()
    print("所有测试完成！")
