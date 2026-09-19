# ❄ 冷链装箱温控规划器

一个可使用 **Docker Compose** 一键启动的 Web 应用：录入货物批次、箱体容量、运输时长与允许温区后，
系统按 **温区兼容性** 与 **容量约束** 自动生成分箱方案，展示每箱温度区间、装载明细以及
未能装载货物的冲突原因。支持 **分段运输温区校验**：按顺序维护各运输段的名称、时长与可用温区，
规划时对箱内货物的共同允许温度 **逐段检查**，报告首次不兼容的运输段、受影响批次与原因，
只有全程通过才标记为可运输。支持 **累计热暴露预算**：每批货物可填写首选温度区间与
最大度时预算（℃·h），允许温区仍作为硬边界，规划器为每个箱子 **逐段选取设定点**，
使箱内最大累计预算使用率最低；任何货物累计超预算则该装箱组合不可用，
页面与接口同步展示各段设定点、每批累计暴露量、剩余预算与首次超限段。
支持在页面上随时修改输入并重新规划。

- 后端：FastAPI（规划算法见 `app/planner.py`，无外部数据库依赖）
- 前端：原生 HTML / CSS / JavaScript（无 CDN 依赖，离线可用）
- 部署：Docker Compose

## 一、启动命令

### 方式 A：Docker Compose（推荐）

```bash
cd /workspace
docker compose up -d --build
```

查看日志 / 停止：

```bash
docker compose logs -f
docker compose down
```

### 方式 B：本地 Python 运行（Python 3.11+）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 二、访问地址与端口

| 内容 | 地址 |
| --- | --- |
| 规划器页面 | <http://localhost:8000/> |
| 健康检查 | <http://localhost:8000/api/health> |
| 规划接口 | `POST http://localhost:8000/api/plan` |
| Swagger 接口文档 | <http://localhost:8000/docs> |

## 三、配置

端口通过环境变量 `APP_PORT` 修改（默认 `8000`）：

```bash
# 方式 1：复制示例配置后修改
cp .env.example .env
#   .env 内容:APP_PORT=9000

# 方式 2：启动时临时指定
APP_PORT=9000 docker compose up -d --build
```

随后访问 <http://localhost:9000/>。

## 四、使用说明

1. 填写 **运输时长**、**单箱容量**、**最大箱数**、**体积单位**。
2. 选择温区维护方式（二选一）：
   - **单一温区（默认）**：在 **允许温区** 中维护全程可用的温区（名称 + 上下限，℃）；
   - **分段运输**：勾选「启用分段运输」后，按执行顺序维护 **运输段**
     （段名称 + 时长 h + 该段可用温区），总运输时长自动按各段时长求和，
     「运输时长」输入框随之禁用。
3. 在 **货物批次** 中录入每批货物：件数、单件体积、允许温度区间，
   以及可选的「最长运输时长」（留空表示不限）；
   如需启用 **累计热暴露预算**，再填写 **首选温度区间**（上下限成对、
   需落在允许温区内）与 **度时预算**（℃·h，留空或 0 表示不启用）。
4. 点击 **「▶ 生成分箱方案」**：
   - 每箱展示 **可设定温度区间**（可能含多个不相连温度段）、**推荐设定温度**、
     匹配温区、容量利用率与装载明细（批次、件数、占用体积）；
   - 分段模式下每箱额外展示 **逐段校验表**（每段的可设定温度、推荐设定点、
     匹配温区），全部通过才标记 **「✓ 全程可运输」**；
   - 箱内有填写首选温度区间的批次时，展示 **热暴露预算表**：每批的
     累计暴露量、度时预算、剩余预算、使用率与状态；启用预算的箱子，
     各段设定点按「最大累计预算使用率最低」自动选取；
   - 未能装载的货物会在下方红色区域列出 **具体冲突原因**；分段不兼容时
     附带 **首次不兼容的运输段** 徽章（第几段 · 段名），度时预算不足时
     附带 **首次超限段** 徽章。
5. 直接在页面修改任意输入后再次点击按钮即可重新规划；点击 **「载入示例」**
   可快速体验分段运输与热暴露预算（示例包含首段不兼容、末段不兼容、
   运输超时、度时预算不足等多种冲突）。

## 五、规划规则

- 货物允许温区必须与至少一个可用温区有交集，否则判定为 **温区不兼容**；
- 同一箱内所有货物的允许温区交集，且交集必须仍落在某个可用温区内；
- **分段运输**：箱内货物的共同允许温度必须在 **每一个运输段** 都能被该段
  某个温区覆盖；任一环节不满足即整批不可运输，并报告 **首次不兼容的运输段、
  受影响批次与原因**；只有全程通过才标记为可运输；
