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

plans = req("GET", "/plans?limit=5")
if not plans:
    print("无方案，先创建...")
    resp = req("POST", "/packing/compare?save=true", {
        "cargo_ids": [7, 8],
        "container_ids": [],
        "enable_split": False
    })
    plans = resp["plans"]

plan = plans[0]
plan_no = plan["plan_no"]
plan_id = plan["id"]
print(f"[方案] plan_no={plan_no} plan_id={plan_id} v={plan.get('version')}")

meta = req("PUT", f"/plans/{plan_no}/meta", {
    "container_no": "MSKU1234567",
    "seal_no": "SEAL-998877",
    "declared_weight": 2035.0
})
print(f"\n[元信息更新] version={meta['new_version']} 箱号={meta['container_no']}")

audit = req("POST", "/compliance/audit", {"plan_identifier": plan_no})
print(f"\n[合规审计] audit_no={audit['audit_no']}")
print(f"  通过={audit['is_passed']}")
print(f"  危险品={audit['hazard_check_passed']} 违规={len(audit['hazard_violations'])}")
print(f"  重量={audit['weight_check_passed']} 违规={len(audit['weight_violations'])}")
print(f"  品名={audit['name_check_passed']} 违规={len(audit['name_violations'])}")
print(f"  备注={audit['remarks']}")
for v in audit['weight_violations'][:3]:
    print(f"    重量违规: {v}")

docs = req("POST", "/customs/documents/generate", {
    "plan_identifier": plan_no,
    "document_type": "BOTH",
    "issued_by": "张经理"
})
if "error" in docs:
    print("单据生成失败:", docs)
else:
    print(f"\n[单据生成] audit_no={docs.get('audit_no')} plan_v={docs.get('plan_version')}")
    pl_no = clc_no = None
    for dtype, info in docs.get("created_documents", {}).items():
        print(f"  [{dtype}] no={info['document_no']} id={info['document_id']}")
        print(f"        件数={info['total_packages']} 重={info['total_weight_kg']}kg 体={info['total_volume_cbm']}CBM")
        if dtype == "PACKING_LIST":
            pl_no = info["document_no"]
        if dtype == "CLC":
            clc_no = info["document_no"]

    if pl_no:
        doc = req("GET", f"/customs/documents/{pl_no}")
        print(f"\n[查询PL] no={doc['document_no']} 箱号={doc['container_no']} 封条={doc['seal_no']}")
        print(f"  重心偏移率={doc['cog_offset_ratio']} 体积利用率={doc['volume_utilization']}% 重量利用率={doc['weight_utilization']}%")
        print(f"  明细={len(doc['document_items'])}条")
        for it in doc['document_items'][:5]:
            print(f"    #{it['item_no']} {it['cargo_name'][:14]:14s} w={it['weight_kg']} pos=({it['x_mm']},{it['y_mm']},{it['z_mm']}) L{it['stack_layer']} 危={it.get('hazard_class')}")
        if len(doc['document_items']) > 5:
            print(f"    ...其余{len(doc['document_items'])-5}条省略")

    if clc_no:
        clc = req("GET", f"/customs/documents/{clc_no}")
        layers = clc.get("document_content", {}).get("layered_loading", {})
        print(f"\n[CLC分层] {len(layers)}层")
        for lk, li in layers.items():
            print(f"  {lk}: {li['piece_count']}件 层重={li['layer_weight_kg']}kg")

    if pl_no:
        voided = req("POST", f"/customs/documents/{pl_no}/void", {"reason": "用户主动作废测试"})
        print(f"\n[作废PL] status={voided['status']} reason={voided['void_reason']}")

    if clc_no:
        reis = req("POST", f"/customs/documents/{clc_no}/reissue", {
            "reason": "录入错误重开",
            "issued_by": "李主任"
        })
        if "error" in reis:
            print("重开失败:", reis)
        else:
            print(f"\n[重开CLC] 旧={reis['old_document']['document_no']}→{reis['old_document']['status']}")
            print(f"        新={reis['new_document']['document_no']} v={reis['new_document']['plan_version']}")

all_docs = req("GET", "/customs/documents")
print(f"\n[单据总览] 共{len(all_docs)}份")
for d in all_docs:
    print(f"  {d['document_no']:20s} {d['document_type']:15s} {d['status']:12s} plan={d['plan_no']}v{d['plan_version']}")

print("\n✅ 主流程测试完成")
