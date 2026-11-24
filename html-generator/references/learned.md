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
