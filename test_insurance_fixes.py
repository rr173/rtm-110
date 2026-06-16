#!/usr/bin/env python3
"""保险模块三个问题修复验证测试"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_hazardous_cargo_match():
    """测试问题3: 危险品货物匹配 - 应该只匹配到危化品特约险,不匹配普通货运险"""
    print("\n" + "="*60)
    print("  测试1: 危险品货物保险产品匹配")
    print("="*60)
    
    payload = {
        "cargo_type": "HAZARDOUS",
        "declared_value": 80000.0,
        "hazard_class": 3,
        "temperature_class": "AMBIENT"
    }
    resp = requests.post(f"{BASE_URL}/insurance/match/cargo", json=payload)
    print(f"状态码: {resp.status_code}")
    
    if resp.status_code == 200:
        matches = resp.json()
        print(f"匹配到 {len(matches)} 个保险产品")
        matched_names = [m['product_name'] for m in matches]
        print(f"匹配产品: {matched_names}")
        
        has_hazard_specialty = "危化品特约险" in matched_names
        has_general = "普通货运险" in matched_names
        
        if has_hazard_specialty and not has_general:
            print("✅ PASS: 危险品只匹配到危化品特约险,排除了普通货运险")
        elif has_hazard_specialty and has_general:
            print("❌ FAIL: 危险品同时匹配到普通货运险和危化品特约险,普通货运险应排除")
            return False
        else:
            print(f"❌ FAIL: 匹配结果异常")
            return False
        
        for m in matches:
            print(f"  - {m['product_name']}")
            print(f"    有效费率(effective_rate): {m.get('effective_rate', 'N/A')}%")
            print(f"    最终费率(final_rate_pct): {m.get('final_rate_pct', 'N/A')}%")
            if m.get('effective_rate') is not None and m.get('effective_rate') > 0:
                print(f"    ✅ 有效费率字段正确返回")
            else:
                print(f"    ❌ 有效费率字段为空")
                return False
        return True
    else:
        print(f"错误: {resp.text}")
        return False


def test_general_cargo_match():
    """测试普通货物匹配 - 不应匹配到危化品特约险"""
    print("\n" + "="*60)
    print("  测试2: 普通货物保险产品匹配")
    print("="*60)
    
    payload = {
        "cargo_type": "ELECTRONICS",
        "declared_value": 50000.0,
        "hazard_class": None,
        "temperature_class": "AMBIENT"
    }
    resp = requests.post(f"{BASE_URL}/insurance/match/cargo", json=payload)
    print(f"状态码: {resp.status_code}")
    
    if resp.status_code == 200:
        matches = resp.json()
        print(f"匹配到 {len(matches)} 个保险产品")
        matched_names = [m['product_name'] for m in matches]
        print(f"匹配产品: {matched_names}")
        
        if "危化品特约险" in matched_names:
            print("❌ FAIL: 普通货物不应匹配到危化品特约险")
            return False
        else:
            print("✅ PASS: 普通货物正确排除了危化品特约险")
        
        for m in matches:
            if m.get('effective_rate') is not None and m.get('effective_rate') > 0:
                print(f"  - {m['product_name']}: 有效费率 {m['effective_rate']}% ✅")
            else:
                print(f"  - {m['product_name']}: 有效费率为空 ❌")
                return False
        return True
    else:
        print(f"错误: {resp.text}")
        return False


def test_surrender():
    """测试问题1: 退保接口 - 应对已承投保单成功退保"""
    print("\n" + "="*60)
    print("  测试3: 退保接口测试")
    print("="*60)
    
    # 1. 先获取投保单列表
    resp = requests.get(f"{BASE_URL}/insurance/policies")
    if resp.status_code != 200:
        print(f"获取投保单失败: {resp.text}")
        return False
    
    policies = resp.json()
    if not policies:
        print("没有找到投保单")
        return False
    
    accepted_policy = None
    for p in policies:
        if p['status'] == 'accepted':
            accepted_policy = p
            break
    
    if not accepted_policy:
        print("没有找到已承保的投保单")
        return False
    
    policy_id = accepted_policy['id']
    print(f"找到已承投保单 ID={policy_id}, 保单号={accepted_policy['policy_no']}")
    print(f"总保费: {accepted_policy['total_premium']} CNY")
    
    # 2. 尝试退保
    payload = {
        "surrender_reason": "测试退保 - 货主取消运输计划",
        "handled_by": "测试员",
        "remarks": "自动化测试"
    }
    resp = requests.post(f"{BASE_URL}/insurance/policies/{policy_id}/surrender", json=payload)
    print(f"退保请求状态码: {resp.status_code}")
    
    if resp.status_code == 500:
        print(f"❌ FAIL: 退保接口返回500错误: {resp.text}")
        return False
    
    if resp.status_code == 200:
        result = resp.json()
        print("退保成功!")
        print(f"  退保单号: {result.get('surrender_no')}")
        print(f"  退保原因: {result.get('surrender_reason')}")
        print(f"  总保费: {result.get('total_premium')} CNY")
        print(f"  已用天数: {result.get('used_days')} 天")
        print(f"  总保险期: {result.get('total_days')} 天")
        print(f"  退费比例: {result.get('refund_ratio')}")
        print(f"  退费金额: {result.get('refund_amount')} CNY")
        print(f"  新状态: {result.get('new_status')}")
        print(f"  退保时间: {result.get('surrendered_at')}")
        print("✅ PASS: 退保接口工作正常")
        return True
    else:
        print(f"退保失败: {resp.text}")
        return False


def main():
    print("\n" + "="*60)
    print("  保险模块三个问题修复验证")
    print("="*60)
    
    all_pass = True
    
    # 测试1: 危险品匹配
    if not test_hazardous_cargo_match():
        all_pass = False
    
    # 测试2: 普通货物匹配 + 有效费率字段
    if not test_general_cargo_match():
        all_pass = False
    
    # 测试3: 退保接口
    if not test_surrender():
        all_pass = False
    
    print("\n" + "="*60)
    if all_pass:
        print("  ✅ 所有修复验证通过!")
    else:
        print("  ❌ 部分测试未通过!")
    print("="*60 + "\n")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
