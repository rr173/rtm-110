#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/chengjie/bytedance/newcj/rtm-110')

from app.database import SessionLocal
from app import models, crud
from app.damage_claim_engine import (
    DAMAGE_STATUS_SEVERE,
    DAMAGE_STATUS_MINOR,
    DAMAGE_TYPE_CRUSH,
    DAMAGE_TYPE_WET,
)

def test():
    db = SessionLocal()
    
    print("=" * 60)
    print("测试: 修复验证 - 挤压损坏推断和幂等性")
    print("=" * 60)
    
    # 1. 清理旧的测试数据
    print("\n1. 清理旧数据...")
    inspections = db.query(models.CargoDamageInspection).all()
    for ins in inspections:
        db.query(models.DamageInference).filter(
            models.DamageInference.inspection_id == ins.id
        ).delete()
        claims = db.query(models.ClaimRecord).filter(
            models.ClaimRecord.inspection_id == ins.id
        ).all()
        for claim in claims:
            db.query(models.ClaimItem).filter(
                models.ClaimItem.claim_id == claim.id
            ).delete()
            db.delete(claim)
        db.query(models.InspectionCargoItem).filter(
            models.InspectionCargoItem.inspection_id == ins.id
        ).delete()
        db.delete(ins)
    db.commit()
    
    # 2. 重新生成演示数据
    print("2. 重新生成演示数据...")
    crud.create_demo_damage_claim(db)
    
    # 3. 验证问题1: 挤压损坏推断
    print("\n3. 验证问题1: 丙烷气瓶挤压损坏推断")
    inspection = db.query(models.CargoDamageInspection).first()
    print(f"   检验记录: {inspection.inspection_no}")
    
    items = crud.get_inspection_items(db, inspection.id)
    for item in items:
        print(f"   - {item.cargo_name}: status={item.damage_status}, type={item.damage_type}")
    
    inferences = db.query(models.DamageInference).filter(
        models.DamageInference.inspection_id == inspection.id
    ).all()
    
    print(f"\n   推断结果数量: {len(inferences)}")
    crush_found = False
    for inf in inferences:
        print(f"   - {inf.cargo_name}: cause={inf.inferred_cause}, confidence={inf.confidence_level}, resp={inf.responsibility}")
        if inf.inferred_cause == DAMAGE_TYPE_CRUSH:
            crush_found = True
    
    if crush_found:
        print("\n   ✓ 挤压损坏推断存在！问题1修复成功。")
    else:
        print("\n   ✗ 挤压损坏推断缺失！问题1未修复！")
    
    # 4. 验证问题2: 幂等性
    print("\n4. 验证问题2: 分析接口幂等性")
    
    # 获取初始理赔数量
    claim_count_before = db.query(models.ClaimRecord).filter(
        models.ClaimRecord.inspection_id == inspection.id
    ).count()
    print(f"   首次分析后理赔记录数: {claim_count_before}")
    
    # 获取初始理赔金额
    first_claim = db.query(models.ClaimRecord).filter(
        models.ClaimRecord.inspection_id == inspection.id
    ).first()
    first_amount = first_claim.total_claim_amount if first_claim else 0
    print(f"   首次分析后理赔金额: {first_amount}")
    
    # 再次运行分析
    print("   再次调用分析接口...")
    result = crud.run_damage_analysis(db, inspection.id)
    second_amount = result["claim_summary"]["total_claim_amount"]
    
    # 再次统计
    claim_count_after = db.query(models.ClaimRecord).filter(
        models.ClaimRecord.inspection_id == inspection.id
    ).count()
    print(f"   再次分析后理赔记录数: {claim_count_after}")
    print(f"   再次分析后理赔金额: {second_amount}")
    
    if claim_count_before == claim_count_after and first_amount == second_amount:
        print("\n   ✓ 幂等性验证通过！记录数和金额都没有变化，问题2修复成功。")
    else:
        print(f"\n   ✗ 幂等性验证失败！记录数从{claim_count_before}变成{claim_count_after}，问题2未修复！")
    
    # 再跑第三次确保
    print("\n   第三次调用分析接口...")
    result3 = crud.run_damage_analysis(db, inspection.id)
    claim_count_third = db.query(models.ClaimRecord).filter(
        models.ClaimRecord.inspection_id == inspection.id
    ).count()
    third_amount = result3["claim_summary"]["total_claim_amount"]
    print(f"   第三次分析后理赔记录数: {claim_count_third}")
    print(f"   第三次分析后理赔金额: {third_amount}")
    
    if claim_count_third == 1 and third_amount == first_amount:
        print("\n   ✓ 三次调用结果一致，幂等性完全可靠！")
    else:
        print("\n   ✗ 三次调用结果不一致！")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    db.close()

if __name__ == "__main__":
    test()
