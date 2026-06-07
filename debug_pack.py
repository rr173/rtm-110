import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.packing.algorithm import Box, pack_boxes


def test_single_box_packing():
    print("=== 测试单箱装箱能力 ===")

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
    print(f"总体积: {len(boxes) * 500*400*300 / 1e9:.3f} m³")
    print(f"20尺箱容积: {5898 * 2352 * 2393 / 1e9:.3f} m³")

    result = pack_boxes(
        container_length=5898.0,
        container_width=2352.0,
        container_height=2393.0,
        container_max_weight=28200.0,
        boxes=boxes
    )

    print(f"\n装箱结果:")
    print(f"  已装入: {len(result['placed_cargos'])} 件")
    print(f"  未装入: {len(result['unplaced_cargos'])} 件")
    print(f"  体积利用率: {result['volume_utilization'] * 100:.1f}%")
    print(f"  总重量: {result['total_weight']:.1f} kg")

    if result['unplaced_cargos']:
        print(f"\n未装入货物示例 (前5个):")
        for uc in result['unplaced_cargos'][:5]:
            print(f"  - {uc['cargo_name']}: {uc['reason']}")

    print(f"\n前5件已装货物位置:")
    for pc in result['placed_cargos'][:5]:
        print(f"  - {pc['cargo_name']}: "
              f"位置({pc['x']:.0f}, {pc['y']:.0f}, {pc['z']:.0f}), "
              f"尺寸{pc['length']:.0f}x{pc['width']:.0f}x{pc['height']:.0f}, "
              f"方向{pc['orientation']}")


if __name__ == "__main__":
    test_single_box_packing()
