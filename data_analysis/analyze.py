#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2025年中国手机市场销量份额分析脚本
读取sales.json文件，分析各品牌市场份额
"""

import json
import os
import sys
from typing import Dict, List, Tuple


def load_sales_data(file_path: str) -> Dict:
    """加载销售数据JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件格式不正确 - {e}")
        sys.exit(1)


def analyze_market_shares(data: Dict) -> Tuple[str, str, float]:
    """分析市场份额数据"""
    brands = data.get('brands', [])
    
    if not brands:
        print("错误：没有找到品牌数据")
        sys.exit(1)
    
    # 找出市场份额最高和最低的品牌
    max_share_brand = None
    min_share_brand = None
    max_share = -1.0
    min_share = 101.0
    total_share = 0.0
    
    for brand in brands:
        share = brand.get('market_share', 0)
        name = brand.get('name', '未知品牌')
        
        # 更新最高份额
        if share > max_share:
            max_share = share
            max_share_brand = name
        
        # 更新最低份额
        if share < min_share:
            min_share = share
            min_share_brand = name
        
        # 累加总份额
        total_share += share
    
    return max_share_brand, min_share_brand, total_share


def format_percentage(value: float) -> str:
    """格式化百分比显示"""
    return f"{value:.1f}%"


def check_total_share(total_share: float) -> Tuple[bool, str]:
    """检查总份额是否为100%"""
    tolerance = 0.1  # 允许的误差范围
    diff = abs(total_share - 100.0)
    
    if diff <= tolerance:
        return True, f"[OK] 总份额为 {format_percentage(total_share)}，接近100%（误差：{diff:.2f}%）"
    else:
        return False, f"[ERROR] 总份额为 {format_percentage(total_share)}，与100%相差 {diff:.2f}%"


def display_analysis_results(data: Dict, max_brand: str, min_brand: str, total_share: float):
    """显示分析结果"""
    print("=" * 60)
    print("2025年中国手机市场销量份额分析报告")
    print("=" * 60)
    
    # 显示基本信息
    print(f"数据年份：{data.get('year', '未知')}")
    print(f"市场：{data.get('market', '未知')}")
    print(f"数据来源：{data.get('data_source', '未知')}")
    print(f"总出货量：{data.get('total_shipments', '未知')} {data.get('total_shipments_unit', '')}")
    print()
    
    # 显示各品牌数据
    print("各品牌市场份额详情：")
    print("-" * 40)
    brands = data.get('brands', [])
    for brand in brands:
        name = brand.get('name', '未知品牌')
        share = brand.get('market_share', 0)
        rank = brand.get('rank', '未知')
        shipments = brand.get('shipments', 0)
        shipments_unit = brand.get('shipments_unit', '')
        
        print(f"  {rank}. {name:10} {format_percentage(share):>8} 出货量：{shipments:,} {shipments_unit}")
    print()
    
    # 显示分析结果
    print("分析结果：")
    print("-" * 40)
    
    # 找出最高和最低份额的具体数值
    max_share = 0
    min_share = 100
    for brand in brands:
        if brand.get('name') == max_brand:
            max_share = brand.get('market_share', 0)
        if brand.get('name') == min_brand:
            min_share = brand.get('market_share', 0)
    
    print(f"1. 市场份额最高的品牌：{max_brand} ({format_percentage(max_share)})")
    print(f"2. 市场份额最低的品牌：{min_brand} ({format_percentage(min_share)})")
    
    # 检查总份额
    is_valid, message = check_total_share(total_share)
    print(f"3. {message}")
    
    print()
    
    # 显示数据质量评估
    print("数据质量评估：")
    print("-" * 40)
    if is_valid:
        print("[PASS] 数据质量良好：各品牌份额总和接近100%")
    else:
        print("[WARNING] 数据质量警告：各品牌份额总和与100%有较大差异")
        print("          建议检查数据源或重新计算各品牌份额")
    
    print("=" * 60)


def main():
    """主函数"""
    # 设置文件路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_file = os.path.join(current_dir, "sales.json")
    
    print(f"正在加载数据文件：{json_file}")
    print()
    
    # 加载数据
    data = load_sales_data(json_file)
    
    # 分析数据
    max_brand, min_brand, total_share = analyze_market_shares(data)
    
    # 显示结果
    display_analysis_results(data, max_brand, min_brand, total_share)
    
    # 返回退出码
    is_valid, _ = check_total_share(total_share)
    return 0 if is_valid else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)