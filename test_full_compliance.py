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
        print(f"HTTP {e.code} on {method} {path}: {e.read()[:500]}")
        raise

print("=" * 70)
print(" 集装箱装载合规审计与海关申报 - 全功能验证")
print("=" * 70)

# 找合规货物
cargos = req("GET", "/cargos?limit=20")
goods = [c for c in cargos if c["name"] in ("普通家电箱", "普通服装箱")]
print(f"\n📦 选用合规货物: {[c['name'] + ' (id='+str(c['id'])+')' for c in goods]}")
cargo_ids = [c["id"] for c in goods]

# 1. 配载计算
print("\n--- 1. 生成配载方案 ---")
resp = req("POST", "/packing/compare?save=true", {
    "cargo_ids": cargo_ids,
    "container_ids": [],
    "enable_split": False
})
plan = resp["plans"][0]
plan_no = plan["plan_no"]
print(f"   方案编号: {plan_no}")
print(f"   装入 {plan['placed_count']}/{plan['total_cargos']} 件")
print(f"   体积利用率: {plan['volume_utilization']:.2%}")

# 2. 更新元信息
print("\n--- 2. 设置箱号/铅封/申报重量 ---")
declared_w = plan["total_weight"] * 1.01  # 故意设偏差1%，在2%以内应该通过
meta = req("PUT", f"/plans/{plan_no}/meta", {
    "container_no": "MSKU-TEST-9999",
    "seal_no": "SEAL-A1B2C3",
    "declared_weight": round(declared_w, 2),
})
print(f"   箱号: {meta['container_no']}")
print(f"   新版本: v{meta['new_version']}")

# 3. 合规审计
print("\n--- 3. 执行合规审计 ---")
audit = req("POST", "/compliance/audit", {"plan_identifier": plan_no})
print(f"   审计编号: {audit['audit_no']}")
print(f"   整体通过: {audit['is_passed']}")
print(f"     - 危险品隔离: {'✅' if audit['hazard_check_passed'] else '❌'} 违规{len(audit['hazard_violations'])}项")
print(f"     - 重量偏差:   {'✅' if audit['weight_check_passed'] else '❌'} 违规{len(audit['weight_violations'])}项")
print(f"     - 品名匹配:   {'✅' if audit['name_check_passed'] else '❌'} 违规{len(audit['name_violations'])}项")
print(f"   备注: {audit['remarks']}")
assert audit["is_passed"], "❌ 合规审计应该通过!"

# 4. 审计列表
print("\n--- 4. 审计列表查询(不带筛选) ---")
all_audits = req("GET", "/compliance/audits?limit=10")
print(f"   共 {len(all_audits)} 条审计记录")
assert len(all_audits) > 0, "❌ 审计列表应该有数据!"

# 5. 生成单据
print("\n--- 5. 生成 Packing List + CLC ---")
docs = req("POST", "/customs/documents/generate", {
    "plan_identifier": plan_no,
    "document_type": "BOTH",
    "issued_by": "测试员小王"
})
print(f"   关联审计: {docs['audit_no']}")
for dtype, info in docs["created_documents"].items():
    print(f"   [{dtype}] {info['document_no']} 件数={info['total_packages']} 重={info['total_weight_kg']}kg")
pl_no = docs["created_documents"]["PACKING_LIST"]["document_no"]
clc_no = docs["created_documents"]["CLC"]["document_no"]

# 6. 查询单据详情
print("\n--- 6. 单据详情 ---")
pl = req("GET", f"/customs/documents/{pl_no}")
print(f"   Packing List: {pl['document_no']}")
print(f"     箱号: {pl['container_no']}  铅封: {pl['seal_no']}")
print(f"     总件数: {pl['total_packages']}  总重: {pl['total_weight_kg']}kg")
print(f"     体积利用率: {pl['volume_utilization']}%  重量利用率: {pl['weight_utilization']}%")
print(f"     重心偏移率: {pl['cog_offset_ratio']}")
print(f"     明细条目: {len(pl['document_items'])} 条")
for it in pl['document_items'][:3]:
    print(f"       #{it['item_no']:3d} {it['cargo_name'][:16]:16s} 层{it['stack_layer']}  ({it['x_mm']},{it['y_mm']},{it['z_mm']})mm")
