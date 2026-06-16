#!/usr/bin/env python3
import subprocess
import json

def call_analyze():
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', 'http://localhost:8000/damage/inspections/1/analyze'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_claims_count():
    result = subprocess.run(
        ['curl', '-s', 'http://localhost:8000/damage/claims'],
        capture_output=True,
        text=True
    )
    data = json.loads(result.stdout)
    return len(data)

print("=" * 60)
print("API 层幂等性验证测试")
print("=" * 60)

print(f"\n初始理赔记录数: {get_claims_count()}")

print("\n第1次调用分析接口...")
r1 = call_analyze()
a1 = r1['claim_summary']['total_claim_amount']
cid1 = r1['claim_id']
print(f"  理赔ID: {cid1}, 金额: {a1}")
print(f"  调用后理赔记录数: {get_claims_count()}")

print("\n第2次调用分析接口...")
r2 = call_analyze()
a2 = r2['claim_summary']['total_claim_amount']
cid2 = r2['claim_id']
print(f"  理赔ID: {cid2}, 金额: {a2}")
print(f"  调用后理赔记录数: {get_claims_count()}")

print("\n第3次调用分析接口...")
r3 = call_analyze()
a3 = r3['claim_summary']['total_claim_amount']
cid3 = r3['claim_id']
print(f"  理赔ID: {cid3}, 金额: {a3}")
print(f"  调用后理赔记录数: {get_claims_count()}")

print("\n" + "=" * 60)
if a1 == a2 == a3:
    print(f"✓ 三次调用理赔金额一致: {a1}")
    print("✓ 幂等性验证通过！")
else:
    print(f"✗ 金额不一致: {a1} -> {a2} -> {a3}")
    print("✗ 幂等性验证失败！")
print("=" * 60)
