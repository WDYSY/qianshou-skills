---
name: html-generator
description: 把分析结论整理成精美的HTML可视化页面。当用户需要生成HTML报告、可视化页面、数据图表页面、地图展示页面时使用。
---

> ⚠️ 开始工作前用 `Grep` 在 `references/learned.md` 里按当前任务的关键词查相关教训（积累的踩坑记录，文件可能很长——**不要一次性 Read 全文**，先 grep 命中再针对性看上下文。文件不存在则跳过）

# HTML 可视化页面生成

将分析结论、数据报告整理为图文并茂的单页 HTML 可视化页面，保存后提供可访问的 URL。

## 设计规范

### 页面风格

- **单页面应用**，纯 HTML + CSS + JS，不依赖 Vue/React 等框架
- **色彩风格**：如果没有更专业的风格，可以参考携程旅行网，主色 #0086F6（携程蓝）、辅助色 #FF7D13（活力橙）、背景 #F5F7FA、卡片白 #FFFFFF
- **风格要求**：专业优雅、信息层次清晰
- **布局**：合理留白，响应式适配
- **字体**：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`

### 配色方案(参考)

```
主色系：#0086F6, #005CE6, #003CB3
橙色系：#FF7D13, #FF9A3E, #FFB86A
辅助色：#00C853（成功）, #FF5252（警告）, #7C4DFF（强调）
中性色：#1A1A1A, #333333, #666666, #999999, #CCCCCC, #F5F7FA
图表色板：['#0086F6', '#FF7D13', '#00C853', '#7C4DFF', '#FF5252', '#26C6DA', '#FFD54F', '#AB47BC']
```

## 数据可视化

### ECharts 图表

使用 ECharts CDN 呈现专业可视化效果。**vendor 一律走 pages 静态资源**（公网可达，playwright 截图能走通，本地浏览器能直接打开，发布到 pages 时会被自动重写成相对路径）：

```html
<!-- ✅ 推荐：pages 公网 vendor（playwright/本地/pages 三端都能用） -->
<script src="{{当前助手上下文中的 GitLab Pages 根地址}}/static/vendor/echarts.min.js"></script>

