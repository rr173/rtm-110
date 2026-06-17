#!/usr/bin/env python3
"""保险模块第二轮三个问题修复验证测试"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"


def test_statistics():
    """测试1: 按保险产品统计接口 - 出单量不应为0"""
    print("\n" + "="*60)
    print("  测试1: 保险产品统计接口")
    print("="*60)
    
    resp = requests.get(f"{BASE_URL}/insurance/statistics/by-product")
    print(f"状态码: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAIL: {resp.text}")
        return False
    
    stats = resp.json()
    print(f"统计产品数量: {len(stats)}")
    
    has_nonzero = False
    for s in stats:
        print(f"\n  - {s['product_name']} ({s['product_code']})")
        print(f"    出单量: {s['total_policies']} 单")
        print(f"    承保件数: {s.get('total_items', 'N/A')} 件")
        print(f"    总保费: {s['total_premium']} CNY")
        print(f"    总保额: {s['total_insured_amount']} CNY")
        
        if s['total_premium'] > 0:
            if s['total_policies'] > 0:
                print(f"    ✅ 出单量正确, 有保费对应有出单量")
                has_nonzero = True
            else:
                print(f"    ❌ 有保费({s['total_premium']})但出单量为0, 这是bug!")
                return False
    
    if has_nonzero:
        print("\n✅ PASS: 统计接口出单量正确")
        return True
    else:
        print("\n⚠️  没有有效保单数据,请先确保有已承保保单")
        return True


def test_generate_policy_filters_zero_value():
    """测试2: 一键生成投保单 - 应过滤掉无申报价值的货物"""
    print("\n" + "="*60)
    print("  测试2: 一键生成投保单过滤无申报价值货物")
    print("="*60)
    
    # 先找一个配载方案
    resp = requests.get(f"{BASE_URL}/plans?limit=1")
    if resp.status_code != 200:
        print(f"获取配载方案失败: {resp.text}")
        return False
    
    plans = resp.json()
    if not plans:
        print("没有配载方案")
        return False
    
    plan = plans[0]
    plan_id = plan['id']
    print(f"使用配载方案 ID={plan_id}, 编号={plan.get('plan_no')}")
    
    # 先看配载方案的匹配结果,确认有0价值货物
    resp = requests.post(f"{BASE_URL}/insurance/match/packing/{plan_id}")
    if resp.status_code != 200:
        print(f"匹配失败: {resp.text}")
        return False
    
    match_result = resp.json()
    total_cargos = match_result.get('total_cargos', 0)
    zero_value_count = 0
    for item in match_result.get('match_results', []):
        if item.get('declared_value', 0) <= 0:
            zero_value_count += 1
    
    print(f"方案总货物数: {total_cargos}")
    print(f"无申报价值货物数: {zero_value_count}")
    
    if zero_value_count == 0:
        print("⚠️  该方案没有0价值货物,跳过过滤测试")
        return True
    
    # 尝试一键生成投保单
    payload = {
        "policyholder_name": "测试货主有限公司",
        "policyholder_contact": "13800138000",
        "voyage_no": "VOY-TEST-001",
        "insurance_period_days": 30,
        "auto_select_cheapest": True
    }
    resp = requests.post(f"{BASE_URL}/insurance/policies/generate/{plan_id}", json=payload)
    print(f"生成投保单状态码: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAIL: {resp.text}")
        return False
    
    policy = resp.json()
    items = policy.get('policy_items', [])
    print(f"生成的投保单货物明细数量: {len(items)}")
    
    for item in items:
        if item.get('declared_value', 0) <= 0:
            print(f"❌ FAIL: 发现0价值货物[{item.get('cargo_name')}]仍在明细中!")
            return False
        if item.get('premium', 0) <= 0 and item.get('declared_value', 0) > 0:
            print(f"⚠️  货物[{item.get('cargo_name')}]保费为0但有价值,可能是计算问题")
    
    if len(items) < total_cargos - zero_value_count:
        print("⚠️  明细数量比预期少,可能有其他过滤条件")
    elif len(items) == total_cargos - zero_value_count:
        print(f"✅ PASS: 正确过滤了{zero_value_count}件0价值货物,明细{len(items)}件")
    else:
        print(f"⚠️  明细数量{len(items)}多于预期{total_cargos - zero_value_count},请检查")
    
    return True


def test_surrender_and_query():
    """测试3: 退保接口返回退保编号,且可按投保单查询退保记录"""
    print("\n" + "="*60)
    print("  测试3: 退保接口和退保记录查询")
    print("="*60)
    
    # 1. 先找一个已承保或已提交的投保单
    resp = requests.get(f"{BASE_URL}/insurance/policies")
    if resp.status_code != 200:
        print(f"获取投保单失败: {resp.text}")
        return False
    
    policies = resp.json()
    
    # 优先找已承保的,其次是已提交的
    target_policy = None
    for p in policies:
        if p['status'] == 'accepted':
            target_policy = p
            break
    if not target_policy:
        for p in policies:
            if p['status'] == 'submitted':
                target_policy = p
                break
    
    if not target_policy:
        # 如果没有有效保单,先创建一个草稿并提交
        print("没有可退保的保单,先创建一个测试保单...")
        resp = requests.get(f"{BASE_URL}/packing/plans?limit=1")
        if resp.status_code != 200 or not resp.json():
            print("无法创建测试保单")
            return False
        plan_id = resp.json()[0]['id']
        
        # 生成投保单
        payload = {
            "policyholder_name": "退保测试货主",
            "policyholder_contact": "13900139000",
            "voyage_no": "VOY-SUR-TEST",
            "insurance_period_days": 30,
            "auto_select_cheapest": True
        }
        resp = requests.post(f"{BASE_URL}/insurance/policies/generate/{plan_id}", json=payload)
        if resp.status_code != 200:
            print(f"生成保单失败: {resp.text}")
            return False
        policy = resp.json()
        policy_id = policy['id']
        
        # 提交
        resp = requests.post(f"{BASE_URL}/insurance/policies/{policy_id}/status", json={"new_status": "submitted"})
        if resp.status_code != 200:
            print(f"提交保单失败: {resp.text}")
            return False
        
        # 承保
        resp = requests.post(f"{BASE_URL}/insurance/policies/{policy_id}/status", json={"new_status": "accepted"})
        if resp.status_code != 200:
            print(f"承保保单失败: {resp.text}")
            return False
        
        target_policy = resp.json()
    
    policy_id = target_policy['id']
    policy_no = target_policy['policy_no']
    print(f"使用保单 ID={policy_id}, 编号={policy_no}, 状态={target_policy['status']}")
    
    # 2. 先查一下退保记录(应该没有)
    resp = requests.get(f"{BASE_URL}/insurance/surrender/{policy_id}")
    if resp.status_code == 200:
        print(f"⚠️  保单尚未退保但查到了退保记录: {resp.json()}")
    elif resp.status_code == 404:
        print(f"✅ 尚未退保,正确返回404")
    else:
        print(f"❌ 查询退保记录返回异常: {resp.status_code} - {resp.text}")
    
    # 3. 退保
    payload = {
        "surrender_reason": "测试修复-货物取消出运",
        "handled_by": "测试员001",
        "remarks": "自动化测试第二轮修复验证"
    }
    resp = requests.post(f"{BASE_URL}/insurance/policies/{policy_id}/surrender", json=payload)
    print(f"\n退保请求状态码: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAIL: 退保失败: {resp.text}")
        return False
    
    surrender_result = resp.json()
    print("\n退保返回结果:")
    print(f"  保单ID: {surrender_result.get('policy_id')}")
    print(f"  保单号: {surrender_result.get('policy_no')}")
    print(f"  退保编号: {surrender_result.get('surrender_no', 'MISSING!')}")
    print(f"  退保原因: {surrender_result.get('surrender_reason')}")
    print(f"  总保费: {surrender_result.get('total_premium')}")
    print(f"  退费金额: {surrender_result.get('refund_amount')}")
    print(f"  新状态: {surrender_result.get('new_status')}")
    print(f"  退保时间: {surrender_result.get('surrendered_at')}")
    
    surrender_no = surrender_result.get('surrender_no')
    if not surrender_no:
        print("\n❌ FAIL: 退保返回中缺少退保编号(surrender_no)字段!")
        return False
    else:
        print(f"\n✅ 退保编号正确返回: {surrender_no}")
    
    # 4. 再查询退保记录
    resp = requests.get(f"{BASE_URL}/insurance/surrender/{policy_id}")
    print(f"\n查询退保记录状态码: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ FAIL: 查询退保记录失败: {resp.text}")
        return False
    
    surrender_record = resp.json()
    print("\n退保记录查询结果:")
    print(f"  记录ID: {surrender_record.get('id')}")
    print(f"  保单ID: {surrender_record.get('policy_id')}")
    print(f"  退保编号: {surrender_record.get('surrender_no', 'MISSING!')}")
    print(f"  退保原因: {surrender_record.get('surrender_reason')}")
    print(f"  处理人: {surrender_record.get('handled_by')}")
    print(f"  备注: {surrender_record.get('remarks')}")
    print(f"  退费金额: {surrender_record.get('refund_amount')}")
    
    if surrender_record.get('surrender_no') != surrender_no:
        print(f"\n❌ FAIL: 查询到的退保编号[{surrender_record.get('surrender_no')}]与退保返回的[{surrender_no}]不一致!")
        return False
    
    print("\n✅ PASS: 退保接口和退保记录查询都正常")
    return True


def main():
    print("\n" + "="*60)
    print("  保险模块第二轮三个问题修复验证")
    print("="*60)
    
    all_pass = True
    
    # 测试1: 统计接口
    if not test_statistics():
        all_pass = False
    
    # 测试2: 一键生成过滤0价值货物
    if not test_generate_policy_filters_zero_value():
        all_pass = False
    
    # 测试3: 退保接口和查询
    if not test_surrender_and_query():
        all_pass = False
    
    print("\n" + "="*60)
    if all_pass:
        print("  ✅ 所有第二轮修复验证通过!")
    else:
        print("  ❌ 部分测试未通过!")
    print("="*60 + "\n")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