- 分段模式下总运输时长 = 各段时长之和；若同时显式填写运输时长且与段时长
  之和不一致，接口返回 400 提示；
- 同一批货物允许以 **件** 为最小单位拆分到多个箱子；
- 装箱采用 First-Fit-Decreasing 启发式：温度下限越低（要求越苛刻）的批次优先，
  同温限按总体积降序，依次尝试已有箱子，放不下再开新箱；
- 运输时长超过货物「最长运输时长」时，该批整批不予装载并给出原因；
- **累计热暴露预算**（货物填写首选温度区间 + 度时预算后启用）：
  - 允许温区仍是硬边界：每段设定点必须落在「箱内货物共同允许温区 ∩
    该段某可用温区」内；
  - 单段暴露量 = 段时长 × 设定点到该批首选温度区间的距离（℃·h），
    全程逐段累计；
  - 每段设定点从「该段可行区间端点 + 箱内各批首选区间端点」中选取，
    使本段结束后箱内 **最大累计预算使用率** 最低，平局取较低温度；
  - 任何货物累计暴露超过其度时预算，该装箱组合不可用：装货时即拒绝
    形成该组合；若某批即使独占一箱（可行温区最宽）也必然超限，则整批
    不予装载，并报告 **首次超限段** 与届时累计暴露量；
  - 未填写预算的批次保持原规则（设定点取最宽可行区间中点），
    填写了首选区间但未填预算的批次只统计暴露量、不参与约束；
- 达到最大箱数或单件体积超过单箱容量时，剩余货物按冲突输出。

## 六、接口示例

### 单一温区模式（兼容原有调用）

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{
    "transport_hours": 24,
    "box_capacity": 12,
    "max_boxes": 20,
    "volume_unit": "m³",
    "zones": [{"name": "冷藏区", "t_min": 0, "t_max": 8}],
    "cargoes": [{"name": "鲜奶", "units": 40, "unit_volume": 0.25,
                 "t_min": 2, "t_max": 6}]
  }'
```

### 分段运输模式

提供 `segments`（非空）即启用分段校验；`transport_hours` 可省略，
默认取各段时长之和（若显式填写则必须与段时长之和一致）：

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{
    "box_capacity": 12,
    "segments": [
      {"name": "干线冷链", "hours": 14,
       "zones": [{"name": "冷冻区", "t_min": -18, "t_max": -2},
                 {"name": "冷藏区", "t_min": 0, "t_max": 8}]},
      {"name": "末端配送", "hours": 4,
       "zones": [{"name": "冷藏区", "t_min": 0, "t_max": 8},
                 {"name": "常温区", "t_min": 15, "t_max": 25}]}
    ],
    "cargoes": [
      {"name": "三文鱼", "units": 10, "unit_volume": 0.4, "t_min": -2, "t_max": 2},
      {"name": "冷冻牛排", "units": 5, "unit_volume": 0.8, "t_min": -22, "t_max": -15}
    ]
  }'
```

### 累计热暴露预算

货物批次可选填 `preferred_t_min` / `preferred_t_max`（首选温度区间，需落在
允许温区内）与 `max_degree_hours`（最大度时预算，℃·h）；填写预算后
规划器逐段优化设定点并校验累计暴露：

```bash
curl -X POST http://localhost:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{
    "box_capacity": 12,
    "segments": [
      {"name": "干线冷链", "hours": 14,
       "zones": [{"name": "冷冻区", "t_min": -18, "t_max": -2},
                 {"name": "冷藏区", "t_min": 0, "t_max": 8}]},
      {"name": "末端配送", "hours": 4,
       "zones": [{"name": "冷藏区", "t_min": 0, "t_max": 8},
                 {"name": "常温区", "t_min": 15, "t_max": 25}]}
    ],
    "cargoes": [
      {"name": "三文鱼", "units": 10, "unit_volume": 0.4,
       "t_min": -2, "t_max": 2,
       "preferred_t_min": -1, "preferred_t_max": 1, "max_degree_hours": 30},
      {"name": "鲜奶", "units": 20, "unit_volume": 0.25,
       "t_min": 2, "t_max": 6,
       "preferred_t_min": 2, "preferred_t_max": 3, "max_degree_hours": 30}
    ]
  }'
```

