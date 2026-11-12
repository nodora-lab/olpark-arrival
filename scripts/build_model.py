# 도착 시간 모델 만들기 + 검증
# 실행: python scripts/build_model.py   (저장소 맨 위 폴더에서, parse_events.py 먼저)
#
# 원칙
#  - 예측 시점에 아는 정보만 입력: 요일 유형, 공연장, 공연 시작 시각(예매 때 이미 공개).
#    공연 당일 관람객 수·당일 날씨 같은 사후 정보는 쓰지 않는다.
#  - 서로 다른 공연(같은 공연의 여러 회차는 한 묶음)으로 학습·검증을 나눈다.
#  - 기준선 = 요일 유형(평일·토·일) x 10분 시간대 평균.
import csv, json, os, statistics as st, datetime as dt, collections

RAW = os.path.join("data", "raw")
OUT = os.path.join("site", "data")
os.makedirs(OUT, exist_ok=True)
BIN = 10
NB = 24 * 60 // BIN
MAJOR = ["KSPO DOME", "핸드볼경기장", "올림픽홀"]  # 큰 공연장 우선순위
SHORT_STOP = 15  # 15분 이하 머문 차 = 내려 주기·태우기·돌아 나가기로 봄


def tbin(t):
    return (t.hour * 60 + t.minute) // BIN


def hm(b):
    m = b * BIN
    return f"{m // 60:02d}:{m % 60:02d}"


def daytype(d):
    w = d.weekday()
    return "토" if w == 5 else "일" if w == 6 else "평일"


# ---------- 1. 입출차 2024-07 ----------
recs = []
with open(os.path.join(RAW, "inout_202407.csv"), encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd)
    for r in rd:
        if len(r) < 3 or not r[1]:
            continue
        a = dt.datetime.strptime(r[1], "%Y-%m-%d %H:%M")
        b = dt.datetime.strptime(r[2], "%Y-%m-%d %H:%M")
        recs.append((a, b))

