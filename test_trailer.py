from app.packing.trailer_cog_engine import (
    TrailerSpec, BoxSpec, PlacedBox,
    optimize_box_positions, generate_unload_sequence,
    calculate_axle_loads, check_left_right_balance
)


def print_separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def demo_scenario_1():
    print_separator("场景一：标准平板拖车 - 五箱混装")

    trailer = TrailerSpec(
        total_length=9000.0,
        platform_length=6096.0,
        platform_width=2440.0,
        front_axle_position=1500.0,
        rear_axle_position=7500.0,
        front_axle_max_load=8000.0,
        rear_axle_max_load=12000.0,
        total_max_weight=18000.0
    )

    boxes = [
        BoxSpec(box_id=1, box_name="设备箱A", length=2400, width=1200, weight=3500, cog_offset_x=0),
        BoxSpec(box_id=2, box_name="设备箱B", length=2000, width=1200, weight=2800, cog_offset_x=100),
        BoxSpec(box_id=3, box_name="物料箱C", length=1800, width=1000, weight=1500, cog_offset_x=-50),
        BoxSpec(box_id=4, box_name="配件箱D", length=1500, width=1000, weight=1200, cog_offset_x=0),
        BoxSpec(box_id=5, box_name="重型箱E", length=2200, width=1200, weight=4200, cog_offset_x=150),
    ]

    print(f"拖车参数:")
    print(f"  平板长度: {trailer.platform_length} mm")
    print(f"  平板宽度: {trailer.platform_width} mm")
    print(f"  前轴位置: {trailer.front_axle_position} mm (距前端)")
    print(f"  后轴位置: {trailer.rear_axle_position} mm (距前端)")
    print(f"  轴距: {trailer.wheelbase} mm")
    print(f"  前轴限重: {trailer.front_axle_max_load} kg")
    print(f"  后轴限重: {trailer.rear_axle_max_load} kg")
    print(f"  总限重: {trailer.total_max_weight} kg")

    print(f"\n待装货物 ({len(boxes)} 箱):")
    total_weight = sum(b.weight for b in boxes)
    for b in boxes:
        print(f"  {b.box_name}: {b.length}x{b.width} mm, 重量 {b.weight} kg")
    print(f"  总重量: {total_weight} kg")

    result = optimize_box_positions(trailer, boxes)

    print(f"\n优化结果:")
    print(f"  总箱数: {result['total_boxes']}")
    print(f"  总重量: {result['total_weight']:.1f} kg")
    print(f"  前轴荷: {result['front_axle_load']:.1f} kg ({result['front_axle_load_ratio']*100:.1f}%)")
    print(f"  后轴荷: {result['rear_axle_load']:.1f} kg ({result['rear_axle_load_ratio']*100:.1f}%)")
    print(f"  轴荷是否超限: {'否' if result['axles_within_limit'] else '是'}")
    print(f"  左右偏差: {result['left_right_balance_ratio']*100:.1f}%")
    print(f"  左右是否超限: {'否' if result['left_right_within_limit'] else '是'}")
    print(f"  左侧重量: {result['left_weight']:.1f} kg")
    print(f"  右侧重量: {result['right_weight']:.1f} kg")
    print(f"  综合评分: {result['score']:.4f}")
    print(f"  建议: {result['recommendation']}")

    print(f"\n各箱位置:")
    for i, box in enumerate(result['loaded_boxes']):
        print(f"  [{i+1}] {box['box_name']}:")
        print(f"      位置: x={box['x']:.0f}mm, y={box['y']:.0f}mm")
        print(f"      尺寸: {box['length']}x{box['width']} mm")
        print(f"      重量: {box['weight']} kg")

    placed_boxes = []
    for lb in result["loaded_boxes"]:
        placed_boxes.append(PlacedBox(
            box_id=lb["box_id"],
            box_name=lb["box_name"],
            x=lb["x"],
            y=lb["y"],
            length=lb["length"],
            width=lb["width"],
            weight=lb["weight"],
            cog_offset_x=lb["cog_offset_x"]
        ))

    unload_result = generate_unload_sequence(trailer, placed_boxes, max_lr_ratio=0.15)

    print(f"\n卸载顺序仿真:")
    print(f"  总步数: {unload_result['total_steps']}")
    print(f"  全部步骤合法: {'是' if unload_result['all_steps_valid'] else '否'}")
    print(f"  不合法步数: {unload_result['invalid_steps_count']}")

    print(f"\n卸载步骤详情:")
    for step in unload_result['sequence']:
        status = "✓" if step['axles_within_limit_before'] and step['left_right_within_limit_before'] else "✗"
        print(f"  [{status}] 步骤 {step['step_number']}: 卸载 {step['box_name']}")
        print(f"       卸前: 前轴 {step['front_axle_load_before']:.1f}kg, 后轴 {step['rear_axle_load_before']:.1f}kg")
        print(f"       卸后: 前轴 {step['front_axle_load_after']:.1f}kg, 后轴 {step['rear_axle_load_after']:.1f}kg")
        print(f"       左右偏差: {step['left_right_ratio_before']*100:.1f}% {'(合法)' if step['left_right_within_limit_before'] else '(超限)'}")


