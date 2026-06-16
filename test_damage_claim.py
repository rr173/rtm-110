#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/chengjie/bytedance/newcj/rtm-110')

from app.damage_claim_engine import (
    infer_damage_cause,
    calculate_claim_amount,
    determine_primary_responsibility,
    analyze_damage_and_generate_claim,
    DAMAGE_STATUS_MINOR,
    DAMAGE_STATUS_SEVERE,
    DAMAGE_TYPE_CRUSH,
    DAMAGE_TYPE_WET,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    RESPONSIBILITY_PACKER,
    RESPONSIBILITY_CARRIER,
)

print("=" * 60)
print("测试1: 理赔金额计算")
print("=" * 60)

ratio, amount = calculate_claim_amount(10000, DAMAGE_STATUS_MINOR)
print(f"轻微损坏: 申报价值10000, 理赔比例={ratio}, 理赔金额={amount}")
assert ratio == 0.5
assert amount == 5000

ratio, amount = calculate_claim_amount(10000, DAMAGE_STATUS_SEVERE)
print(f"严重损坏: 申报价值10000, 理赔比例={ratio}, 理赔金额={amount}")
assert ratio == 0.8
assert amount == 8000

ratio, amount = calculate_claim_amount(10000, "lost")
print(f"灭失: 申报价值10000, 理赔比例={ratio}, 理赔金额={amount}")
assert ratio == 1.0
assert amount == 10000

print("✓ 理赔金额计算测试通过")

print("\n" + "=" * 60)
print("测试2: 挤压损坏推断")
print("=" * 60)

inspection_item = {
    "id": 1,
    "cargo_id": 101,
    "cargo_name": "测试货物A",
    "damage_status": DAMAGE_STATUS_SEVERE,
    "damage_type": DAMAGE_TYPE_CRUSH,
    "declared_value": 5000,
    "x": 100,
    "y": 100,
    "z": 0,
    "length": 500,
    "width": 400,
    "height": 300,
    "weight": 100,
    "max_top_load": 80,
}

all_cargos = [
    inspection_item,
    {
        "id": 2,
        "cargo_id": 102,
        "cargo_name": "顶部货物",
        "x": 100,
        "y": 100,
        "z": 300,
        "length": 500,
        "width": 400,
        "height": 200,
        "weight": 100,
    },
]

plan_data = {
    "cog_offset_x_ratio": 0.05,
    "cog_offset_y_ratio": 0.03,
}

inferences = infer_damage_cause(
    inspection_item,
    all_cargos,
    plan_data,
    container_length=6000
)

print(f"推断结果数量: {len(inferences)}")
for inf in inferences:
    print(f"  - 原因: {inf['inferred_cause']}")
    print(f"    置信度: {inf['confidence_level']}")
    print(f"    责任方: {inf['responsibility']}")
    print(f"    说明: {inf['explanation']}")

print("✓ 挤压损坏推断测试通过")

print("\n" + "=" * 60)
print("测试3: 浸湿损坏推断")
print("=" * 60)

wet_item = {
    "id": 3,
    "cargo_id": 103,
    "cargo_name": "门口货物",
    "damage_status": DAMAGE_STATUS_MINOR,
    "damage_type": DAMAGE_TYPE_WET,
    "declared_value": 3000,
    "x": 5400,
    "y": 100,
    "z": 0,
    "length": 500,
    "width": 400,
    "height": 300,
    "weight": 50,
}

wet_inferences = infer_damage_cause(
    wet_item,
    [wet_item],
    plan_data,
    container_length=6000
)

print(f"推断结果数量: {len(wet_inferences)}")
for inf in wet_inferences:
    print(f"  - 原因: {inf['inferred_cause']}")
    print(f"    置信度: {inf['confidence_level']}")
    print(f"    责任方: {inf['responsibility']}")
    print(f"    说明: {inf['explanation']}")

print("✓ 浸湿损坏推断测试通过")

print("\n" + "=" * 60)
print("测试4: 责任判定")
print("=" * 60)