days = sorted({a.date() for a, _ in recs})
ent = {d: [0] * NB for d in days}        # 10분마다 들어온 차(모두)
ent_long = {d: [0] * NB for d in days}   # 15분 넘게 머문 차(실제 주차)
ent_short = {d: [0] * NB for d in days}  # 15분 이하(내려 주기 등)
occ = {d: [0] * NB for d in days}        # 10분 구간 시작 때 안에 있던 차
for a, b in recs:
    d = a.date()
    k = tbin(a)
    ent[d][k] += 1
    stay = (b - a).total_seconds() / 60
    (ent_short if stay <= SHORT_STOP else ent_long)[d][k] += 1
    for dd in days:
        t0 = dt.datetime.combine(dd, dt.time())
        if b <= t0 or a >= t0 + dt.timedelta(days=1):
            continue
        s = max(0, -(-int((a - t0).total_seconds()) // (BIN * 60)))
        e = min(NB, -(-int((b - t0).total_seconds()) // (BIN * 60)))
        for i in range(s, e):
            occ[dd][i] += 1

stays = sorted((b - a).total_seconds() / 60 for a, b in recs)
short_share = sum(1 for x in stays if x <= SHORT_STOP) / len(stays)

# ---------- 2. 공연 일정 ----------
events = list(csv.DictReader(open(os.path.join("data", "events_all.csv"), encoding="utf-8-sig")))
by_date = collections.defaultdict(list)
for e in events:
    by_date[e["date"]].append(e)


def main_show(dstr):
    """그날 가장 큰 공연장의 (가장 이른) 공연. 없으면 None."""
    for v in MAJOR:
        c = [e for e in by_date.get(dstr, []) if e["venue"] == v and e["start"]]
        if c:
            c.sort(key=lambda e: e["start"])
            return c[0]
    return None


cdays = []
for d in days:
    m = main_show(d.isoformat())
    if m:
        h, mi = map(int, m["start"].split(":"))
        cdays.append({"date": d, "start_bin": (h * 60 + mi) // BIN, "venue": m["venue"],
                      "title": m["title"], "all": [f"{e['venue']} {e['start']}" for e in by_date[d.isoformat()]
                                                   if e["venue"] in MAJOR]})
cset = {c["date"]: c for c in cdays}

# 같은 공연 회차 묶음 (제목 기준) -> 묶음째 빼고 검증
grp_of = {}
for c in cdays:
    grp_of[c["date"]] = c["title"]
# 같은 날 두 공연이 걸쳐 묶음이 겹치면 날짜가 이어진 것끼리 합친다
groups = collections.defaultdict(set)
for c in cdays:
    groups[c["title"]].add(c["date"])

# ---------- 3. 예측 방법 ----------
LO, HI = 11 * 60 // BIN, 21 * 60 // BIN  # 평가 구간 11:00-21:00


def baseline(series, d, train):
    same = [x for x in train if daytype(x) == daytype(d)]
    if not same:
        same = train
    return [st.mean(series[x][k] for x in same) for k in range(NB)]


def aligned(series, d, train_c, start_bin):
    out = []
    for k in range(NB):
        vals = []
        for c in train_c:
            j = k - start_bin + c["start_bin"]
            if 0 <= j < NB:
                vals.append(series[c["date"]][j])
        out.append(st.mean(vals) if vals else 0)
    return out


def hybrid(series, d, train, train_c, start_bin):
    """기준선(요일 유형 평균) + 공연 시작 기준으로 맞춘 '평소보다 많은 양'."""
    base_d = baseline(series, d, train)
    exc = []
    for k in range(NB):
        vals = []
        for c in train_c:
            j = k - start_bin + c["start_bin"]
            if 0 <= j < NB:
                bc = baseline(series, c["date"], [x for x in train if x != c["date"]])
                vals.append(series[c["date"]][j] - bc[j])
        exc.append(st.mean(vals) if vals else 0)
    return [base_d[k] + exc[k] for k in range(NB)]


def mae(y, p, lo=LO, hi=HI):
    return st.mean(abs(y[k] - p[k]) for k in range(lo, hi))


def peak_bin(y, start_bin):
    lo = max(0, start_bin - 6 * 60 // BIN)
    seg = y[lo:start_bin + 1]
    return lo + seg.index(max(seg))


def recommend(pred, start_bin, buffer_min=60, calm=0.75, width_min=60, earliest_min=240):
    """시작 buffer 분 전까지 도착, 예측 입차가 공연 전 최고치의 calm 배 미만인
    가장 늦은 width 분 구간. 없으면 가장 덜 붐비는 구간."""
    lo = max(0, start_bin - earliest_min // BIN)
    pk = max(pred[max(0, start_bin - 6 * 60 // BIN):start_bin + 1]) or 1
    w = width_min // BIN
    last_end = start_bin - buffer_min // BIN
    best = None
    for end in range(last_end, lo + w - 1, -1):
        seg = pred[end - w + 1:end + 1]
        if max(seg) < calm * pk:
            best = (end - w + 1, end + 1)
            break
    if best is None:
        cands = [(st.mean(pred[e - w + 1:e + 1]), e) for e in range(lo + w - 1, last_end + 1)]
        _, e = min(cands)
        best = (e - w + 1, e + 1)
    return best


results = []
for c in cdays:
    d = c["date"]
    hold = groups[c["title"]] | {d}
    train = [x for x in days if x not in hold]
    train_c = [x for x in cdays if x["date"] not in hold]
    sb = c["start_bin"]
    row = {"date": d.isoformat(), "weekday": "월화수목금토일"[d.weekday()], "start": hm(sb),
           "venue": c["venue"], "shows": c["all"]}
    for name, series in (("entries", ent), ("occupancy", occ)):
        y = series[d]
        pb = baseline(series, d, train)
        pa = aligned(series, d, train_c, sb)
        ph = hybrid(series, d, train, train_c, sb)
        row[name] = {"baseline": round(mae(y, pb), 1), "aligned": round(mae(y, pa), 1),
                     "hybrid": round(mae(y, ph), 1)}
        if name == "entries":
            ap = peak_bin(y, sb)
            row["peak_actual"] = hm(ap)
            row["peak_err_min"] = {k: abs(peak_bin(p, sb) - ap) * BIN for k, p in
                                   (("baseline", pb), ("aligned", pa), ("hybrid", ph))}
            # 의사결정 평가 (내려 주기 혼잡 = 15분 이하 차, 주차 혼잡 = 모든 입차)
            dec = {}
            for sname, ser in (("dropoff", ent_short), ("entries", ent)):
                yy = ser[d]
                lo = max(0, sb - 6 * 60 // BIN)
                act_peak = max(sum(yy[k:k + 6]) / 6 for k in range(lo, sb - 5)) or 1
                preds = {"baseline": baseline(ser, d, train), "aligned": aligned(ser, d, train_c, sb),
                         "hybrid": hybrid(ser, d, train, train_c, sb)}
                dd = {}
                for k, pp in preds.items():
                    s0, e0 = recommend(pp, sb)
                    dd[k] = {"window": f"{hm(s0)}-{hm(e0)}", "ratio_to_peak": round(st.mean(yy[s0:e0]) / act_peak, 2),
                             "wait_min": (sb - (s0 + e0) // 2) * BIN}
                for off in (180, 150, 120, 90, 60):
                    s0, e0 = sb - off // BIN, sb - off // BIN + 6
                    dd[f"fixed_{off}"] = {"window": f"{hm(s0)}-{hm(e0)}", "ratio_to_peak": round(st.mean(yy[s0:e0]) / act_peak, 2),
                                          "wait_min": off - 30}
                dec[sname] = dd
            row["decision"] = dec
    results.append(row)


def avg(key, sub):
    return round(st.mean(r[key][sub] for r in results), 1)


summary = {
    "n_days": len(results),
    "n_groups": len(groups),
    "entries_mae": {k: avg("entries", k) for k in ("baseline", "aligned", "hybrid")},
    "occupancy_mae": {k: avg("occupancy", k) for k in ("baseline", "aligned", "hybrid")},
    "peak_err_min": {k: round(st.mean(r["peak_err_min"][k] for r in results), 1) for k in ("baseline", "aligned", "hybrid")},
    "decision": {sn: {k: {"ratio_to_peak": round(st.mean(r["decision"][sn][k]["ratio_to_peak"] for r in results), 2),
                          "wait_min": round(st.mean(r["decision"][sn][k]["wait_min"] for r in results))}
                      for k in results[0]["decision"][sn]} for sn in ("dropoff", "entries")},
}
best = min(("baseline", "aligned", "hybrid"), key=lambda k: summary["entries_mae"][k])
summary["best_entries"] = best
summary["model_beats_baseline"] = summary["entries_mae"][best] < summary["entries_mae"]["baseline"]

# ---------- 4. 앱에 넣을 패턴 (전체 공연일로 다시 학습) ----------
OFF_LO, OFF_HI = -8 * 60 // BIN, 3 * 60 // BIN  # 시작 8시간 전 - 3시간 뒤


def profile(series, use):
    rows = []
    for o in range(OFF_LO, OFF_HI + 1):
        vals = []
        for c in use:
            j = c["start_bin"] + o
            if 0 <= j < NB:
                vals.append(series[c["date"]][j])
        vals.sort()
        q = lambda p: vals[min(len(vals) - 1, int(p * (len(vals) - 1) + 0.5))]
        rows.append({"off": o * BIN, "mean": round(st.mean(vals), 1), "p25": q(0.25), "p75": q(0.75),
                     "min": vals[0], "max": vals[-1]})
    return rows


prof = {"entries": profile(ent, cdays), "entries_long": profile(ent_long, cdays),
        "entries_short": profile(ent_short, cdays), "occupancy": profile(occ, cdays)}

# 요일 유형별 평소 곡선(공연 없는 날만, 없으면 전체)
base_curves = {}
for t in ("평일", "토", "일"):
    pool = [d for d in days if daytype(d) == t and d not in cset] or [d for d in days if daytype(d) == t]
    base_curves[t] = {"n": len(pool), "has_show_days": any(d in cset for d in pool),
                      "occupancy": [round(st.mean(occ[d][k] for d in pool)) for k in range(NB)],
                      "entries": [round(st.mean(ent[d][k] for d in pool), 1) for k in range(NB)]}

daily = [{"date": d.isoformat(), "weekday": "월화수목금토일"[d.weekday()], "entries": sum(ent[d]),
          "max_occ": max(occ[d]), "max_occ_at": hm(occ[d].index(max(occ[d]))),
          "show": cset[d]["all"] if d in cset else []} for d in days]

# ---------- 4-1. 도착 시점별 과거 참고 범위 (앱의 중심 표) ----------
# 공연 시작 기준 30분 단위 도착 구간마다, 그날 공연 전 가장 붐빈 60분 대비 몇 %였는지.
# 학습이 필요 없는 기술 통계라서 '예측'이라 부르지 않는다.
arrival_table = []
for off in range(240, 0, -30):  # 시작 4시간 전부터 30분 전까지
    rowt = {"from_min": off, "to_min": off - 30}
    for sname, ser in (("dropoff", ent_short), ("entries", ent), ("parked", occ)):
        vals = []
        for c in cdays:
            yy = ser[c["date"]]
            sb = c["start_bin"]
            lo = max(0, sb - 6 * 60 // BIN)
            if sname == "parked":
                pk = max(yy[lo:sb + 1]) or 1
                v = st.mean(yy[sb - off // BIN: sb - off // BIN + 3]) / pk
            else:
                pk = max(sum(yy[k:k + 3]) / 3 for k in range(lo, sb - 2)) or 1
                v = st.mean(yy[sb - off // BIN: sb - off // BIN + 3]) / pk
            vals.append(round(v, 2))
        vals.sort()
        rowt[sname] = {"median": round(st.median(vals), 2), "min": vals[0], "max": vals[-1],
                       "p25": vals[int(0.25 * (len(vals) - 1) + 0.5)], "p75": vals[int(0.75 * (len(vals) - 1) + 0.5)]}
    arrival_table.append(rowt)

# ---------- 5. 주차장 혼잡도 기록 (시 단위만 믿을 수 있음) ----------
cong = []
with open(os.path.join(RAW, "parking_congestion_20260812.csv"), encoding="utf-8") as f:
    rd = csv.reader(f)
    next(rd)
    for r in rd:
        if len(r) >= 6:
            cong.append({"zone": r[2], "state": r[3], "date": r[4], "time": r[5]})
ts_bug = sum(1 for c in cong if c["time"][3:5] == c["date"][5:7] and c["time"][6:8] == c["date"][8:10])
cong_days = sorted({c["date"] for c in cong})
near = {"KSPO DOME": ["P4", "P5"], "핸드볼경기장": ["P6"], "올림픽홀": ["P2"], "우리금융아트홀": ["P7"]}
cong_events = []
for dstr in cong_days:
    m = main_show(dstr)
    if not m:
        continue
    zs = near[m["venue"]]
    hits = sorted(int(c["time"][:2]) for c in cong if c["date"] == dstr and c["zone"] in zs and c["state"] in ("혼잡", "만차"))
    if not hits:
        continue
    sh = int(m["start"][:2])
    cong_events.append({"date": dstr, "venue": m["venue"], "start": m["start"], "zones": zs,
                        "first_busy_hour": hits[0], "hours_before_start": sh - hits[0]})
hb = sorted(x["hours_before_start"] for x in cong_events)
cong_summary = {"rows": len(cong), "days": len(cong_days), "time_bug_rows": ts_bug,
                "event_days_with_record": len(cong_events),
                "hours_before_start": {"min": hb[0], "median": st.median(hb), "max": hb[-1]} if hb else None,
                "examples": cong_events}

# ---------- 6. 다가오는 공연 ----------
today = dt.date.today()
upcoming = []
for e in events:
    if e["date"] >= today.isoformat() and e["venue"] in MAJOR + ["우리금융아트홀", "88잔디마당", "티켓링크 라이브 아레나"]:
        upcoming.append({"date": e["date"], "venue": e["venue"], "title": e["title"], "start": e["start"],
                         "time_text": e["tm"], "source": f"https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoView.es?mid=a20301010100&evtSeq={e['evtSeq']}"})

# 영문 공연정보(개방 파일)에서 '공연일자'가 실제 공연일인지 점검
perf = list(csv.reader(open(os.path.join(RAW, "perf_en_20260901.csv"), encoding="utf-8")))[1:]
perf = [p for p in perf if len(p) >= 6]
cnt = collections.Counter(p[5] for p in perf)
same_date_max = cnt.most_common(1)[0]

model = {
    "built": dt.datetime.now().isoformat(timespec="minutes"),
    "bin_min": BIN,
    "short_stop_min": SHORT_STOP,
    "short_stop_share": round(short_share, 3),
    "train_period": "2024-07-01 - 2024-07-31 (올림픽공원 입출차 정보, 215,528건)",
    "concert_days": [{"date": c["date"].isoformat(), "start": hm(c["start_bin"]), "venue": c["venue"], "shows": c["all"]} for c in cdays],
    "validation": {"summary": summary, "by_day": results},
    "profile": prof,
    "arrival_table": arrival_table,
    "base_curves": base_curves,
    "daily": daily,
    "congestion": cong_summary,
    "perf_en_check": {"rows": len(perf), "most_common_date": same_date_max[0], "rows_on_that_date": same_date_max[1]},
}
json.dump(model, open(os.path.join(OUT, "model.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(upcoming, open(os.path.join(OUT, "events.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("congestion", json.dumps({k: v for k, v in cong_summary.items() if k != "examples"}, ensure_ascii=False))
print("upcoming", len(upcoming), "perf_en", model["perf_en_check"], "short_share", model["short_stop_share"])