<!-- ❌ 避免：jsdelivr / K8s 集群内域名（{SYS_BASE_URL}/...）— playwright 沙箱通常走不通 -->
```

可使用的图表类型（根据数据特点选择最合适的）：

| 场景 | 推荐图表 |
|------|----------|
| 趋势变化 | 折线图（面积图）、多轴折线 |
| 大小对比 | 柱状图（堆叠/分组）、条形图 |
| 占比构成 | 饼图、环形图、玫瑰图 |
| 多维对比 | 雷达图 |
| 相关性/分布 | 散点图、气泡图 |
| 流向关系 | 桑基图 |
| 层级结构 | 矩形树图、旭日图 |
| 进度/仪表 | 仪表盘 |
| 排名 | 水平条形图 |
| 热度分布 | 热力图 |
| 组合分析 | 双轴图、图表联动 |

ECharts 配置要求：
- 设置 `tooltip`、`legend`、`toolbox`（含保存图片、数据视图）
- 使用上方配色方案的图表色板
- 添加合理的动画效果
- 图表容器设置合适的高度（至少 400px）
- 响应式：监听 `window.resize` 事件调用 `chart.resize()`

#### ECharts 交互与防裁切硬约束

- 每个 `series` 必须设置有业务含义的 `series.name`，禁止依赖 ECharts 自动生成的 `series0`；否则 tooltip、legend 和 toolbox 的数据视图都无法正确表达指标名。
- 自定义 tooltip 前先确认 `trigger` 的回调参数形态：`trigger: 'axis'` 的 `formatter` 收到数组，`trigger: 'item'` 收到单个对象。需要同时兼容时，先归一化参数，禁止直接读取不确定的 `params.name` / `params.value`：

```javascript
tooltip: {
  trigger: 'axis',
  formatter: function (params) {
    const items = Array.isArray(params) ? params : [params];
    if (!items.length) return '';
    const title = items[0].axisValue ?? items[0].name ?? '';
    return [title].concat(items.map(function (item) {
      const value = item.value ?? '-';
      return item.marker + (item.seriesName || '数值') + '：' + value;
    })).join('<br/>');
  }
}
```

- tooltip 中不得出现 `undefined`、`null` 或 `[object Object]`。数据结构复杂时应在 `series.data` 中使用 `{name, value}`，或按 `dataIndex` 回查原始数据，不能猜测字段名。
- 横向条形图、负数图、瀑布图以及带外置 `label` 的图表，必须设置 `grid.containLabel: true`，并为外置标签预留足够的 `grid.left` / `grid.right`（通常至少 60–100px，长文本按实际宽度增加）。正负值并存时两侧都要检查，不能只保证柱体在绘图区内。
- label 的小数位、百分号等格式只能影响展示，tooltip 与数据视图仍应保留可核对的原始数值。

### 数据表格与大宽表（矩阵表）硬约束

当页面包含多列数据表或二维矩阵表（如「船司 × 售卖站点」矩阵）时，必须遵守以下规范：

1. **大表数据压缩与同步渲染（防移动端弱网半截断流）**
   - 当表格单元格总数 > 500（如 75 行 × 43 列 = 3,225 格）时，**禁止**在 HTML 中直接硬编码展开几千个带内联 `style="background:..."`、`title="..."`、多子标签的 `<td>`（会产生 300KB+ 的超长单行 HTML；在内网容器未开启 gzip 或移动端弱网下，浏览器解析完前几 KB 的 `<thead>` 后卡在庞大的 `<tbody>` 传输中，页面就会停留在「只有一行表头、无表体、无底部图例与页脚」的半截状态）。
   - **正确做法**：将列头与行数据存为紧凑的 JS 数组（如 `const COLS = [...]; const ROWS = [...];`），紧跟在 `<table>` 之后用同步 `<script>` 一次性拼接 `tbody.innerHTML`，将整页 HTML 体积控制在 50 KB 以内。

2. **表头标签统一与冻结列（`position: sticky`）层级/选择器规范**
   - `<thead>` 内的所有表头单元格**必须统一使用 `<th>`**，禁止在 `<thead>` 里混写 `<td class="rtype">` 或 `<td class="total">`（会导致无法命中 `thead th { position: sticky; top: 0 }`，纵向滚动时该列表头跟着表体滚走）。
   - 冻结列的宽度与定位必须写在类选择器上（如 `.idx`、`.rowhead`、`.rtype`、`.total`），**禁止**写成 `td.idx`（会导致 `<th class="idx">` 丢失 `width/min-width` 和 `left: 0`，不仅横向滚动时表头 `#` 脱落，且在空表或加载中时第一列变窄，与第二列 `left: 36px` 之间裂开一道白缝）。
   - 左上角交叉固定的表头格（同时具有 `top: 0` 和 `left: ...`）必须设置更高的 `z-index`（如 `thead th.idx, thead th.rowhead { z-index: 5 }`；普通表头 `thead th { z-index: 3 }`；表体左侧固定列 `z-index: 2`）。

3. **移动端窄屏（`@media (max-width: 768px)`）冻结列宽度红线**
   - **手机端左侧 `sticky` 冻结列总宽度严禁超过 160px（即 375px 屏宽的 45%）**。
   - 若桌面端冻结了 3～4 列（如 `#` 36px + `名称` 150px + `类型` 206px + `合计` 56px = 448px，已超过手机整屏宽度），必须在 `@media (max-width: 768px)` 下将次要冻结列（如「类型」「合计」）重置为 `position: static; left: auto;`（其表头仅保留 `position: sticky; top: 0; left: auto;`），手机端只保留最核心的 1～2 列（如 `#` 32px + `名称` 124px）横向固定，确保右侧数据列有充足的横向滑动视口。