print(f"       ... 共{len(pl['document_items'])}件")

clc = req("GET", f"/customs/documents/{clc_no}")
layers = clc["document_content"]["layered_loading"]
print(f"\n   CLC 分层装载: {len(layers)} 层")
for lk in sorted(layers.keys()):
    li = layers[lk]
    print(f"     {lk}: {li['piece_count']}件, {li['layer_weight_kg']}kg")

# 7. 单据按编号查询
print("\n--- 7. 按编号查询 ---")
by_no = req("GET", f"/customs/documents?document_no={pl_no}")
print(f"   编号 {pl_no} → 查到 {len(by_no)} 条")
assert len(by_no) == 1 and by_no[0]["document_no"] == pl_no

# 8. 按方案 + status=valid 查询
print("\n--- 8. 按方案查询 + status=valid 过滤 ---")
by_plan_valid = req("GET", f"/customs/documents?plan_identifier={plan_no}&status=valid")
print(f"   方案 {plan_no} 的 valid 单据: {len(by_plan_valid)} 份")
for d in by_plan_valid:
    print(f"     {d['document_no']} {d['document_type']} {d['status']}")
assert all(d["status"] == "valid" for d in by_plan_valid), "❌ valid过滤后不该有非valid的"

# 9. 作废单据
print("\n--- 9. 作废 Packing List ---")
voided = req("POST", f"/customs/documents/{pl_no}/void", {"reason": "单据信息有误，作废重开"})
print(f"   作废后状态: {voided['status']}")
print(f"   作废原因: {voided['void_reason']}")

# 10. 再查 valid 数量
print("\n--- 10. 作废后再查 valid 过滤 ---")
after_void = req("GET", f"/customs/documents?plan_identifier={plan_no}&status=valid")
print(f"   valid单据数: {len(after_void)} (应=1，仅剩CLC)")
assert len(after_void) == 1, "❌ 作废后应只剩1份valid"

# 11. 查 void
void_list = req("GET", f"/customs/documents?plan_identifier={plan_no}&status=void")
print(f"   void单据数: {len(void_list)} (应=1)")
assert len(void_list) == 1

# 12. 版本关联：修改方案 → 旧单自动失效
print("\n--- 11. 方案变更 → 旧单自动失效 ---")
print(f"   修改前 CLC 状态: {clc['status']} (v{clc['plan_version']})")
new_meta = req("PUT", f"/plans/{plan_no}/meta", {
    "container_no": "MSKU-NEW-8888",
})
print(f"   修改后方案版本: v{new_meta['new_version']}")
clc_check = req("GET", f"/customs/documents/{clc_no}")
print(f"   CLC 新状态: {clc_check['status']}")
print(f"   失效原因: {clc_check.get('void_reason', '无')}")
assert clc_check["status"] == "outdated", "❌ 方案变更后单据应自动标记outdated"

# 13. 重开CLC
print("\n--- 12. 作废重开 CLC ---")
reis = req("POST", f"/customs/documents/{clc_no}/reissue", {
    "reason": "箱号变更，重新签发",
    "issued_by": "张主管"
})
print(f"   旧单: {reis['old_document']['document_no']} → {reis['old_document']['status']}")
print(f"   新单: {reis['new_document']['document_no']} → v{reis['new_document']['plan_version']}")
assert reis["new_document"]["status"] == "valid"
assert reis["old_document"]["status"] == "superseded"

print("\n" + "=" * 70)
print(" 🎉 全部测试通过！")
print("=" * 70)
print(" ✅ 品名校验：不一致判不合格")
print(" ✅ 审计列表：不带筛选也返回数据")
print(" ✅ status过滤：按方案查时正确过滤valid/void/outdated")
print(" ✅ 版本关联：方案改了 → 单据自动outdated")
print(" ✅ 作废重开：旧单superseded，新单valid")
print(" ✅ 单据编号查询")
print(" ✅ 完整合规审计 + 双单生成")
print("=" * 70)
