# 시간 선택 규칙 자체를 검증한다 (build_model.py 다음에 실행)
# 1) 공연 묶음째 빼고 나머지 공연 날로 참고 표를 만든 뒤, 규칙으로 도착 구간을 골라
#    뺀 공연 날의 실제 단시간 체류 차량 유입을 '시작 1시간-30분 전' 구간과 비교
# 2) 단시간 체류 기준(10·15·20·30분)을 바꿔도 구간 순서가 유지되는지
# 3) 큰 공연장 두 곳이 같은 날 공연한 날을 빼도 순서가 유지되는지
import csv, json, os, statistics as st, datetime as dt, collections

RAW = os.path.join("data", "raw")
BIN = 10
NB = 144
MAJOR = ["KSPO DOME", "핸드볼경기장", "올림픽홀"]
WINDOWS = list(range(240, 0, -30))  # 시작 몇 분 전부터 30분
LIMITS = {"3시간 전까지": 180, "2시간 30분 전까지": 150, "2시간 전까지": 120, "1시간 30분 전까지": 90}

recs = []
with open(os.path.join(RAW, "inout_202407.csv"), encoding="utf-8") as f:
    rd = csv.reader(f); next(rd)
    for r in rd:
        if len(r) >= 3 and r[1]:
            a = dt.datetime.strptime(r[1], "%Y-%m-%d %H:%M"); b = dt.datetime.strptime(r[2], "%Y-%m-%d %H:%M")
            recs.append((a, (b - a).total_seconds() / 60))
events = list(csv.DictReader(open(os.path.join("data", "events_all.csv"), encoding="utf-8-sig")))
by_date = collections.defaultdict(list)
for e in events:
    by_date[e["date"]].append(e)
days = sorted({a.date() for a, _ in recs})
cdays = []
for d in days:
    ds = d.isoformat()
    for v in MAJOR:
        c = sorted([e for e in by_date.get(ds, []) if e["venue"] == v and e["start"]], key=lambda e: e["start"])
        if c:
            h, m = map(int, c[0]["start"].split(":"))
            n_major = len({e["venue"] for e in by_date[ds] if e["venue"] in MAJOR})
            cdays.append({"date": d, "sb": (h * 60 + m) // BIN, "title": c[0]["title"], "multi": n_major > 1})
            break


def series(th):
    s = {d: [0] * NB for d in days}
    for a, stay in recs:
        if stay <= th:
            s[a.date()][(a.hour * 60 + a.minute) // BIN] += 1
    return s


def ratios(ser, c):
    y = ser[c["date"]]; sb = c["sb"]
    lo = max(0, sb - 36)
    pk = max(sum(y[k:k + 3]) / 3 for k in range(lo, sb - 2)) or 1
    return {w: st.mean(y[sb - w // BIN: sb - w // BIN + 3]) / pk for w in WINDOWS}


def table(ser, use):
    rs = [ratios(ser, c) for c in use]
    return {w: st.median(r[w] for r in rs) for w in WINDOWS}


def choose(tab, limit):
    cand = [w for w in WINDOWS if 90 <= w <= limit]
    return min(cand, key=lambda w: (round(tab[w], 3), w))  # 덜 붐비는 곳, 같으면 늦은 쪽


S15 = series(15)
groups = collections.defaultdict(list)
for c in cdays:
    groups[c["title"]].append(c)

# 1) 규칙 검증
rule = {name: [] for name in LIMITS}
for g, members in groups.items():
    train = [c for c in cdays if c["title"] != g and c["date"] not in {m["date"] for m in members}]
    tab = table(S15, train)
    for name, lim in LIMITS.items():
        w = choose(tab, lim)
        for c in members:
            r = ratios(S15, c)
            rule[name].append({"date": c["date"].isoformat(), "window_from": w, "chosen": round(r[w], 2),
                               "hour_before": round(r[60], 2), "better": r[w] < r[60]})
# 1-2) 단순 규칙과 비교 (같은 공연 묶음 빼기, 학습 필요 없음)
simple = {"3시간 전부터 30분": 180, "2시간 30분 전부터 30분": 150, "2시간 전부터 30분": 120, "1시간 30분 전부터 30분": 90, "1시간 전부터 30분": 60}
simple_res = {}
for name, w in simple.items():
    vals = [ratios(S15, c) for c in cdays]
    simple_res[name] = {"window_from": w, "mean": round(st.mean(r[w] for r in vals), 2),
                        "better_days_vs_hour": sum(r[w] < r[60] for r in vals), "days": len(vals)}

rule_summary = {name: {"window_from_mode": collections.Counter(x["window_from"] for x in v).most_common(1)[0][0],
                       "chosen_mean": round(st.mean(x["chosen"] for x in v), 2),
                       "hour_before_mean": round(st.mean(x["hour_before"] for x in v), 2),
                       "better_days": sum(x["better"] for x in v), "days": len(v),
                       "worst": max(v, key=lambda x: x["chosen"] - x["hour_before"])}
                for name, v in rule.items()}

# 2) 기준 민감도: 구간 순위 상관(스피어만)
def rank(d):
    order = sorted(d, key=lambda w: d[w]); return {w: i for i, w in enumerate(order)}


def spearman(a, b):
    ra, rb = rank(a), rank(b); n = len(a)
    return 1 - 6 * sum((ra[w] - rb[w]) ** 2 for w in a) / (n * (n * n - 1))


base_tab = table(S15, cdays)
sens = {}
for th in (10, 15, 20, 30):
    t = table(series(th), cdays)
    sens[th] = {"spearman_vs_15": round(spearman(t, base_tab), 2),
                "hour_before": round(t[60], 2), "two_half_before": round(t[150], 2)}
# 3) 단독 공연 날만
single = [c for c in cdays if not c["multi"]]
t_single = table(S15, single)
single_check = {"days": [c["date"].isoformat() for c in single], "spearman_vs_all": round(spearman(t_single, base_tab), 2),
                "hour_before": round(t_single[60], 2), "two_half_before": round(t_single[150], 2)}

out = {"rule": rule_summary, "simple_rules": simple_res, "rule_detail": rule, "threshold_sensitivity": sens, "single_show_days": single_check,
       "groups": {g: [m["date"].isoformat() for m in v] for g, v in groups.items()}}
json.dump(out, open(os.path.join("site", "data", "rule_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"simple": simple_res, "rule": {k: {kk: vv for kk, vv in v.items() if kk != "worst"} for k, v in rule_summary.items()},
                  "sens": sens, "single": single_check}, ensure_ascii=False, indent=1))