4. **行列双向搜索框（同时支持搜行名 / 搜列名）禁止无条件求交集**
   - 当搜索框占位符提示可搜「行关键词或列关键词」（如 `筛选船司 / 站点（如 公主、en-US）`）时，**严禁**简单用 `colHit = headCells.map(c => c.includes(v))` 和 `rowHit = row.includes(v)` 同时隐藏不命中的列和行：否则输入行名（`公主`）时所有列 `colHit = false` 导致全表消失，输入列名（`en-US`）时所有行 `rowHit = false` 导致只剩一行表头。
   - **正确做法**：
     - 左侧固定信息列（如前 4 列 `#`、`名称`、`类型`、`合计`）在列过滤中始终保持显示（`if (i < 4) return true;`）；
     - 将用户输入按空格/逗号拆分为词元，分别匹配列头文本（含 `title` 属性）得到 `colTokens`、匹配行文本得到 `rowTokens`；
     - 仅当存在匹配的 `colTokens` 时才隐藏未命中的数据列，仅当存在匹配的 `rowTokens` 时才隐藏未命中的数据行；存在既不匹配任何行也不匹配任何列的词元时显示 `.empty-tip`（「未找到匹配项」提示）。

### Mermaid 设计图

流程图、时序图、类图、ER 图、状态机、Gantt、思维导图等"文字驱动的设计图"用 mermaid。**同样用项目本地缓存**：

```html
<script src="{{当前助手上下文中的 GitLab Pages 根地址}}/static/vendor/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default', securityLevel: 'loose' });</script>

<div class="mermaid">
sequenceDiagram
    用户->>百舸: 排序请求
    百舸-->>用户: 排序结果
</div>
```

支持的图类型：
| 用途 | 关键字 |
|------|--------|
| 流程图 / 架构图 | `graph LR` / `graph TD` / `flowchart` |
| 时序图 | `sequenceDiagram` |
| 类图 | `classDiagram` |
| 状态机 | `stateDiagram-v2` |
| ER 图 | `erDiagram` |
| Gantt | `gantt` |
| 思维导图 | `mindmap` |
| 用户旅程 | `journey` |

容器宽度至少 800px，复杂时序图建议 1200px+。

### 百度地图

涉及经纬度、地理位置、热力图、距离计算等场景，使用百度地图 JS API：

```html
<script src="https://api.map.baidu.com/api?v=2.0&ak=${BAIDU_MAP_KEY}"></script>
<!-- 如需热力图 -->
<script src="https://api.map.baidu.com/library/Heatmap/2.0/src/Heatmap_min.js"></script>
```

百度地图密钥从环境变量读取：`BAIDU_MAP_KEY=9oOu88qSixRH10Coy9Puw0hC6bq8md3u`

注意事项：
- 使用 `v=2.0`（非 WebGL 版本），配合 `BMap` 类和 `BMapLib.HeatmapOverlay`
- 不要用 `v=3.0&type=webgl`（BMapGL），热力图库不兼容
- 不要使用 `setMapStyle` 个性化地图（当前 key 未开通该服务）

支持的地图场景：
- 标注点标记（地点位置）
- 热力图（BMapLib.HeatmapOverlay）
- 两点间直线距离（`map.getDistance(pointA, pointB)`）
- 驾车路线规划（BMap.DrivingRoute）
- 步行路线规划（BMap.WalkingRoute）
- 区域围栏/多边形（BMap.Polygon）
- 信息窗口（BMap.InfoWindow）

地图配置要求：
- 地图容器高度至少 500px
- 设置合理的初始中心点和缩放级别
- 添加比例尺、缩放控件
- 热力图使用默认 gradient（不要自定义 gradient，自定义容易产生明显的圆形暗圈），只设 `radius: 30`
- 标注点使用小尺寸（12px 以内）自定义样式，不要遮挡热力图

### 热力图正确用法示例

```javascript
var map = new BMap.Map('map-container');
map.centerAndZoom(new BMap.Point(121.47, 31.23), 11);
map.enableScrollWheelZoom(true);
map.addControl(new BMap.ScaleControl());
map.addControl(new BMap.NavigationControl({ type: BMAP_NAVIGATION_CONTROL_ZOOM }));

var heatmapOverlay = new BMapLib.HeatmapOverlay({ radius: 30 });
map.addOverlay(heatmapOverlay);
heatmapOverlay.setDataSet({
    data: [{ lng: 121.47, lat: 31.23, count: 100 }, ...],
    max: 100
});
```

