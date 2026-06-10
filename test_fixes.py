import urllib.request, json

BASE = "http://localhost:8002"

def req(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"__error__": True, "code": e.code, "body": e.read().decode()[:500]}

print("=" * 60)
print("【修复1】品名校验：不一致应判不合格")
print("=" * 60)

# 创建一个名字完全不同的货物
bad_cargo = req("POST", "/cargos", {
    "name": "苹果箱",
    "length": 400, "width": 300, "height": 300, "weight": 10,
    "quantity": 3,
    "declared_name": "Totally Different Name",
    "declared_weight": 10.0
})
print(f"创建货物: id={bad_cargo['id']} name={bad_cargo['name']} declared={bad_cargo['declared_name']}")

# 配载
plans_resp = req("POST", "/packing/compare?save=true", {
    "cargo_ids": [bad_cargo["id"]],
    "container_ids": [],
    "enable_split": False
})
plan_no = plans_resp["plans"][0]["plan_no"]
plan_id = plans_resp["plans"][0]["id"]
print(f"生成方案: {plan_no} 装入={plans_resp['plans'][0]['placed_count']}")

# 合规审计
audit = req("POST", "/compliance/audit", {"plan_identifier": plan_no})
print(f"审计结果: passed={audit['is_passed']}")
print(f"  品名校验: passed={audit['name_check_passed']} 违规数={len(audit['name_violations'])}")
if audit["name_violations"]:
    print(f"  违规示例: {audit['name_violations'][0]}")

# 验证品名校验确实失败了
assert not audit["name_check_passed"], "❌ 品名不一致应该失败但通过了!"
assert not audit["is_passed"], "❌ 品名不一致整体审计应该失败!"
print("✅ 品名校验修复成功：不一致判不合格")

print()
print("=" * 60)
print("【修复2】审计列表不带筛选也能返回数据")
print("=" * 60)

all_audits = req("GET", "/compliance/audits?limit=10")
print(f"直接查审计列表: 返回 {len(all_audits)} 条")
assert len(all_audits) > 0, "❌ 不带筛选应该能返回审计记录!"
for a in all_audits[:3]:
    print(f"  - {a['audit_no']} passed={a['is_passed']} plan={a['plan_no']}")
print("✅ 审计列表修复成功：不带筛选也返回数据")

print()
print("=" * 60)
print("【修复3】按方案查单据 + status过滤生效")
print("=" * 60)

# 先找一个品名为空的货物(普通家电箱)，让它生成单据
good_cargos = req("GET", "/cargos?limit=20")
good = next((c for c in good_cargos if c["name"] == "普通家电箱"), None)
assert good, "找不到普通家电箱"
print(f"找到合规货物: id={good['id']} name={good['name']} declared={good['declared_name']}")

# 生成方案
plans2 = req("POST", "/packing/compare?save=true", {
    "cargo_ids": [good["id"]],
    "container_ids": [],
    "enable_split": False
})
plan2_no = plans2["plans"][0]["plan_no"]
print(f"生成方案: {plan2_no}")

# 设置元信息
req("PUT", f"/plans/{plan2_no}/meta", {
    "container_no": "TEST-001",
    "seal_no": "SEAL-001",
    "declared_weight": good["weight"] * good["quantity"],
})

# 生成单据 (PACKING_LIST)
gen_result = req("POST", "/customs/documents/generate", {
    "plan_identifier": plan2_no,
    "document_type": "PACKING_LIST",
    "issued_by": "测试员"
})
assert "created_documents" in gen_result, f"生成失败: {gen_result}"
pl_no = gen_result["created_documents"]["PACKING_LIST"]["document_no"]
print(f"生成单据: {pl_no} status=valid")

# 作废它
voided = req("POST", f"/customs/documents/{pl_no}/void", {"reason": "作废测试"})
print(f"作废后: status={voided['status']}")

# 查全部单据 (按方案)
all_by_plan = req("GET", f"/customs/documents?plan_identifier={plan2_no}")
print(f"按方案查(全部): {len(all_by_plan)} 条")
for d in all_by_plan:
    print(f"  - {d['document_no']} {d['status']}")

# 只查 valid
valid_by_plan = req("GET", f"/customs/documents?plan_identifier={plan2_no}&status=valid")
print(f"按方案查(valid): {len(valid_by_plan)} 条")
for d in valid_by_plan:
    print(f"  - {d['document_no']} {d['status']}")

# 只查 void
void_by_plan = req("GET", f"/customs/documents?plan_identifier={plan2_no}&status=void")
print(f"按方案查(void): {len(void_by_plan)} 条")
for d in void_by_plan:
    print(f"  - {d['document_no']} {d['status']}")

# 验证
assert len(all_by_plan) >= 1, "❌ 按方案查全部应该至少有1条"
assert len(void_by_plan) == 1 and void_by_plan[0]["document_no"] == pl_no, "❌ status=void 过滤不对"
assert all(d["status"] == "valid" for d in valid_by_plan), "❌ status=valid 过滤后还有非valid的"
print("✅ 按方案查单据 + status过滤 修复成功")

print()
print("🥳 三个修复点全部验证通过!")
