# html-generator 踩坑记录

## 2026-08-05 · 本地 vendor 里的 echarts.min.js 中段损坏

**症状**：pages 上生成的可视化页面所有 `echarts.init(...)` 图表容器空白（KPI/文字/emoji 都正常，就是 canvas 一个不出）。浏览器控制台没有明显的加载错误，`typeof echarts === 'undefined'`。

**排查**：
1. curl 拉 `pages.release.ctripcorp.com/qiuyuli/ttd-super-assisstant/static/vendor/echarts.min.js` 返回 200，Content-Length 正常，UMD wrapper 头也在（`!function(t,e){"object"==typeof exports&&...})(this,(function(t){"use strict";...})`）
2. 但 `echarts.min.js` 加载完执行后 `window.echarts` / `globalThis.echarts` 都是 undefined —— 说明脚本执行过程中出错了
3. 拉 jsdelivr 的 5.4.3 干净版 md5 对比：
   - 本地/pages vendor：`f644de40893e1d72850b5651576fdfd2`
   - jsdelivr CDN：`38588d6b8c7c30b9941c28c01b389b88`
   - **大小完全相同（1024740 bytes）**，但从**字节 172032 开始**内容不同
4. 推测是某次编辑器/传输过程把中段代码换错了（大小碰巧一致，内容替换成了另一段），静默污染

**修复**：从 `https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js` 下载覆盖 `ui/static/vendor/echarts.min.js` 和 `public/static/vendor/echarts.min.js`，两处都要同步。

**预防**：
- vendor 目录里的第三方脚本应该保持只读 / 校验 md5，不要用编辑器打开（可能有静默编码转换）
- 新增或更新 vendor 时应该记录官方 md5，定期校验
- pages 发布脚本的 vendor URL 重写走的是 `../../static/vendor/xxx`，本地 `ui/static/vendor/` 是真北源头，`public/static/vendor/` 是 pages 部署副本，两处要保持一致

**兜底方案**：如果本地 vendor 又坏了，先在 HTML 里改成 `https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js` 让页面能用，再单独修 vendor。

## 2026-11-05 · 大尺寸矩阵表（table/matrix）在手机端「只显示一行表头」及搜索即空表

**症状**：生成的 `cruise_ship_locale_matrix_v3_20261105.html`（75 家船司 × 43 个售卖站点矩阵表）在手机端飞书内打开时，偶发出现表格区域只有表头一行（`# | [白缝] | 船司 | 采购类型`），表体、底部图例和页脚全部缺失；且在搜索框输入 placeholder 给出的示例词（如 `公主` 或 `en-US`）时，表格要么整表消失，要么只剩一行表头。

**根因排查**：
1. **383 KB 单行 `<tbody>` 导致移动端弱网半截渲染**：75 × 43 = 3,225 个单元格全部硬编码展开为带 `title`、`style="background:rgba(...)"`、双 `<span>` 的 HTML，压在第 62 行单行 383 KB（整页 395 KB），而 `port8038` 容器未开启 gzip。手机弱网下收到前 10.5 KB（第 1～61 行，刚好到 `</thead><tbody>`）后先渲染出顶部卡片和表头，卡在第 62 行传输途中时，页面就只有一行表头且下方没有 `.legend` 和 `.foot`。
2. **`<th class="idx">` 与 `td.idx` 选择器不匹配产生表头白缝**：表头第一格写的是 `<th class="idx">#</th>`，而 CSS 写的是 `td.idx { width: 36px; min-width: 36px; left: 0; }`。当 `<tbody>` 尚未加载或被筛选为空时，`<th class="idx">` 没有 36px 宽度约束（自然宽仅约 20px），而第二列 `.rowhead` 被 `left: 36px` 固定在 36px 处，中间 20px～36px 就会露出 `.tablebox` 的白色背景形成一道竖向白缝。同时 `<thead>` 里把「采购类型」「合计」写成了 `<td>`，纵向滚动时不会随 `thead th` 吸顶。
3. **左侧 4 列全部 sticky（总宽 448px）超出手机屏宽**：`#`(36px) + `船司`(150px) + `采购类型`(206px) + `合计`(56px) = 448px 全部设了 `position: sticky`，而手机端 `.tablebox` 宽仅约 335px，冻结列比容器还宽，导致窄屏下右侧站点列无法正常横向滚动查看。
4. **行列双向搜索的「AND 交集死锁」**：`oninput` 同时用输入词过滤 `headCells`（`colHit`）和 `tbody tr`（`rowHit`），且未豁免前 4 列。输入船司名 `公主` 时没有任何列头含 `公主`（`colHit` 全 false，所有单元格被 `display: none`）；输入站点名 `en-US` 时没有任何船司行含 `en-US`（`rowHit` 全 false，所有数据行被 `display: none`，只剩一行表头）。