## HTML 模板结构参考

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{页面标题}}</title>
    <!-- favicon: **必须包含**这一行原样写法。本地预览不解析这个占位符（favicon 会 404，页面主体正常）；
         publish_to_pages.py 发布时会自动重写为 pages 仓库的相对路径 ../../logov4.jpg。
         不要省略、不要改成 data: URI、不要自己写相对路径、不要把占位符替换成实际域名。 -->
    <link rel="icon" type="image/jpeg" href="{SYS_BASE_URL}/static/logov4.jpg">
    <script src="{{当前助手上下文中的 GitLab Pages 根地址}}/static/vendor/echarts.min.js"></script>
    <!-- 如需 mermaid 设计图 -->
    <!-- <script src="{{当前助手上下文中的 GitLab Pages 根地址}}/static/vendor/mermaid.min.js"></script> -->
    <!-- 如需地图 -->
    <script src="https://api.map.baidu.com/api?v=2.0&ak=9oOu88qSixRH10Coy9Puw0hC6bq8md3u"></script>
    <!-- 如需热力图 -->
    <script src="https://api.map.baidu.com/library/Heatmap/2.0/src/Heatmap_min.js"></script>
    <style>
        /* 风格样式 */
    </style>
</head>
<body>
    <div class="container">
        <header>...</header>
        <main>
            <!-- 网页内容 -->
        </main>
        <footer>
            <p>{{当前助手名称}}</p>
            <p style="color:#999; font-size:12px; margin-top:8px;">⚠️ 免责声明：本页面内容由 AI 调研生成，可能存在数据偏差或理解偏差，请仔细校验后再用于决策。</p>
        </footer>
    </div>
    <script>
        // ECharts / BaiduMap 初始化
    </script>
