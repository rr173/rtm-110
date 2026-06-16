#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/chengjie/bytedance/newcj/rtm-110')

from app.database import SessionLocal, Base, engine
from app import models, crud

print("=" * 60)
print("测试: 数据库 CRUD 操作")
print("=" * 60)

db = SessionLocal()

try:
    print("\n1. 查询检验记录列表")
    inspections = crud.list_damage_inspections(db)
    print(f"   检验记录数量: {len(inspections)}")
    for insp in inspections:
        print(f"   - {insp.inspection_no}: {insp.plan_no}, 状态={insp.status}")

    if inspections:
        first_insp = inspections[0]
        print(f"\n2. 查询检验记录详情 (ID: {first_insp.id})")
        detail = crud.get_damage_inspection(db, inspection_id=first_insp.id)
        print(f"   检验编号: {detail.inspection_no}")
        print(f"   方案编号: {detail.plan_no}")
        print(f"   总件数: {detail.total_cargos}")
        print(f"   完好: {detail.intact_count}")
        print(f"   轻微损坏: {detail.minor_damage_count}")
        print(f"   严重损坏: {detail.severe_damage_count}")
        print(f"   灭失: {detail.lost_count}")

        print(f"\n3. 查询检验货物明细")
        items = crud.get_inspection_items(db, first_insp.id)
        print(f"   货物明细数量: {len(items)}")
        for item in items:
            print(f"   - {item.cargo_name}: {item.damage_status}, "
                  f"损坏类型={item.damage_type}, 申报价值={item.declared_value}")

        if first_insp.status == "submitted":
            print(f"\n4. 查询损坏推断结果")
            inferences = crud.get_damage_inferences(db, first_insp.id)
            print(f"   推断结果数量: {len(inferences)}")
            for inf in inferences:
                print(f"   - {inf.cargo_name}: {inf.inferred_cause}, "
                      f"置信度={inf.confidence_level}, 责任={inf.responsibility}")

            print(f"\n5. 查询理赔记录")
            claim = db.query(models.ClaimRecord).filter(
                models.ClaimRecord.inspection_id == first_insp.id
            ).first()
            if claim:
                print(f"   理赔编号: {claim.claim_no}")
                print(f"   总理赔金额: {claim.total_claim_amount}")
                print(f"   承运方责任金额: {claim.carrier_responsibility_amount}")
                print(f"   装箱方责任金额: {claim.packer_responsibility_amount}")

                claim_items = crud.get_claim_items(db, claim.id)
                print(f"   理赔明细数量: {len(claim_items)}")
                for ci in claim_items:
                    print(f"   - {ci.cargo_name}: {ci.damage_status}, "
                          f"理赔金额={ci.claim_amount}, 责任={ci.primary_responsibility}")
            else:
                print("   暂无理赔记录 (需要先运行分析)")

    print(f"\n6. 按责任方统计理赔金额")
    stats = crud.get_claim_statistics_by_responsibility(db)
    print(f"   理赔记录数: {stats['claim_count']}")
    print(f"   总金额: {stats['total_amount']}")
    print(f"   承运方: {stats['carrier_amount']}")
    print(f"   装箱方: {stats['packer_amount']}")
    print(f"   货主: {stats['shipper_amount']}")
    print(f"   不可抗力: {stats['force_majeure_amount']}")

    print(f"\n7. 查询理赔记录列表")
    claims = crud.list_claim_records(db)
    print(f"   理赔记录数量: {len(claims)}")
    for claim in claims:
        print(f"   - {claim.claim_no}: {claim.plan_no}, 金额={claim.total_claim_amount}, 状态={claim.status}")

    print("\n" + "=" * 60)
    print("所有数据库 CRUD 测试通过！✓")
    print("=" * 60)

except Exception as e:
    print(f"\n测试失败: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