两批同箱时共同允许温度被收窄为 `[2, 2]`℃，各段设定点只能取 2℃，
三文鱼每段暴露 `段时长 × |2 - 1|`，全程累计 18 ℃·h（预算 30，剩余 12）。
响应中每箱附带 `exposure` 块，示例（节选）：

```json
{
  "exposure": {
    "setpoint_strategy": "budget_optimal",
    "all_within_budget": true,
    "items": [
      {"batch_no": 1, "name": "三文鱼",
       "preferred_t_min": -1.0, "preferred_t_max": 1.0,
       "cumulative_degree_hours": 18.0, "budget_degree_hours": 30.0,
       "remaining_degree_hours": 12.0, "utilization": 0.6,
       "first_exceeded_segment_no": null, "first_exceeded_segment_name": null}
    ]
  }
}
```

若某批即使独占一箱也必然超预算，则整批不予装载体现在 `unloaded` 中
（下例摘自页面「载入示例」数据的响应）：

```json
{
  "batch_no": 3,
  "name": "冰鲜金枪鱼",
  "units": 8,
  "volume": 2.4,
  "reason": "按逐段最优设定点,该批在运输段「支线转运」(第 2 段,6.0h)后累计热暴露 10.0 ℃·h 超过度时预算 9.0 ℃·h;即使独占一箱(可行温区最宽)仍超限,任何装箱组合均不可用",
  "first_exceeded_segment_no": 2,
  "first_exceeded_segment_name": "支线转运"
}
```

### 响应字段（新增部分）

| 字段 | 说明 |
| --- | --- |
| `summary.segment_mode` | 是否分段运输模式 |
| `summary.transport_hours` | 总运输时长（分段模式为各段时长之和） |
| `summary.all_transportable` | 全部装载且每箱全程逐段通过才为 `true` |
| `summary.heat_budget_enabled` | 是否存在填写了度时预算的货物批次 |
| `segments[]` | 回显规范化后的运输段（序号 / 名称 / 时长 / 温区） |
| `boxes[].transportable` | 该箱是否全程逐段通过温区校验 |
| `boxes[].segment_checks[]` | 逐段校验结果：`ok`、该段可设定温度段、设定点 `recommended_setpoint`（启用预算的箱子按最大累计预算使用率最低选取）、匹配温区，失败时附 `reason` |
| `boxes[].exposure` | 热暴露结果；箱内无填写首选温度区间的批次时为 `null` |
| `boxes[].exposure.setpoint_strategy` | 设定点策略：`budget_optimal`（按预算最优）/ `midpoint`（区间中点） |
| `boxes[].exposure.all_within_budget` | 箱内所有预算批次是否全程未超限 |
| `boxes[].exposure.items[]` | 每批（填写首选区间者）的累计暴露量 `cumulative_degree_hours`、预算 `budget_degree_hours`、剩余预算 `remaining_degree_hours`、使用率 `utilization` 及首次超限段 `first_exceeded_segment_no` / `first_exceeded_segment_name`（未超限为 `null`） |
| `unloaded[].failed_segment_no` / `failed_segment_name` | 首次不兼容的运输段序号与名称（仅分段温度冲突时出现），`reason` 中含完整原因 |
| `unloaded[].first_exceeded_segment_no` / `first_exceeded_segment_name` | 首次超过度时预算的运输段序号与名称（仅预算不足整批拒载时出现） |

货物批次请求字段（均为可选）：`preferred_t_min` / `preferred_t_max`
首选温度区间（需成对填写且落在允许温区内）、`max_degree_hours`
最大度时预算 ℃·h（需先填写首选区间，留空或 0 表示不启用）。

分段模式下，上面的「冷冻牛排」会因末端配送段无冷冻温区而整批不可运输，
响应中 `unloaded` 对应条目示例：

```json
{
  "batch_no": 2,
  "name": "冷冻牛排",
  "units": 5,
  "volume": 4.0,
  "reason": "运输段「末端配送」(第 2 段,4.0h)的可用温区 (冷藏区、常温区) 与允许温区 [-22.0, -15.0]℃ 均无交集,全程温度无法保证",
  "failed_segment_no": 2,
  "failed_segment_name": "末端配送"
}
```

## 七、项目结构

```
.
├── app/
│   ├── main.py        # FastAPI 入口与静态资源挂载
│   ├── planner.py     # 温区兼容 + 容量约束 + 热暴露预算分箱算法
│   └── schemas.py     # 请求模型
├── static/
│   ├── index.html     # 单页前端
│   ├── styles.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```
