# GGbot Ink Frontend (示例)

最小的基于 Ink 的终端前端，用来通过 GGbot HTTP API 快速交互。

要求
- Node.js 18+，npm

安装

```bash
cd example/frontend
npm install
```

运行

```bash
# 指定 API 地址（可选）
export GGBOT_API_URL=http://127.0.0.1:8000
npm start
```

在 Windows PowerShell 下：

```powershell
$env:GGBOT_API_URL = 'http://127.0.0.1:8000'
npm start
```

说明
- 在输入框回车会将内容 POST 到 `/api/v1/messages`。
- 若 API 返回结构不同，会尝试以 JSON 字符串显示返回值。
