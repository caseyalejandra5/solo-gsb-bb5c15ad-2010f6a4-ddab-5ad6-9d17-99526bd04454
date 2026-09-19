"""冷链装箱温控规划器核心算法。

规则:
- 每个温区是一个闭区间 [t_min, t_max],货物允许温区同理。
- 货物只能装入"允许温区与某个箱体可用温区存在交集"的箱子。
- 箱内可行温度 = 已装入货物允许温区的交集;实际可设定温度还必须落在某个
  温区内,因此最终输出的温度段是 "可行交集 ∩ 各温区" 的合并结果。
- 支持分段运输:按顺序维护若干运输段(名称/时长/可用温区),箱内货物的
  共同允许温度必须在每一段都能被该段某个温区覆盖,否则报告首次不兼容的
  运输段;只有全程通过才标记为可运输。未提供运输段时退化为全程单一温区。
- 累计热暴露预算:货物可额外填写首选温度区间与最大度时预算(℃·h),
  允许温区仍作为硬边界。规划器为每个箱子逐段选取一个同时落在箱内货物
  共同允许温区与该段某可用温区内的设定点;单段暴露量 = 段时长 × 设定点
  到该批首选区间的距离。每段从"该段可行区间端点 + 箱内各批首选区间端点"
  中选取使本段结束后箱内最大累计预算使用率最低的点,平局取较低温度;
  任何货物累计超预算则该装箱组合不可用。未填写预算的批次保持原规则
  (设定点取最宽可行区间中点,不参与预算约束)。
- 同一批货物可按"件"为最小单位拆分到多个箱子。
- 采用 First-Fit-Decreasing 启发式:温度下限越低(要求越苛刻)的批次优先,
  同温限按总体积降序;依次塞入已有箱子,放不下再开新箱。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EPS = 1e-9
# 未装载原因中最多列举几个温区/箱子名称
_DETAIL_LIMIT = 3


def _r(v: float) -> float:
    """规整浮点输出,消除 -0.0 之类误差。"""
    v = round(float(v), 4)
    return 0.0 if abs(v) < 1e-9 else v


@dataclass
class _Iv:
    lo: float
    hi: float

    def intersect(self, other: "_Iv") -> "_Iv | None":
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return _Iv(lo, hi) if lo <= hi + EPS else None


@dataclass
class _Zone:
    name: str
    iv: _Iv


def _dist_to_iv(t: float, iv: _Iv) -> float:
    """温度 t 到闭区间的距离(区间内为 0)。"""
    if t < iv.lo:
        return iv.lo - t
    if t > iv.hi:
        return t - iv.hi
    return 0.0


@dataclass
class _Segment:
    """一个运输段:按顺序执行,段内可使用一组温区。"""

    no: int
    name: str
    hours: float
    zones: list[_Zone]


def _first_failed_segment(segments: list[_Segment], iv: _Iv) -> _Segment | None:
    """返回首个没有任何温区能覆盖 iv 的运输段;全程兼容时返回 None。"""
    for seg in segments:
        if not any(iv.intersect(z.iv) is not None for z in seg.zones):
            return seg
    return None


@dataclass
class _Loaded:
    batch_no: int
    name: str
    units: int
    volume: float


@dataclass
class _Box:
    index: int
    capacity: float
    segments: list[_Segment]
    used: float = 0.0
    items: list[_Loaded] = field(default_factory=list)
    # 已装入货物允许温区的交集;首件货物装入时初始化
    feasible: _Iv | None = None
    # 箱内批次(按批次号去重),用于热暴露模拟
    batch_map: dict[int, "_Batch"] = field(default_factory=dict)

    def try_load(self, batch: "_Batch", iv: _Iv) -> bool:
        """尝试装入 1 件货物,成功则更新箱内温度交集与容量。"""
        if self.used + batch.unit_volume > self.capacity + EPS:
            return False
        new_feasible = iv if self.feasible is None else self.feasible.intersect(iv)
        if new_feasible is None:
            return False
        # 交集后的温度必须在每个运输段都至少能被该段一个温区覆盖
        if _first_failed_segment(self.segments, new_feasible) is not None:
            return False
        # 新批次会收窄可行区间,需重验箱内热暴露预算;同批已在箱内时结论不变
        if batch.no not in self.batch_map and not self._exposure_ok(
            new_feasible, batch
        ):
            return False
        if self.items and self.items[-1].batch_no == batch.no:
            self.items[-1].units += 1
            self.items[-1].volume = _r(self.items[-1].volume + batch.unit_volume)
        else:
            self.items.append(
                _Loaded(
                    batch_no=batch.no,
                    name=batch.name,
                    units=1,
                    volume=batch.unit_volume,
                )
            )
        self.batch_map[batch.no] = batch
        self.used = _r(self.used + batch.unit_volume)
        self.feasible = new_feasible
        return True

    def _exposure_ok(self, feasible: _Iv, extra: "_Batch") -> bool:
        """在箱内加入 extra 批次后,所有含预算批次的累计暴露均不超限。"""
        batches = list(self.batch_map.values())
        if extra.budget is None and all(b.budget is None for b in batches):
            return True
        return _simulate_exposure(self.segments, feasible, [*batches, extra])["ok"]

    def can_take(self, batch: "_Batch", iv: _Iv) -> bool:
        """该箱是否在温区与热暴露预算上能容纳此批货物(不考虑剩余容量)。"""
        candidate = iv if self.feasible is None else self.feasible.intersect(iv)
        if candidate is None or _first_failed_segment(self.segments, candidate) is not None:
            return False
        return batch.no in self.batch_map or self._exposure_ok(candidate, batch)


@dataclass
class _Batch:
    no: int
    name: str
    units: int
    unit_volume: float
    iv: _Iv
    max_hours: float | None
    pref: _Iv | None  # 首选温度区间(可选);暴露量按设定点到该区间距离计量
    budget: float | None  # 最大度时预算 ℃·h(可选,需配合首选区间)
    total_volume: float


def _fmt_names(names: list[str]) -> str:
    head = "、".join(names[:_DETAIL_LIMIT])
    if len(names) > _DETAIL_LIMIT:
        head += f" 等 {len(names)} 项"
    return head


def _merge_segments(segs: list[_Iv]) -> list[_Iv]:
    """合并相交或端点相接的温度段。"""
    segs = sorted(segs, key=lambda s: (s.lo, s.hi))
    merged: list[_Iv] = []
    for s in segs:
        if merged and s.lo <= merged[-1].hi + EPS:
            merged[-1].hi = max(merged[-1].hi, s.hi)
        else:
            merged.append(_Iv(s.lo, s.hi))
    return merged


def _simulate_exposure(
    segments: list[_Segment], feasible: _Iv, batches: list[_Batch]
) -> dict[str, Any]:
    """对给定装箱组合逐段选取设定点并累计各批热暴露。

    每段设定点必须落在 "箱内共同允许温区 ∩ 该段某可用温区" 内;候选点为
    该段各可行区间的端点与箱内各批首选区间端点(落在可行区间内的),逐一
    评估"本段结束后箱内最大累计预算使用率",取最低者,平局取较低温度。
    箱内无任何预算批次时沿用原规则:取最宽可行区间的中点。
    返回各段设定点、各批(填写了首选区间的)累计暴露与首次超限段。
    """
    tracked = [b for b in batches if b.pref is not None]
    budgeted = [b for b in tracked if b.budget is not None]
    cum: dict[int, float] = {b.no: 0.0 for b in tracked}
    # 批次号 -> (首次超限的运输段, 该段结束时的累计暴露)
    first_exceeded: dict[int, tuple[_Segment, float]] = {}
    setpoints: dict[int, float | None] = {}
    for seg in segments:
        merged = _merge_segments(
            [s for z in seg.zones if (s := feasible.intersect(z.iv)) is not None]
        )
        if not merged:
            # 该段温区无可行温度(装载前已逐段预检,此处仅兜底):不累计暴露
            setpoints[seg.no] = None
            continue
        if budgeted:
            candidates: set[float] = set()
            for m in merged:
                candidates.update((m.lo, m.hi))
                for b in tracked:
                    assert b.pref is not None
                    for p in (b.pref.lo, b.pref.hi):
                        if m.lo - EPS <= p <= m.hi + EPS:
                            candidates.add(p)
            best_t: float | None = None
            best_obj = float("inf")
            for t in sorted(candidates):
                obj = max(
                    (cum[b.no] + seg.hours * _dist_to_iv(t, b.pref)) / b.budget
                    for b in budgeted
                )
                # 严格更优才替换:候选按温度升序遍历,平局自然保留较低温度
                if obj < best_obj - EPS:
                    best_obj, best_t = obj, t
            setpoint = best_t
        else:
            widest = max(merged, key=lambda s: s.hi - s.lo)
            setpoint = (widest.lo + widest.hi) / 2
        setpoints[seg.no] = setpoint
        assert setpoint is not None
        for b in tracked:
            assert b.pref is not None
            cum[b.no] += seg.hours * _dist_to_iv(setpoint, b.pref)
            if (
                b.budget is not None
                and cum[b.no] > b.budget + EPS
                and b.no not in first_exceeded
            ):
                first_exceeded[b.no] = (seg, cum[b.no])
    exposures = [
        {
            "batch": b,
            "cumulative": cum[b.no],
            "first_exceeded": first_exceeded[b.no][0] if b.no in first_exceeded else None,
            "exceeded_cumulative": (
                first_exceeded[b.no][1] if b.no in first_exceeded else None
            ),
        }
        for b in tracked
    ]
    return {"ok": not first_exceeded, "setpoints": setpoints, "exposures": exposures}


def _parse_zones(raw_zones: list[dict[str, Any]], ctx: str) -> list[_Zone]:
    """解析温区列表;ctx 为错误消息前缀(如所属运输段)。"""
    zones: list[_Zone] = []
    for i, z in enumerate(raw_zones):
        lo, hi = float(z["t_min"]), float(z["t_max"])
        name = str(z.get("name") or f"温区 {i + 1}")
        if lo > hi + EPS:
            raise ValueError(f"{ctx}温区 {name} 的温度下限高于上限")
        zones.append(_Zone(name=name, iv=_Iv(lo, hi)))
    return zones


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    """根据请求 payload 生成分箱方案;输入不合法时抛 ValueError。"""
    box_capacity = float(payload.get("box_capacity", 0))
    max_boxes = int(payload.get("max_boxes", 100))
    volume_unit = str(payload.get("volume_unit") or "体积单位").strip() or "体积单位"

    if box_capacity <= 0:
        raise ValueError("箱体容量必须大于 0")
    if max_boxes <= 0:
        raise ValueError("最大箱数必须大于 0")

    th_raw = payload.get("transport_hours")
    raw_segments = payload.get("segments") or []
    segment_mode = bool(raw_segments)

    segments: list[_Segment] = []
    if segment_mode:
        # 分段运输:总时长为各段时长之和;显式给的 transport_hours 必须一致
        total_hours = 0.0
        for i, s in enumerate(raw_segments):
            name = str(s.get("name") or f"第 {i + 1} 段").strip() or f"第 {i + 1} 段"
            hours = float(s["hours"])
            if hours <= 0:
                raise ValueError(f"运输段 {name} 的时长必须大于 0")
            zones = _parse_zones(s.get("zones") or [], f"运输段 {name} 的")
            if not zones:
                raise ValueError(f"运输段 {name} 至少需要定义一个可用温区")
            segments.append(_Segment(no=i + 1, name=name, hours=hours, zones=zones))
            total_hours += hours
        total_hours = _r(total_hours)
        if th_raw not in (None, ""):
            th = float(th_raw)
            if th < 0:
                raise ValueError("运输时长不能为负数")
            if abs(th - total_hours) > 1e-6:
                raise ValueError(
                    f"运输时长 {_r(th)}h 与各运输段时长之和 {_r(total_hours)}h "
                    f"不一致,请修正,或留空自动按段时长求和"
                )
        transport_hours = total_hours
    else:
        # 兼容模式:全程单一温区,视为唯一运输段
        transport_hours = 0.0 if th_raw in (None, "") else float(th_raw)
        if transport_hours < 0:
            raise ValueError("运输时长不能为负数")
        zones = _parse_zones(payload.get("zones") or [], "")
        if not zones:
            raise ValueError("至少需要定义一个允许温区")
        segments.append(
            _Segment(no=1, name="全程", hours=transport_hours, zones=zones)
        )

    batches: list[_Batch] = []
    for i, c in enumerate(payload.get("cargoes") or []):
        name = str(c.get("name") or f"批次 {i + 1}")
        lo, hi = float(c["t_min"]), float(c["t_max"])
        if lo > hi + EPS:
            raise ValueError(f"货物 {name} 的允许温度下限高于上限")
        units = int(c["units"])
        unit_volume = float(c["unit_volume"])
        if units <= 0:
            raise ValueError(f"货物 {name} 的件数必须大于 0")
        if unit_volume <= 0:
            raise ValueError(f"货物 {name} 的单件体积必须大于 0")
        mh = c.get("max_transport_hours")
        max_hours = None if mh in (None, "", 0, "0") else float(mh)
        if max_hours is not None and max_hours < 0:
            raise ValueError(f"货物 {name} 的最长运输时长不能为负数")
        # 首选温度区间(可选,上下限需成对填写且落在允许温区内)
        pref_lo_raw, pref_hi_raw = c.get("preferred_t_min"), c.get("preferred_t_max")
        pref_lo = None if pref_lo_raw in (None, "") else float(pref_lo_raw)
        pref_hi = None if pref_hi_raw in (None, "") else float(pref_hi_raw)
        if (pref_lo is None) != (pref_hi is None):
            raise ValueError(f"货物 {name} 的首选温度区间需同时填写下限与上限")
        pref: _Iv | None = None
        if pref_lo is not None and pref_hi is not None:
            if pref_lo > pref_hi + EPS:
                raise ValueError(f"货物 {name} 的首选温度下限高于上限")
            if pref_lo < lo - EPS or pref_hi > hi + EPS:
                raise ValueError(
                    f"货物 {name} 的首选温度区间 [{_r(pref_lo)}, {_r(pref_hi)}]℃ "
                    f"需落在允许温区 [{_r(lo)}, {_r(hi)}]℃ 内"
                )
            pref = _Iv(pref_lo, pref_hi)
        # 最大度时预算(可选,0/留空视为不启用;启用时必须给出首选区间)
        mb = c.get("max_degree_hours")
        budget = None if mb in (None, "", 0, "0") else float(mb)
        if budget is not None:
            if budget < 0:
                raise ValueError(f"货物 {name} 的度时预算不能为负数")
            if pref is None:
                raise ValueError(
                    f"货物 {name} 填写了度时预算,需同时填写首选温度区间"
                )
        batches.append(
            _Batch(
                no=i + 1,
                name=name,
                units=units,
                unit_volume=unit_volume,
                iv=_Iv(lo, hi),
                max_hours=max_hours,
                pref=pref,
                budget=budget,
                total_volume=_r(units * unit_volume),
            )
        )
    if not batches:
        raise ValueError("至少需要录入一批货物")

    boxes: list[_Box] = []
    unloaded: list[dict[str, Any]] = []

    def add_unloaded(batch: _Batch, units: int, reason: str, **extra: Any) -> None:
        unloaded.append(
            {
                "batch_no": batch.no,
                "name": batch.name,
                "units": units,
                "volume": _r(units * batch.unit_volume),
                "reason": reason,
                **extra,
            }
        )

    # 温度下限越低越苛刻,优先装;同温限按总体积降序
    for b in sorted(batches, key=lambda x: (x.iv.lo, -x.total_volume)):
        # 1) 运输时长预检
        if b.max_hours is not None and transport_hours > b.max_hours + EPS:
            add_unloaded(
                b,
                b.units,
                f"运输时长 {_r(transport_hours)}h 超过该批允许的 "
                f"{_r(b.max_hours)}h,全程温度无法保证",
            )
            continue

        # 2) 逐段温区兼容性预检:每一段都必须有温区覆盖该批允许温区
        failed_seg = _first_failed_segment(segments, b.iv)
        if failed_seg is not None:
            if segment_mode:
                add_unloaded(
                    b,
                    b.units,
                    f"运输段「{failed_seg.name}」(第 {failed_seg.no} 段,"
                    f"{_r(failed_seg.hours)}h)的可用温区 "
                    f"({_fmt_names([z.name for z in failed_seg.zones])}) 与允许温区 "
                    f"[{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 均无交集,全程温度无法保证",
                    failed_segment_no=failed_seg.no,
                    failed_segment_name=failed_seg.name,
                )
            else:
                add_unloaded(
                    b,
                    b.units,
                    f"允许温区 [{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 与全部可用温区 "
                    f"({_fmt_names([z.name for z in segments[0].zones])}) 均无交集",
                )
            continue

        # 2.5) 热暴露预算预检:独占一箱(可行区间最宽)仍超预算,则任何组合都不可行
        if b.budget is not None:
            solo = _simulate_exposure(segments, b.iv, [b])
            if not solo["ok"]:
                rec = solo["exposures"][0]
                seg = rec["first_exceeded"]
                add_unloaded(
                    b,
                    b.units,
                    f"按逐段最优设定点,该批在运输段「{seg.name}」(第 {seg.no} 段,"
                    f"{_r(seg.hours)}h)后累计热暴露 {_r(rec['exceeded_cumulative'])} "
                    f"℃·h 超过度时预算 {_r(b.budget)} ℃·h;即使独占一箱"
                    f"(可行温区最宽)仍超限,任何装箱组合均不可用",
                    first_exceeded_segment_no=seg.no,
                    first_exceeded_segment_name=seg.name,
                )
                continue

        # 3) 先尝试已有箱子(First-Fit)
        remaining = b.units
        unusable_boxes = 0
        for box in boxes:
            if remaining == 0:
                break
            if not box.can_take(b, b.iv):
                unusable_boxes += 1
                continue
            while remaining > 0 and box.try_load(b, b.iv):
                remaining -= 1
            if remaining > 0:
                # 温区兼容但本箱容量已不足
                unusable_boxes += 1

        # 4) 开新箱继续装,直到装完或达到上限
        while remaining > 0:
            if len(boxes) >= max_boxes:
                if segment_mode:
                    compatible_note = "逐段温区均兼容"
                else:
                    covering = [
                        z.name
                        for z in segments[0].zones
                        if b.iv.intersect(z.iv) is not None
                    ]
                    compatible_note = f"温区兼容({_fmt_names(covering)})"
                add_unloaded(
                    b,
                    remaining,
                    f"{compatible_note},"
                    f"但已达最大箱数 {max_boxes},现有 {len(boxes)} 个箱子"
                    f"{'温度/热暴露预算不兼容或容量不足' if unusable_boxes else '容量不足'}",
                    tried_boxes=len(boxes),
                )
                break
            if b.unit_volume > box_capacity + EPS:
                add_unloaded(
                    b,
                    remaining,
                    f"单件体积 {_r(b.unit_volume)} {volume_unit} 超过单箱容量 "
                    f"{_r(box_capacity)} {volume_unit},新箱也无法装载",
                    new_box_failed=True,
                )
                break
            box = _Box(index=len(boxes) + 1, capacity=box_capacity, segments=segments)
            if not box.try_load(b, b.iv):
                # 理论上不可达(预检已保证逐段温区兼容且独占一箱不超预算),仅作兜底
                failed = _first_failed_segment(segments, b.iv)
                if segment_mode and failed is not None:
                    reason = (
                        f"允许温区 [{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 与运输段"
                        f"「{failed.name}」(第 {failed.no} 段)可用温区"
                        f"({_fmt_names([z.name for z in failed.zones])})无有效温度交集"
                    )
                else:
                    reason = (
                        f"允许温区 [{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 与新箱可用温区"
                        f"({_fmt_names([z.name for z in segments[0].zones])})"
                        f"无有效温度交集"
                    )
                add_unloaded(b, remaining, reason, new_box_failed=True)
                break
            boxes.append(box)
            remaining -= 1
            while remaining > 0 and box.try_load(b, b.iv):
                remaining -= 1

    # 5) 组装输出
    out_boxes: list[dict[str, Any]] = []
    loaded_units = 0
    loaded_volume = 0.0
    for box in boxes:
        assert box.feasible is not None
        box_batches = list(box.batch_map.values())
        # 箱内有填写首选温度区间的批次时,逐段设定点由热暴露模拟给出
        # (含预算批次按"最大累计预算使用率最低"选取,否则沿用区间中点规则)
        sim = (
            _simulate_exposure(box.segments, box.feasible, box_batches)
            if any(b.pref is not None for b in box_batches)
            else None
        )
        # 逐段校验:每段可设定温度 = 箱内货物共同交集 ∩ 该段各温区,再合并相邻段
        segment_checks: list[dict[str, Any]] = []
        envelope_raw: list[_Iv] = []
        transportable = True
        for seg in box.segments:
            merged = _merge_segments(
                [
                    s
                    for z in seg.zones
                    if (s := box.feasible.intersect(z.iv)) is not None
                ]
            )
            matched = [
                z.name
                for z in seg.zones
                if box.feasible.intersect(z.iv) is not None
            ]
            ok = bool(merged)
            check: dict[str, Any] = {
                "segment_no": seg.no,
                "name": seg.name,
                "hours": _r(seg.hours),
                "ok": ok,
                "temperature_segments": [
                    {"t_min": _r(s.lo), "t_max": _r(s.hi)} for s in merged
                ],
                "matched_zones": matched,
                "recommended_setpoint": None,
            }
            if ok:
                if sim is not None:
                    # 热暴露模拟选定的本段设定点
                    check["recommended_setpoint"] = _r(sim["setpoints"][seg.no])
                else:
                    widest_seg = max(merged, key=lambda s: s.hi - s.lo)
                    check["recommended_setpoint"] = _r(
                        (widest_seg.lo + widest_seg.hi) / 2
                    )
                envelope_raw.extend(merged)
            else:
                transportable = False
                check["reason"] = (
                    f"箱内货物共同允许温度 [{_r(box.feasible.lo)}, "
                    f"{_r(box.feasible.hi)}]℃ 与该段可用温区均无交集"
                )
            segment_checks.append(check)

        # 全程温度包络(兼容字段)= 各段可设定温度段合并后的结果
        envelope = _merge_segments(envelope_raw)
        widest = max(envelope, key=lambda s: s.hi - s.lo)
        matched_all = list(
            dict.fromkeys(name for c in segment_checks for name in c["matched_zones"])
        )
        items_out = []
        for it in box.items:
            loaded_units += it.units
            loaded_volume += it.volume
            items_out.append(
                {
                    "batch_no": it.batch_no,
                    "name": it.name,
                    "units": it.units,
                    "volume": _r(it.volume),
                }
            )
        # 热暴露结果:仅统计填写了首选温度区间的批次
        exposure_out = None
        if sim is not None:
            exposure_items = []
            for rec in sim["exposures"]:
                eb = rec["batch"]
                seg = rec["first_exceeded"]
                cum_v = rec["cumulative"]
                exposure_items.append(
                    {
                        "batch_no": eb.no,
                        "name": eb.name,
                        "preferred_t_min": _r(eb.pref.lo),
                        "preferred_t_max": _r(eb.pref.hi),
                        "cumulative_degree_hours": _r(cum_v),
                        "budget_degree_hours": (
                            _r(eb.budget) if eb.budget is not None else None
                        ),
                        "remaining_degree_hours": (
                            _r(eb.budget - cum_v) if eb.budget is not None else None
                        ),
                        "utilization": (
                            _r(cum_v / eb.budget) if eb.budget is not None else None
                        ),
                        "first_exceeded_segment_no": seg.no if seg else None,
                        "first_exceeded_segment_name": seg.name if seg else None,
                    }
                )
            exposure_out = {
                "setpoint_strategy": (
                    "budget_optimal"
                    if any(b.budget is not None for b in box_batches)
                    else "midpoint"
                ),
                "all_within_budget": sim["ok"],
                "items": exposure_items,
            }
        out_boxes.append(
            {
                "box_no": box.index,
                "temperature_range": {
                    "t_min": _r(envelope[0].lo),
                    "t_max": _r(envelope[-1].hi),
                },
                "temperature_segments": [
                    {"t_min": _r(s.lo), "t_max": _r(s.hi)} for s in envelope
                ],
                "recommended_setpoint": _r((widest.lo + widest.hi) / 2),
                "matched_zones": matched_all,
                "transportable": transportable,
                "segment_checks": segment_checks,
                "exposure": exposure_out,
                "used_volume": _r(box.used),
                "capacity": _r(box.capacity),
                "utilization": _r(min(1.0, box.used / box.capacity)),
                "items": items_out,
            }
        )

    total_units = sum(c.units for c in batches)
    total_volume = sum(c.total_volume for c in batches)
    unloaded_units = sum(u["units"] for u in unloaded)
    all_transportable = unloaded_units == 0 and all(
        b["transportable"] for b in out_boxes
    )

    return {
        "summary": {
            "total_cargo_units": total_units,
            "loaded_units": loaded_units,
            "unloaded_units": unloaded_units,
            "total_cargo_volume": _r(total_volume),
            "loaded_volume": _r(loaded_volume),
            "unloaded_volume": _r(total_volume - loaded_volume),
            "boxes_used": len(boxes),
            "max_boxes": max_boxes,
            "all_loaded": unloaded_units == 0,
            "transport_hours": _r(transport_hours),
            "segment_mode": segment_mode,
            "all_transportable": all_transportable,
            "heat_budget_enabled": any(b.budget is not None for b in batches),
        },
        "segments": [
            {
                "segment_no": seg.no,
                "name": seg.name,
                "hours": _r(seg.hours),
                "zones": [
                    {"name": z.name, "t_min": _r(z.iv.lo), "t_max": _r(z.iv.hi)}
                    for z in seg.zones
                ],
            }
            for seg in segments
        ],
        "boxes": out_boxes,
        "unloaded": unloaded,
        "volume_unit": volume_unit,
    }
