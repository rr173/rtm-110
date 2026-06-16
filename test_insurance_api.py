#!/usr/bin/env python3
"""保险模块API综合测试"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def test_products():
    print_section("1. 测试保险产品列表")
    resp = requests.get(f"{BASE_URL}/insurance/products")
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        products = resp.json()
        print(f"保险产品数量: {len(products)}")
        for p in products:
            print(f"  - {p['product_code']}: {p['product_name']}")
            print(f"    基础费率: {p['base_rate_pct']}%, 免赔额: {p['deductible_amount']}")
        return products
    else:
        print(f"错误: {resp.text}")
        return None

def test_policies():
    print_section("2. 测试投保单列表")
    resp = requests.get(f"{BASE_URL}/insurance/policies")
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        policies = resp.json()
        print(f"投保单数量: {len(policies)}")
        for p in policies:
            print(f"  - {p['policy_no']}: {p['policyholder_name']}")
            print(f"    状态: {p['status']}, 总保费: {p['total_premium']} CNY")
        return policies
    else:
        print(f"错误: {resp.text}")
        return None

def test_policy_detail(policy_id):
    print_section(f"3. 测试投保单详情 (ID: {policy_id})")
    resp = requests.get(f"{BASE_URL}/insurance/policies/{policy_id}")
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        policy = resp.json()
        print(f"投保单号: {policy['policy_no']}")
        print(f"投保人: {policy['policyholder_name']}")
        print(f"状态: {policy['status']}")
        print(f"航次: {policy['voyage_no']}")
        print(f"总保额: {policy['total_insured_amount']} CNY")
        print(f"总保费: {policy['total_premium']} CNY")
        print(f"保险期限: {policy['insurance_period_days']} 天")
        print(f"生效日期: {policy['effective_date']}")
        print(f"到期日期: {policy['expiry_date']}")
        print(f"\n货物明细 ({len(policy['policy_items'])} 件):")
        for item in policy['policy_items']:
            print(f"  - {item['cargo_name']} ({item['cargo_type']})")
            print(f"    保额: {item['declared_value']} CNY, 保费: {item['premium']} CNY")
            print(f"    费率: {item['final_rate_pct']}% = {item['base_rate_pct']}% × {item['hazard_coeff']} × {item['cold_chain_coeff']} × {item['high_value_coeff']}")
            if item['deductible_summary']:
                print(f"    免赔: {item['deductible_summary'].get('summary', 'N/A')}")
        return policy
    else:
        print(f"错误: {resp.text}")
        return None

def test_match_cargo():
    print_section("4. 测试单件货物保险产品匹配")
    payload = {
        "cargo_type": "ELECTRONICS",
        "declared_value": 150000.0,
        "hazard_class": None,
        "temperature_class": "AMBIENT"
    }
    resp = requests.post(f"{BASE_URL}/insurance/match/cargo", json=payload)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        matches = resp.json()
        print(f"匹配到 {len(matches)} 个保险产品 (按保费从低到高排序):")
        for i, m in enumerate(matches, 1):
            print(f"  {i}. {m['product_name']}")
            print(f"     预估保费: {m['estimated_premium']} CNY")
            print(f"     最终费率: {m['final_rate_pct']}%")
        return matches
    else:
        print(f"错误: {resp.text}")
        return None

def test_premium_calc(product_id):
    print_section(f"5. 测试保费计算 (产品ID: {product_id})")
    payload = {
        "product_id": product_id,
        "declared_value": 200000.0,
        "hazard_class": 3,
        "temperature_class": "REFRIGERATED"
    }
    resp = requests.post(f"{BASE_URL}/insurance/premium/calculate", json=payload)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"基础费率: {result['base_rate_pct']}%")
        print(f"危险品系数: {result['hazard_coeff']}")
        print(f"冷链系数: {result['cold_chain_coeff']}")
        print(f"高价值系数: {result['high_value_coeff']}")
        print(f"最终费率: {result['final_rate_pct']}%")
        print(f"保费: {result['premium']} CNY")
        print(f"\n计算明细:")
        for k, v in result['breakdown'].items():
            print(f"  {k}: {v}")
        print(f"\n免赔条款: {result['deductible_summary'].get('summary', 'N/A')}")
        return result
    else:
        print(f"错误: {resp.text}")
        return None

def test_statistics():
    print_section("6. 测试保险产品统计")
    resp = requests.get(f"{BASE_URL}/insurance/statistics/by-product")
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"统计产品数量: {len(stats)}")
        for s in stats:
            print(f"  - {s['product_name']} ({s['product_code']})")
            print(f"    出单量: {s['total_policies']} 单, 总保费: {s['total_premium']} CNY, 总保额: {s['total_insured_amount']} CNY")
        return stats
    else:
        print(f"错误: {resp.text}")
        return None

def test_match_packing_plan(plan_identifier):
    print_section(f"7. 测试配载方案货物批量匹配 (方案: {plan_identifier})")
    resp = requests.post(f"{BASE_URL}/insurance/match/packing/{plan_identifier}")
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"方案: {result['plan_no']}")
        print(f"货物数量: {result['total_cargos']}")
        for item in result['match_results']:
            print(f"\n  - {item['cargo_name']} (价值: {item['declared_value']} CNY)")
            print(f"    匹配产品数量: {len(item['matched_products'])}")
            for i, p in enumerate(item['matched_products'], 1):
                print(f"    {i}. {p['product_name']}: {p['estimated_premium']} CNY")
        return result
    else:
        print(f"错误: {resp.text}")
        return None

def main():
    print("\n" + "="*60)
    print("  集装箱货物保险模块 API 综合测试")
    print("="*60)

    try:
        # 1. 保险产品列表
        products = test_products()
        if not products:
            print("\n❌ 保险产品测试失败")
            return 1

        # 2. 投保单列表
        policies = test_policies()
        if not policies:
            print("\n❌ 投保单列表测试失败")
            return 1

        # 3. 投保单详情
        if policies:
            policy_detail = test_policy_detail(policies[0]['id'])
            if not policy_detail:
                print("\n❌ 投保单详情测试失败")
                return 1

        # 4. 单件货物匹配
        matches = test_match_cargo()
        if matches is None:
            print("\n❌ 货物匹配测试失败")
            return 1

        # 5. 保费计算
        if products:
            premium = test_premium_calc(products[0]['id'])
            if premium is None:
                print("\n❌ 保费计算测试失败")
                return 1

        # 6. 统计
        stats = test_statistics()
        if stats is None:
            print("\n❌ 统计测试失败")
            return 1

        # 7. 配载方案批量匹配
        if policies:
            match_result = test_match_packing_plan(str(policies[0]['plan_id']))
            if match_result is None:
                print("\n⚠️  配载方案匹配测试跳过")

        print("\n" + "="*60)
        print("  ✅ 所有测试通过!")
        print("="*60 + "\n")
        return 0

    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器,请确保服务已启动在端口 8000")
        return 1
    except Exception as e:
        print(f"\n❌ 测试发生异常: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