def demo_scenario_2():
    print_separator("场景二：重型平板拖车 - 双大箱重载")

    trailer = TrailerSpec(
        total_length=14000.0,
        platform_length=12192.0,
        platform_width=2440.0,
        front_axle_position=2000.0,
        rear_axle_position=12000.0,
        front_axle_max_load=10000.0,
        rear_axle_max_load=20000.0,
        total_max_weight=28000.0
    )

    boxes = [
        BoxSpec(box_id=10, box_name="大型集装箱1", length=6000, width=2400, weight=8000, cog_offset_x=200),
        BoxSpec(box_id=11, box_name="大型集装箱2", length=5500, width=2400, weight=7500, cog_offset_x=-100),
    ]

    print(f"拖车参数:")
    print(f"  平板长度: {trailer.platform_length} mm")
    print(f"  前轴限重: {trailer.front_axle_max_load} kg")
    print(f"  后轴限重: {trailer.rear_axle_max_load} kg")

    result = optimize_box_positions(trailer, boxes)

    print(f"\n优化结果:")
    print(f"  总重量: {result['total_weight']:.1f} kg")
    print(f"  前轴荷: {result['front_axle_load']:.1f} kg ({result['front_axle_load_ratio']*100:.1f}%)")
    print(f"  后轴荷: {result['rear_axle_load']:.1f} kg ({result['rear_axle_load_ratio']*100:.1f}%)")
    print(f"  轴荷是否超限: {'否' if result['axles_within_limit'] else '是'}")
    print(f"  建议: {result['recommendation']}")

    print(f"\n各箱位置:")
    for i, box in enumerate(result['loaded_boxes']):
        print(f"  [{i+1}] {box['box_name']}: x={box['x']:.0f}mm, 重量 {box['weight']}kg")


def demo_scenario_3():
    print_separator("场景三：短途配送拖车 - 八箱轻载")

    trailer = TrailerSpec(
        total_length=7000.0,
        platform_length=5000.0,
        platform_width=2200.0,
        front_axle_position=1200.0,
        rear_axle_position=5800.0,
        front_axle_max_load=5000.0,
        rear_axle_max_load=8000.0,
        total_max_weight=12000.0
    )

    boxes = [
        BoxSpec(box_id=20, box_name="快递箱1", length=1200, width=800, weight=500, cog_offset_x=0),
        BoxSpec(box_id=21, box_name="快递箱2", length=1000, width=800, weight=600, cog_offset_x=0),
        BoxSpec(box_id=22, box_name="生鲜箱", length=1500, width=1000, weight=800, cog_offset_x=50),
        BoxSpec(box_id=23, box_name="易碎品箱", length=1100, width=900, weight=400, cog_offset_x=0),
        BoxSpec(box_id=24, box_name="日用品箱", length=1300, width=1000, weight=700, cog_offset_x=-30),
        BoxSpec(box_id=25, box_name="家电箱", length=1800, width=1000, weight=900, cog_offset_x=80),
        BoxSpec(box_id=26, box_name="服装箱", length=1400, width=900, weight=350, cog_offset_x=0),
        BoxSpec(box_id=27, box_name="食品箱", length=1600, width=1100, weight=650, cog_offset_x=20),
    ]

    result = optimize_box_positions(trailer, boxes)

    print(f"优化结果:")
    print(f"  总箱数: {result['total_boxes']}")
    print(f"  总重量: {result['total_weight']:.1f} kg")
    print(f"  前轴荷: {result['front_axle_load']:.1f} kg ({result['front_axle_load_ratio']*100:.1f}%)")
    print(f"  后轴荷: {result['rear_axle_load']:.1f} kg ({result['rear_axle_load_ratio']*100:.1f}%)")
    print(f"  轴荷是否超限: {'否' if result['axles_within_limit'] else '是'}")
    print(f"  左右偏差: {result['left_right_balance_ratio']*100:.1f}%")
    print(f"  建议: {result['recommendation']}")

    placed_boxes = []
    for lb in result["loaded_boxes"]:
        placed_boxes.append(PlacedBox(
            box_id=lb["box_id"],
            box_name=lb["box_name"],
            x=lb["x"],
            y=lb["y"],
            length=lb["length"],
            width=lb["width"],
            weight=lb["weight"],
            cog_offset_x=lb["cog_offset_x"]
        ))

    unload_result = generate_unload_sequence(trailer, placed_boxes, max_lr_ratio=0.15)

    print(f"\n卸载顺序仿真:")
    print(f"  全部步骤合法: {'是' if unload_result['all_steps_valid'] else '否'}")
    print(f"  步骤数: {unload_result['total_steps']}")


def main():
    print_separator("多箱联合重心优化与装卸顺序仿真引擎 - 演示")

    demo_scenario_1()
    demo_scenario_2()
    demo_scenario_3()

    print_separator("演示结束")


if __name__ == "__main__":
    main()