</body>
</html>
```

## 输出规范

### 文件保存

页面采用**双写策略**：

1. **本地副本**（admin 后台预览/排查用）
   - 路径：`/home/powerop/work/baige-ai-assistant/ui/generated/{YYYYMM}/`
   - 文件命名：`{topic}_{YYYYMMDD_HHmmss}.html`，如 `order_analysis_20260509_143022.html`
   - 命名只用英文字母、数字、下划线
   - 保存前确保年月子目录存在（自动创建）

2. **GitLab Pages 发布**（给用户的对外链接）
   - 由 `publish_to_pages.py` 按当前助手上下文，把本地副本拷贝并 push 到该助手的 Pages 仓库
   - 最终报告 URL 必须以本次发布脚本成功返回的完整 URL 为准，禁止自行拼接。
   - 正常交付使用脚本返回且通过下文强校验的 Pages 链接；发布或校验失败时按下文兜底规则处理。

### 访问 URL

发布成功且交付前强校验通过后，向用户提供本次发布脚本返回的完整 URL，并使用 Markdown 链接格式展示。

只允许修改链接标题，链接目标必须逐字使用脚本返回值。具体交付要求见下文「第四步：回复用户」。

**用户信息**：根据当前飞书发送者邮箱前缀决定 `<user-id>`（例如邮箱为 `first_last@trip.com`，则 `<user-id>` 为 `first.last`）。新用户首次出现时，`publish_to_pages.py` 会自动创建用户主页骨架。


### 质量要求

- HTML 文件必须完整可独立运行
- 页面在浏览器中打开后应立即渲染，无空白/报错
- **`<head>` 里必须有 favicon 链接**（按上方模板里的 SYS_BASE_URL 写法），不要省略；publish_to_pages.py 会负责把它重写成 pages 上的相对路径
- 图表数据直接嵌入 JS 变量，不依赖额外接口
- 页面底部标注生成时间和数据来源
- 复杂数据集超过页面承载时，添加筛选/切换交互
- 详细报告类型页面，同时包含结构化的文字内容、专业高级的可视化模块
- 图表需要有SQL、引用互联网数据需要有清晰的来源
- **截图自检**（仅 `VISION_OK`）：发布前用 playwright 截图并 Read，在 1280px 桌面宽度下逐项 hover 所有图表系列，确认标题、系列名和值均正确，且不出现 `undefined`。打开每张图的 toolbox 数据视图，确认表头使用业务指标名而不是 `series0`。检查横向条形图、负数图和外置 label 的最左/最右数据标签，确认没有被裁切；再缩到 375px 宽度复查一次并触发 `chart.resize()`。若页面包含宽表/矩阵表或搜索框：在 375px 宽度下确认左侧 sticky 冻结列总宽不超过视口宽度的 45%、表头无错位白缝；并在搜索框中分别实测输入行关键词和列关键词（直接用 placeholder 里的示例词），确认不会出现全表消失或只剩一行表头。
- **`SKIP_SCREENSHOT_QA` 时跳过整段截图自检**：不要 `browser_take_screenshot`、不要 Read 图片、也不要用截图核对版式；生成并发布后仍必须执行第四步的链接及正文校验。用户配图另走「配图发送」。

## 执行方式（必须遵守）

为避免大量 HTML 代码污染主会话上下文（会导致后续 API 调用 prompt cache miss，严重拖慢响应速度），HTML 文件的生成**必须**委托给 Agent 子进程完成，禁止在主会话中直接 Write HTML 文件。

### 第零步：识图能力门禁（进入本 skill 后立刻做）

进入本 skill 后、整理数据 / 调子 Agent **之前**，必须先跑：

```bash
.venv/bin/python .claude/skills/html-generator/scripts/ensure_vision.py
```

| stdout 首行 | 含义 | 你要做什么 |
|---|---|---|
| `VISION_OK` | 当前模型支持识图 | 继续后面的步骤，发布前做截图自检 |
| `SKIP_SCREENSHOT_QA` | 用户已选择继续用仅文本模型 | 继续生成，但**跳过截图自检** |
| `VOTE_SENT` | 已向用户发出切换模型投票 | **立刻结束本轮**：不要写 HTML、不要调子 Agent、不要再说"等你点哦" |

禁止：没跑脚本就开写页面；`VOTE_SENT` 后还继续生成；`SKIP_SCREENSHOT_QA` 后仍做截图自检。

当前模型是否识图以脚本结果为准（它读 `BAIGE_CURRENT_MODEL` / 系统提示里的「仅文本」标记），不要自己猜。

**第零步只在主会话执行。** 下面第二步的 HTML 子 Agent 不要跑 `ensure_vision.py`，也不要做截图自检。

### 步骤

**第一步：准备结构化数据**

在主会话中，将当前分析结论整理为完整的、自包含的结构化摘要，包含：
- 页面标题、副标题（可选）、描述（可选）
- 所有图表需要的原始数据点（查询的SQL、趋势数组、对比数据、分布数据等，直接给出数值）
- 所有互联网搜索的网页需要提供具体URL（非搜索引擎的搜索URL）
- 关键指标卡片的数值和状态（正常/异常/警告）
- 分析结论和建议的完整文字

**关键：数据必须自包含。** 不能写"参考上文"、"根据之前的分析"等——子进程看不到主会话的任何上下文。所有数据必须在 prompt 中显式给出。

**第二步：调用 Agent 生成本地 HTML 副本**

使用 Agent 工具，将数据和指令传给子进程：

```
Agent({
  description: "生成HTML可视化页面",
  prompt: "你是一个专业的 HTML 可视化页面生成专家。\n\n请先读取设计规范文件获取配色、布局、图表配置等要求：\nRead /home/powerop/work/baige-ai-assistant/.claude/skills/html-generator/SKILL.md\n\n你只负责写 HTML：不要跑 ensure_vision.py，不要截图自检，不要发布。\n\n然后根据以下数据生成一个精美的可视化分析页面。\n\n## 页面信息\n标题: {标题}\n\n## 数据\n{完整的结构化数据，JSON 或 Markdown 格式}\n\n## 分析结论\n{结论文字}\n\n## 输出要求\n- 先执行 mkdir -p /home/powerop/work/baige-ai-assistant/ui/generated/{YYYYMM}\n- 将 HTML 保存到 /home/powerop/work/baige-ai-assistant/ui/generated/{YYYYMM}/{文件名}.html\n- 文件命名: {主题}_{YYYYMMDD_HHmmss}.html，只用英文字母、数字、下划线\n- 完成后只回复保存的文件路径，不要回复其他任何内容"
})
```

**第三步：发布到 GitLab Pages**

主会话拿到本地副本路径后，用 `publish_to_pages.py` 把页面发布到公网（这一步在主会话执行，因为只是一行命令，不会污染上下文）：

```bash
.venv/bin/python .claude/skills/html-generator/scripts/publish_to_pages.py \
  --src-html <子 agent 返回的本地 HTML 绝对路径> \
  --topic <短主题，比如 order-analysis> \
  --user-id <当前发送者 user-id，默认 hua.chen>
