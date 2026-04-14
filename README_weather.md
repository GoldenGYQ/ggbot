# 天气查询脚本使用说明

## 简介
这是一个简单的天气查询脚本，使用OpenWeatherMap API获取实时天气信息。

## 功能特点
- 查询全球城市的实时天气
- 支持多种温度单位（摄氏度、华氏度、开尔文）
- 显示温度、湿度、气压、风速等详细信息
- 支持中文显示
- 简单的命令行界面

## 安装依赖

```bash
pip install requests
```

## 获取API密钥

1. 访问 [OpenWeatherMap官网](https://openweathermap.org/api)
2. 注册账号（免费）
3. 在控制台获取API密钥
4. 免费版每小时可调用60次，足够日常使用

## 使用方法

### 方法1：设置环境变量
```bash
# Windows (PowerShell)
$env:OPENWEATHER_API_KEY="你的API密钥"

# Linux/macOS
export OPENWEATHER_API_KEY="你的API密钥"
```

### 方法2：直接使用命令行参数

```bash
# 查询北京天气
python weather_simple.py --city 北京 --api-key 你的API密钥

# 查询纽约天气（英文）
python weather_simple.py --city "New York" --api-key 你的API密钥 --lang en

# 使用华氏度
python weather_simple.py --city 上海 --api-key 你的API密钥 --unit imperial

# 使用开尔文温度
python weather_simple.py --city 广州 --api-key 你的API密钥 --unit standard
```

### 方法3：创建配置文件
创建 `.env` 文件：
```
OPENWEATHER_API_KEY=你的API密钥
```

然后运行：
```bash
python weather_simple.py --city 北京
```

## 输出示例

```
============================================================
🌍 城市: 北京, CN
📅 时间: 2026-04-14 15:30:00
------------------------------------------------------------
☀️ 天气: 晴天
🌡️  温度: 22.5°C
🤔  体感温度: 21.8°C
💧  湿度: 45%
📊  气压: 1013 hPa
💨  风速: 3.2 m/s 东南
👁️  能见度: 10 km
☁️  云量: 10%
🌅  日出: 05:45
🌇  日落: 18:30
============================================================
```

## 命令行参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--city` | 城市名称（必需） | 无 | `北京`、`"New York"` |
| `--api-key` | OpenWeatherMap API密钥 | 环境变量 `OPENWEATHER_API_KEY` | `--api-key abc123` |
| `--lang` | 语言代码 | `zh`（中文） | `en`（英文）、`ja`（日文） |
| `--unit` | 温度单位 | `metric`（摄氏度） | `imperial`（华氏度）、`standard`（开尔文） |

## 支持的天气图标

- ☀️ 晴天
- 🌙 晴夜
- ⛅ 少云
- ☁️ 多云/阴天
- 🌧️ 雨
- 🌦️ 阵雨
- ⛈️ 雷雨
- ❄️ 雪
- 🌫️ 雾

## 错误处理

如果遇到错误，脚本会显示相应的错误信息：
- API密钥无效或过期
- 城市名称错误
- 网络连接问题
- API调用次数超限

## 注意事项

1. **免费API限制**：每小时最多60次调用
2. **城市名称**：使用英文城市名时可能需要加引号
3. **网络连接**：需要稳定的网络连接
4. **API密钥安全**：不要将API密钥提交到版本控制系统

## 扩展功能建议

如需更多功能，可以考虑：
1. 添加多天天气预报
2. 添加天气预警信息
3. 支持更多天气API（和风天气、彩云天气等）
4. 添加图形界面
5. 添加天气数据缓存

## 许可证

MIT License