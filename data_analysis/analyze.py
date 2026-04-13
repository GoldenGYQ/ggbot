#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国手机市场销量份额分析脚本
读取 sales.json 文件，分析各品牌市场份额
"""

import json
import os
import sys
from typing import Dict, List, Tuple


def setup_encoding():
    """设置编码环境"""
    if sys.platform == 'win32':
        # Windows系统设置UTF-8编码
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def load_sales_data(file_path: str) -> Dict:
    """加载销售数据JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：JSON文件格式不正确 - {e}")
        exit(1)


def analyze_market_shares(data: Dict) -> Tuple[str, str, float, bool]:
    """
    分析市场份额数据
    
    返回：
    - 最高份额品牌
    - 最低份额品牌
    - 总份额
    - 是否等于100%
    """
    brands = data.get('brands', [])
    
    if not brands:
        print("错误：数据中没有品牌信息")
        exit(1)
    
    # 找出最高和最低份额的品牌
    max_share_brand = None
    min_share_brand = None
    max_share = -1
    min_share = 101  # 初始化为大于100的值
    total_share = 0
    
    for brand_data in brands:
        brand_name = brand_data.get('brand', '未知品牌')
        share = brand_data.get('market_share', 0)
        
        # 更新最高份额
        if share > max_share:
            max_share = share
            max_share_brand = brand_name
        
        # 更新最低份额
        if share < min_share:
            min_share = share
            min_share_brand = brand_name
        
        total_share += share
    
    # 检查总份额是否为100%（允许0.1%的误差）
    is_total_100 = abs(total_share - 100) < 0.1
    
    return max_share_brand, min_share_brand, total_share, is_total_100


def print_analysis_results(data: Dict, max_brand: str, min_brand: str, 
                          total_share: float, is_total_100: bool) -> None:
    """打印分析结果"""
    print("=" * 60)
    print("中国手机市场销量份额分析报告")
    print(f"年份：{data.get('year', '未知')}")
    print(f"市场：{data.get('market', '未知')}")
    print(f"数据来源：{data.get('data_source', '未知')}")
    print("=" * 60)
    
    print("\n各品牌市场份额详情：")
    print("-" * 40)
    for brand_data in data.get('brands', []):
        brand = brand_data.get('brand', '未知品牌')
        share = brand_data.get('market_share', 0)
        description = brand_data.get('description', '')
        
        # 添加标记（使用文本代替Unicode表情）
        markers = []
        if brand == max_brand:
            markers.append("[最高份额]")
        if brand == min_brand:
            markers.append("[最低份额]")
        
        marker_str = " " + " ".join(markers) if markers else ""
        
        # 使用更兼容的格式化方式
        brand_str = brand.ljust(10)
        print(f"{brand_str} : {share:5.1f}%{marker_str}")
        if description:
            print(f"           {description}")
    
    print("\n" + "=" * 60)
    print("分析结果：")
    print(f"1. 市场份额最高的品牌：{max_brand}")
    print(f"2. 市场份额最低的品牌：{min_brand}")
    print(f"3. 所有品牌份额总和：{total_share:.2f}%")
    
    if is_total_100:
        print(f"4. 份额总和检查：[通过] 总和为100%（误差范围内）")
    else:
        print(f"4. 份额总和检查：[失败] 总和不为100%（实际为{total_share:.2f}%）")
        print(f"   提示：总份额应为100%，当前偏差：{abs(total_share-100):.2f}%")
    
    print(f"\n市场总规模：{data.get('total_market_size', '未知')}")
    print(f"备注：{data.get('note', '')}")
    print("=" * 60)


def main():
    """主函数"""
    # 设置编码
    setup_encoding()
    
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(script_dir, "sales.json")
    
    print("正在加载数据...")
    data = load_sales_data(data_file)
    
    print("正在分析数据...")
    max_brand, min_brand, total_share, is_total_100 = analyze_market_shares(data)
    
    print_analysis_results(data, max_brand, min_brand, total_share, is_total_100)
    
    # 验证结果合理性
    print("\n结果合理性验证：")
    print("-" * 40)
    
    # 检查是否有负值份额
    has_negative = any(b.get('market_share', 0) < 0 for b in data.get('brands', []))
    if has_negative:
        print("[警告] 发现负值市场份额")
    else:
        print("[通过] 所有市场份额均为非负值")
    
    # 检查份额是否在合理范围内
    all_in_range = all(0 <= b.get('market_share', 0) <= 100 for b in data.get('brands', []))
    if all_in_range:
        print("[通过] 所有市场份额均在0-100%范围内")
    else:
        print("[警告] 发现超出0-100%范围的市场份额")
    
    # 检查是否有重复品牌
    brands = [b.get('brand', '') for b in data.get('brands', [])]
    unique_brands = set(brands)
    if len(brands) == len(unique_brands):
        print("[通过] 品牌名称无重复")
    else:
        print("[警告] 发现重复的品牌名称")
    
    # 额外验证：检查数据完整性
    print("\n数据完整性检查：")
    print("-" * 40)
    
    required_fields = ['year', 'market', 'brands']
    missing_fields = [field for field in required_fields if field not in data]
    if not missing_fields:
        print("[通过] 所有必需字段都存在")
    else:
        print(f"[警告] 缺少必需字段：{', '.join(missing_fields)}")
    
    # 检查每个品牌是否有必要的字段
    brand_issues = []
    for i, brand_data in enumerate(data.get('brands', [])):
        if 'brand' not in brand_data:
            brand_issues.append(f"第{i+1}个品牌缺少品牌名称")
        if 'market_share' not in brand_data:
            brand_issues.append(f"品牌 '{brand_data.get('brand', f'第{i+1}个品牌')}' 缺少市场份额数据")
    
    if not brand_issues:
        print("[通过] 所有品牌数据完整")
    else:
        print("[警告] 发现品牌数据问题：")
        for issue in brand_issues:
            print(f"  - {issue}")


if __name__ == "__main__":
    main()