```

`<user-id>` 的取值规则：
- 看消息头 `[发送者: ... 邮箱=xxx@trip.com]`，取 `@` 前的邮箱前缀作为 user-id
- 邮箱里的下划线（如 `hua_chen`）映射成点号（`hua.chen`）
- 找不到邮箱时回退到 `unknown`

`--topic` 用短横线分隔的英文小写（如 `order-analysis`、`pv-trend`），用于生成目录名 `<YYYYMMDD>-<topic>`。

脚本输出的最后一行就是公网 URL（成功时 stdout 仅一行；失败 stderr 给原因，且 exit code 非 0）。

执行时必须把 stdout、stderr 分别保存到本次任务独立的临时目录，并记录发布脚本自身的退出码；不得用 `| tail -1` 等管道掩盖失败。只有退出码为 0 且 stdout 为单行完整 HTTP(S) URL 时，才将该行保存为本次报告的权威 URL（仅去除行尾换行，不修改 URL）。git push 成功只代表提交完成，不代表页面已部署、可访问。

**第四步：回复用户**

将本次 `publish_to_pages.py` 成功返回的完整 URL，原样放入最终回复的 Markdown 链接中。

必须遵守：

- 报告链接的唯一来源是本次发布脚本的实际返回值。
- 禁止根据 Pages 根地址、用户目录、日期、topic、历史回复或记忆重新拼接地址。
- 禁止修改返回 URL 的任何字符，包括协议、域名、路径、查询参数和末尾斜杠；只允许修改链接标题。
- 目录重名时脚本可能自动添加序号，必须保留返回的实际路径。
- 最终回复、进度消息及后续补发链接均原样复用同一个 URL；截图、上传配图、整理结论后也不得重新拼写。
- 发送任何报告链接前，必须执行下面的工具校验；不得仅凭肉眼比对或口头声明“已检查”。

**交付前强校验（主会话执行，全部通过才可交付）**

1. **先固定待发送正文**：完成结论整理、截图及配图后，将完整最终回复保存为本次任务的临时草稿。用 Bash/Python 从保存的发布 stdout 读取 URL，并据此生成草稿中的 Markdown 链接，禁止手工重输地址。临时文件仅用于本次交付，不修改发布脚本或宿主代码。
2. **机器比对实际链接**：用 Bash/Python 从这份草稿提取报告链接目标，与保存的权威 URL 做逐字相等断言；有多处报告链接时逐一检查。比较对象必须是待发送正文里的链接，不能拿两个自行填写的 URL 或同一个变量互相比对。任一不一致，先重新生成链接并重跑校验，禁止发送该草稿。
3. **访问待发送地址**：对上一步从草稿提取的完整 URL 发起真实 GET（可用 `curl -L` 或浏览器），记录请求 URL、最终响应 URL、HTTP 状态码和响应正文。单次请求最多 15 秒、最多跟随 5 次重定向；不能只做 HEAD、检查域名首页或打开本地 HTML。请求失败、超时、404、5xx 均不通过；重定向后的 200 也须继续核对内容，且不能自行用重定向地址替换脚本返回值。
4. **确认确实是本次报告**：最终响应必须为 HTTP 200；读取实际响应正文/页面 DOM，核对本地 HTML 中的报告标题及至少一项本次报告特有的内容（例如统计时间范围和关键指标值）。仅找到 `<html>`、通用页面标题或图表容器不算通过；登录页、代理报错页、空白页、其他报告及旧版本内容均不通过。`SKIP_SCREENSHOT_QA` 只跳过截图识图，不能跳过 GET 和文本内容校验。
5. **依据结果交付**：工具记录中必须具备“链接完全一致、HTTP 200、标题及内容匹配”三项证据，才能回复报告已生成并提供入口。发送时原样复用已校验草稿，不重新拼写链接；若之后修改正文里的报告链接，必须重新执行第 2～4 项。进度消息在校验完成前只说明正在发布/验证，不提前发送报告入口。

**重要：发布或校验失败的兜底**

- 发布脚本非 0 退出码：报告“发布失败”，附脱敏后的 stderr 摘要，不把残留 stdout 当作成功 URL。
- 发布脚本成功但访问校验未通过：报告“已提交发布，但链接访问验证未通过”，说明实际 HTTP 状态或网络/权限错误，不能宣称“页面可正常访问”。对于可能的部署延迟（404/5xx），只对同一 URL 每隔 10 秒重试，含首次请求最多 3 次；不为重试访问而重复发布、换目录或猜另一个地址。不得无依据承诺“30 秒后可访问”。
- 无法执行工具校验或无法读取正文：明确说“链接尚未完成验证”，不伪造“返回 200 / 标题正常”等结果。暂不将未通过校验的地址作为可用报告入口交付，保留发布原始输出供排查。
- 需要内部预览兜底时，只能用真实本地副本路径对应的 `{{sys_base_url}}/generated/{YYYYMM}/{filename}`，也须实际 GET 并核对标题与内容，通过后才提供；明确标注“内部预览，需相应网络访问条件”。若内部预览也无法验证，则仅说明文件已生成和当前阻塞原因，不继续发送未经验证的链接。

**用户反馈旧链接打不开时**：先找回对应报告那次发布的原始工具输出，将旧回复中的链接与其比较，再对准备补发的实际链接执行上述校验。找不到原始输出时，明确缺少发布证据，先查发布记录；不能根据标题、日期或残缺路径猜地址，也不能默认重新生成/发布报告。只根据工具证据说明是链接不一致、HTTP 错误还是当前网络无法验证，不臆测“复制串行”等内部原因。

### 子 Agent prompt 关于 vendor 引用的注意事项

子 Agent 生成 HTML 时**默认引用当前助手上下文中的 pages 公网 vendor**（即 `<script src="{{GitLab Pages 根地址}}/static/vendor/echarts.min.js">`）——pages 公网可达，playwright 截图能跑通，本地浏览器能直接打开，发布到 pages 仓库时 `publish_to_pages.py` 会自动重写成相对路径 `../../static/vendor/xxx`。

**禁止**写 `{SYS_BASE_URL}/static/vendor/...` 或 `http://port8038.<container>.gps.cloud.ctripcorp.com/static/vendor/...`：这种 K8s 集群内域名 playwright 沙箱走不通，截图直接拿到空白图。**子 Agent 不需要也不应该自己处理 publish 转换**。

