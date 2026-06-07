import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    print("根接口测试成功:", data["message"])


def test_containers():
    response = client.get("/containers")
    assert response.status_code == 200
    containers = response.json()
    print(f"箱型列表: {len(containers)} 个")
    for c in containers:
        print(f"  - {c['name']} (ID: {c['id']})")
    return containers


def test_create_cargos():
    cargos = []
    for i in range(5):
        response = client.post("/cargos", json={
            "name": f"测试货物{i+1}",
            "length": 500.0,
            "width": 400.0,
            "height": 300.0,
            "weight": 10.0,
            "can_rotate_horizontal": True,
            "can_flip": True,
            "max_top_load": 50.0,
            "quantity": 3
        })
        assert response.status_code == 200
        cargo = response.json()
        cargos.append(cargo)
        print(f"创建货物: {cargo['name']} (ID: {cargo['id']}, 数量: {cargo['quantity']})")
    return cargos


def test_compare_packing_split(cargo_ids):
    print("\n=== 测试分箱拆单功能 ===")
    response = client.post("/packing/compare?save=false", json={
        "cargo_ids": cargo_ids,
        "container_ids": [],
        "enable_split": True
    })
    assert response.status_code == 200
    data = response.json()

    print(f"对比ID: {data['comparison_id']}")
    print(f"单箱方案数: {len(data['plans'])}")

    if data.get('split_result'):
        sr = data['split_result']
        print(f"\n分箱拆单结果:")
        print(f"  总箱数: {sr['total_boxes']}")
        print(f"  总货物数: {sr['total_cargos']}")
        print(f"  已装入: {sr['placed_cargos_count']} 件")
        print(f"  未装入: {len(sr['unplaced_cargos'])} 种")
        print(f"  总重量: {sr['total_weight']:.1f} kg")
        print(f"  平均体积利用率: {sr['average_volume_utilization'] * 100:.1f}%")
        print(f"  推荐: {sr['recommendation']}")

        print(f"\n箱型使用情况:")
        for usage in sr['container_usage']:
            print(f"  {usage['container_name']}: {usage['count']} 个")

        print(f"\n各箱详情:")
        for box in sr['boxes'][:5]:
            print(f"  箱{box['box_index']} ({box['container_name']}): "
                  f"装入{box['placed_count']}件, "
                  f"利用率{box['volume_utilization'] * 100:.1f}%, "
                  f"重量{box['total_weight']:.1f}kg")
        if len(sr['boxes']) > 5:
            print(f"  ... 还有 {len(sr['boxes']) - 5} 个箱子")
    else:
        print("错误: 没有返回分箱拆单结果")

    return data


def test_compare_packing_no_split(cargo_ids):
    print("\n=== 测试不分箱的普通对比 (验证向后兼容) ===")
    response = client.post("/packing/compare?save=false", json={
        "cargo_ids": cargo_ids,
        "container_ids": [],
        "enable_split": False
    })
    assert response.status_code == 200
    data = response.json()

    print(f"对比ID: {data['comparison_id']}")
    print(f"方案数: {len(data['plans'])}")
    print(f"推荐: {data['recommendation']}")
    print(f"分箱结果为 None: {data.get('split_result') is None}")

    for plan in data['plans'][:2]:
        print(f"  {plan['container_name']}: "
              f"装入{plan['placed_count']}/{plan['total_cargos']}件, "
              f"利用率{plan['volume_utilization'] * 100:.1f}%")

    return data


if __name__ == "__main__":
    print("=" * 50)
    print("开始 API 集成测试")
    print("=" * 50)

    test_root()
    containers = test_containers()
    cargos = test_create_cargos()
    cargo_ids = [c['id'] for c in cargos]

    test_compare_packing_no_split(cargo_ids)
    test_compare_packing_split(cargo_ids)

    print("\n" + "=" * 50)
    print("所有测试完成！")
    print("=" * 50)