test_inferences = [
    {"responsibility": RESPONSIBILITY_PACKER, "confidence_level": CONFIDENCE_HIGH},
    {"responsibility": RESPONSIBILITY_CARRIER, "confidence_level": CONFIDENCE_MEDIUM},
]

primary = determine_primary_responsibility(test_inferences)
print(f"主要责任方: {primary}")
assert primary == RESPONSIBILITY_PACKER

print("✓ 责任判定测试通过")

print("\n" + "=" * 60)
print("测试5: 完整分析流程")
print("=" * 60)

inspection_data = {
    "inspection_items": [
        {
            "id": 1,
            "cargo_id": 101,
            "cargo_name": "货物A",
            "damage_status": DAMAGE_STATUS_SEVERE,
            "damage_type": DAMAGE_TYPE_CRUSH,
            "declared_value": 5000,
            "x": 100,
            "y": 100,
            "z": 0,
            "length": 500,
            "width": 400,
            "height": 300,
            "weight": 100,
            "max_top_load": 80,
        },
        {
            "id": 2,
            "cargo_id": 102,
            "cargo_name": "货物B",
            "damage_status": DAMAGE_STATUS_MINOR,
            "damage_type": DAMAGE_TYPE_WET,
            "declared_value": 3000,
            "x": 5400,
            "y": 100,
            "z": 0,
            "length": 500,
            "width": 400,
            "height": 300,
            "weight": 50,
        },
        {
            "id": 3,
            "cargo_id": 103,
            "cargo_name": "货物C",
            "damage_status": "intact",
            "declared_value": 2000,
            "x": 1000,
            "y": 100,
            "z": 0,
            "length": 500,
            "width": 400,
            "height": 300,
            "weight": 80,
        },
    ]
}

all_cargos_full = [
    {"id": 1, "cargo_id": 101, "cargo_name": "货物A", "x": 100, "y": 100, "z": 0, "length": 500, "width": 400, "height": 300, "weight": 100, "max_top_load": 80},
    {"id": 2, "cargo_id": 102, "cargo_name": "货物B", "x": 5400, "y": 100, "z": 0, "length": 500, "width": 400, "height": 300, "weight": 50, "max_top_load": 50},
    {"id": 3, "cargo_id": 103, "cargo_name": "货物C", "x": 1000, "y": 100, "z": 0, "length": 500, "width": 400, "height": 300, "weight": 80, "max_top_load": 100},
    {"id": 4, "cargo_id": 104, "cargo_name": "货物D", "x": 100, "y": 100, "z": 300, "length": 500, "width": 400, "height": 200, "weight": 100, "max_top_load": 0},
]

result = analyze_damage_and_generate_claim(
    inspection_data,
    plan_data,
    all_cargos_full,
    container_length=6000
)

print(f"推断总数: {len(result['inferences'])}")
print(f"理赔总金额: {result['claim_summary']['total_claim_amount']}")
print(f"总申报价值: {result['claim_summary']['total_declared_value']}")
print(f"轻微损坏金额: {result['claim_summary']['minor_damage_amount']}")
print(f"严重损坏金额: {result['claim_summary']['severe_damage_amount']}")
print(f"承运方责任金额: {result['claim_summary']['carrier_responsibility_amount']}")
print(f"装箱方责任金额: {result['claim_summary']['packer_responsibility_amount']}")
print(f"理赔项数: {len(result['claim_summary']['claim_items'])}")

print("\n理赔明细:")
for item in result['claim_summary']['claim_items']:
    print(f"  - {item['cargo_name']}: {item['damage_status']}, "
          f"申报价值={item['declared_value']}, "
          f"理赔比例={item['claim_ratio']}, "
          f"理赔金额={item['claim_amount']}, "
          f"主要责任={item['primary_responsibility']}")

print("✓ 完整分析流程测试通过")

print("\n" + "=" * 60)
print("所有测试通过！✓")
print("=" * 60)