## AI 配图（可选）

报告需要装饰类配图（封面插画、空状态插图、概念示意图等纯装饰性图片）时，可以调用 `image-generator` skill 生成。**只在用户明确要求或场景确实合适时才用**——单张图要 30s-4min，乱配反而拖慢出稿。数据图表、真实事物展示**永远**走 ECharts / playwright 截图 / 用户素材，不要拿 AI 图代替。

## 配图发送（截图 + 飞书内联）

当用户希望"在消息里直接看到图"、"截图发我"、或者你判断关键图表/数据视图配图能显著提升表达力时，按以下流程把页面截图嵌入飞书消息正文。

`SKIP_SCREENSHOT_QA` 或当前模型标记「仅文本」：截图后**不要 Read** 图片文件（自己识图会 400 中断整轮），直接 `upload_image.py` 发给用户。仅跳过截图识图自检，链接及正文校验仍必须执行；不要为了自己看页面再截图。

### 何时配图

主动判断配图：
- 用户明说"截图"、"配图"、"发图"、"贴图"
- 你生成了关键图表（趋势对比、热力图、看板）想跟着结论一起呈现
- 长报告里某个核心结论用一张图比文字解释更直观

不配图：
- 用户只想要链接 / 数据原文
- 报告内容偏纯文本（结论、SQL、列表），截图反而冗余

