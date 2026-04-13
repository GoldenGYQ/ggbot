#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证sales.json数据
"""

import json

def main():
    with open('sales.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("验证sales.json数据：")
    print("=" * 50)
    
    # 计算总份额
    total_share = 0
    print("各品牌市场份额：")
    for brand in data['brands']:
        name = brand['name']
        share = brand['market_share']
        total_share += share
        print(f"  {name}: {share}%")
    
    print(f"\n总份额: {total_share}%")
    print(f"与100%的差异: {abs(total_share-100):.2f}%")
    
    # 检查数据合理性
    print("\n数据合理性检查：")
    print("-" * 30)
    
    # 1. 检查份额是否在合理范围内
    valid_shares = True
    for brand in data['brands']:
        share = brand['market_share']
        if share < 0 or share > 100:
            print(f"  [ERROR] {brand['name']}的份额{share}%不在0-100范围内")
            valid_shares = False
    
    if valid_shares:
        print("  [OK] 所有品牌份额都在0-100%范围内")
    
    # 2. 检查总份额是否接近100%
    if abs(total_share - 100) < 0.1:
        print(f"  [OK] 总份额{total_share}%接近100%")
    else:
        print(f"  [WARNING] 总份额{total_share}%与100%有较大差异")
    
    # 3. 检查出货量是否合理
    total_shipments = data.get('total_shipments', 0)
    calculated_shipments = 0
    for brand in data['brands']:
        calculated_shipments += brand.get('shipments', 0)
    
    # 转换为相同单位（万台）
    if data.get('total_shipments_unit') == '亿部':
        total_shipments_wan = total_shipments * 10000  # 亿部转万台
    else:
        total_shipments_wan = total_shipments
    
    diff_percent = abs(calculated_shipments - total_shipments_wan) / total_shipments_wan * 100
    
    if diff_percent < 1:
        print(f"  [OK] 各品牌出货量总和与总出货量基本一致")
    else:
        print(f"  [NOTE] 各品牌出货量总和({calculated_shipments:,}万台)与总出货量({total_shipments_wan:,}万台)有{diff_percent:.1f}%差异")
    
    print("\n验证完成！")

if __name__ == "__main__":
    main()