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

# 1. 找一个方案
plans = req("GET", "/plans?limit=1")
plan = plans[0]
plan_no = plan["plan_no"]
print(f"[方案] {plan_no} v={plan.get('version')}")

# 2. 生成单据（先确保合规）
print("\n--- 先设置元信息并生成CL单据 ---")
req("PUT", f"/plans/{plan_no}/meta", {
    "container_no": "MSKU-TEST-01",
    "seal_no": "SEAL-TEST-01",
    "declared_weight": 2000.0
})
docs = req("POST", "/customs/documents/generate", {
    "plan_identifier": plan_no,
    "document_type": "CLC",
    "issued_by": "王操作员"
})
clc_no = docs["created_documents"]["CLC"]["document_no"]
doc1 = req("GET", f"/customs/documents/{clc_no}")
print(f"  新单据 CLC_NO={clc_no} STATUS={doc1['status']} plan_v={doc1['plan_version']}")

# 3. 修改方案元信息(触发版本号增长和hash变化)
print("\n--- 修改方案元信息(箱号) → 触发版本+1 + hash变化 + 旧单据失效 ---")
meta2 = req("PUT", f"/plans/{plan_no}/meta", {
    "container_no": "MSKU-NEW-002",
    "seal_no": "SEAL-NEW-002",
})
print(f"  新方案 version={meta2['new_version']} new_hash={meta2['content_hash'][:12]}...")

# 4. 重新检查单据状态 → 应该被标记outdated
doc1_check = req("GET", f"/customs/documents/{clc_no}")
print(f"\n--- 重新检查旧单据 {clc_no} ---")
print(f"  STATUS={doc1_check['status']}")
print(f"  reason={doc1_check.get('void_reason')}")
assert doc1_check["status"] == "outdated", "❌ 方案变更后旧单据应自动失效!"
print("✅ 版本关联自动失效：PASS")

# 5. 再尝试作废已失效单据，应该成功
voided = req("POST", f"/customs/documents/{clc_no}/void", {"reason": "确认作废"})
print(f"\n--- 确认手动作废 ---")
print(f"  STATUS={voided['status']} REASON={voided['void_reason']}")
assert voided["status"] == "void"

# 6. 按编号查询
print("\n--- 按编号查询测试 ---")
r1 = req("GET", f"/customs/documents?document_no={clc_no}")
print(f"  按编号查到 {len(r1)} 条，NO={r1[0]['document_no']}")

# 7. 按方案查询 + 按状态查询
r2 = req("GET", f"/customs/documents?plan_identifier={plan_no}&status=valid")
print(f"  按方案+有效状态查到 {len(r2)} 条 valid 单据")

print("\n🥳 版本关联/自动失效/按编号查询/按方案查询 全部通过!")