### 工作流

**1. 用 mcp__playwright 截整页**

页面已经保存到 `ui/generated/...`，访问 URL 已知：

```
mcp__playwright__browser_navigate({ url: "<生成的 URL>" })
mcp__playwright__browser_resize({ width: 1280, height: 800 })  // 推荐尺寸
mcp__playwright__browser_take_screenshot({
  type: "png",
  fullPage: true,
  filename: "tmp/playwright/<语义化文件名>.png"  // ⚠️ 必须带 tmp/playwright/ 前缀
})
```

⚠️ **`filename` 务必带 `tmp/playwright/` 前缀**——只传纯文件名时 playwright 会落到 cwd（仓库根目录），污染 git 工作区。`tmp/playwright/` 已加入 .gitignore，工具返回里会给出绝对路径，直接传给下一步 `upload_image.py --path` 即可。

`fullPage: true` 截整张页面（含滚动区），适合长报告；想要首屏摘要图就 `fullPage: false`。

**2. 上传到飞书拿 image_key**

**单张图**：

```bash
.venv/bin/python .claude/skills/html-generator/scripts/upload_image.py \
  --path <截图绝对路径>
# stdout： image_key: img_v3_xxxx_yyyyyyy
# stderr： deleted local file: <截图路径>
```

**多张图（强烈推荐用 batch，并发上传，10 张 ~3s）**：

```bash
.venv/bin/python .claude/skills/html-generator/scripts/upload_images_batch.py \
  --paths tmp/playwright/slide_0.png tmp/playwright/slide_1.png tmp/playwright/slide_2.png \
  [--concurrency 6] [--keep]
# stdout 每行： <path>\t<image_key>，顺序与 --paths 一致
# 失败行去 stderr： FAIL\t<path>\t<error>
# 任一失败 → exit 1，但其它图照常完成
```

约束：≤10 MiB / 张，jpg/png/gif/bmp/webp。

**重试**：底层 `upload_image` 已经做了**指数退避 + 抖动**重试（rate limit / 5xx / 网络抖动最多重试 4 次），caller 不需要再加重试逻辑。**只有文件本身不合规**（路径错、超 10 MiB、格式非法）才会立即抛出，不重试——这种情况修文件就行。

**默认上传成功后会自动删除本地文件**——不再手工 `rm`，避免漏删污染仓库。失败的文件会**保留**，stderr 打印路径方便 debug。极少数场景需要保留（同一张图多次复用、debug）才传 `--keep`。

**3. 在最终回复正文里内联引用**

飞书卡片 markdown 元素**直接支持** `![alt](image_key)` 语法（注意是 image_key 不是 URL）。**自然嵌进叙述里**，不要堆在末尾：

```markdown
昨天 PV 总量 9563.67 万，频道 A（101）和频道 B（105）合计占比 40.86%，仍是两大流量支柱。

![场景PV占比](img_v3_xxxx_yyyyyyy)

广告位（154+155+999）合计 11.94%，体量稳定…
```

多图就在不同段落各 `![](key)` 一次。

### 注意

- 截图前先确认 HTML 已经渲染完成（图表 echarts 异步加载，必要时 `browser_wait_for({ time: 2 })`）
- `split_long_text` 已对 `![](key)` 做不可分割保护，长文里图片不会被切到一半
- 截图用 PNG，质量好一点，10 MiB 以内随便用