**修复与预防（已沉淀至 `SKILL.md`「数据表格与大宽表硬约束」）**：
- 单元格 > 500 的矩阵表用紧凑 JSON 数组 + 同步 `<script>` 渲染 `<tbody>`，把 395 KB 压到 ~34 KB；
- `<thead>` 统一用 `<th>`，固定列选择器统一用 `.idx` / `.rowhead` / `.rtype` / `.total`；
- `@media (max-width: 768px)` 下只保留前 1～2 列（总宽 ≤ 160px）横向 `sticky`，其余列在移动端释放为横向可滚；
- 行列双向搜索必须固定保留左侧信息列（`i < 4`），并按词元分别判定是筛行还是筛列，实测 placeholder 中的所有示例词。

## 2026-11-24 · 看板页面手机端柱状图类目溢出屏幕、明细表右侧被硬切

**症状**：生成的「国内门票质量缺陷 GMV 与毛利」看板（环形图 + 双轴分组柱状图 + 明细表）在 PC 端 1280px 下完全正常；手机端（飞书内置浏览器，视口约 375px）打开时：分组柱状图 5 个类目（AI点评/投诉/订单/事件/NPS）只有左侧约 2 个可见，右侧被推出屏幕外；底部明细表右侧列被屏幕硬切；页面标题被折叠成省略号；图例勉强换行、字号明显偏小。环形图卡片本身基本正常，说明 viewport meta 与单列堆叠大概率是生效的，问题出在个别超宽元素。

**根因（实测修正版，2026-11-24 复盘原始会话日志 + 真实页面 375px 实测；推翻最初按截图猜测的「画布溢出」结论）**：
1. **柱状图 X 轴标签 `axisLabel.interval: 'auto'` + `rotate: 0`（直接真凶）**：375px 下 ECharts 自动抽稀标签，5 个类目只显示「AI点评、事件」2 个。手机截图看着像「画布溢出屏幕」，实测画布 295px 完全在视口内——是标签被隐藏，不是柱子被裁。约束 6（窄屏 `interval: 0, rotate: 45`）与自检断言 (b)（类目一个不能少）精确命中。
2. **QA 层跳过 375px 实测（逃逸主因）**：整份会话 0 次 resize 到 375px；主会话用 `grep -c '@media'` 的「断点存在性检查」当成响应式通过的代理证据直接发布（1280px 自检本身执行得很认真，还修了图例颜色与标签裁切）。已补「必跑 + 禁止代理检查 + 四断言」。
3. 次要：369px 视口下 `scrollWidth=380`（11px 轻微横向溢出，断言 (a) 可拦）；只挂 `window.resize` 无 `ResizeObserver`（本案未直接致错，隐患，约束 5 覆盖）。
4. **症状误读修正**：明细表其实包了 `.table-wrap { overflow-x: auto }` 正常内滚（307px 容器内滚 640px 内容）；断点单列、卡片无 min-width、表格滚动容器这些 v6 都做对了——约束 1-4 属预防性固化，不是本案根因。

**修复与预防（已沉淀至 `SKILL.md`「移动端窄屏适配硬约束」）**：
- 页面容器/卡片/图表容器禁止固定与最小像素宽，限宽只用 `max-width`；grid/flex 子项一律 `min-width: 0`；
- `@media (max-width: 768px)` 多列布局塌陷为单列；
- 宽表一律包 `.table-wrap { overflow-x: auto }`，最小宽度写在 `table` 上而非页面容器上；
- ECharts 除 `window.resize` 外必须挂 `ResizeObserver`（debounce 后 `chart.resize()`），init 不传固定宽；
- 375px 自检升级为四条硬断言（无横向溢出 / 全部类目可见 / 表格内部可滚 / 标题不截断），任一不过禁止发布。

**排查手机端横向溢出元凶的快捷 JS**（375px devtools 或手机浏览器控制台执行）：

```js
[...document.querySelectorAll('body *')]
  .filter(el => el.getBoundingClientRect().right > innerWidth + 2)
  .slice(0, 8)
  .map(el => el.tagName + '.' + String(el.className).trim().replace(/\s+/g, '.') + ' right=' + Math.round(el.getBoundingClientRect().right))
```

**取证与复盘姿势（本次实测验证过）**：
- 服务器会话日志：skill-admin 会话详情页右上「下载会话日志」→ json（含 models / skills_summary（可看 skill 版本号）/ 全量消息与工具调用；不含子代理独立记录，截图是需登录的后台链接）。
- 真实页面 375px 复测（比截图识图可靠）：登录后的页面里注入同源 iframe —— `f.src=location.href; f.style.width='375px'`，再量 `f.contentDocument.documentElement.scrollWidth` vs `f.contentWindow.innerWidth`、`.chart-box`/canvas 宽度、`.table-wrap` 是否内滚；读 ECharts 配置用 `echarts.getInstanceByDom(document.querySelector('.chart-box')).getOption()`（实例挂在 `.chart-box` 容器上，不是 canvas 的直接父层）。
- 原始会话实锤：`338d1cc2-717-4184-96af-7791e50b7e26`（服务器 skill `html-generator v6`，主模型 `kr-claude-opus-5.5`，VISION_OK，发布地址 `https://super.ctrip-it.com/dc485b3d32e663e581099a7746f1b58e/`）。
