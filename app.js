/* 공연 날 도착 길잡이 - 정적 웹앱 (서버·계정 없음)
   데이터: site/data/model.json (scripts/build_model.py가 만듦), events.json, venues.json
   실시간: 한국체육산업개발(주) 실시간 주차현황 API (공공데이터포털 15168686) */
(function () {
  "use strict";
  var LIVE_URL = "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504";
  var WD = ["일", "월", "화", "수", "목", "금", "토"];
  var params = new URLSearchParams(location.search);
  var DEMO = params.get("demo") === "1"; // 제출용 화면: 가상 공연명
  var state = { ev: null, mode: "bus", limit: 150, slow: false };
  var M, EVENTS, V, R;

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function toMin(hhmm) { var p = hhmm.split(":"); return (+p[0]) * 60 + (+p[1]); }
  function fmt(min) {
    min = ((min % 1440) + 1440) % 1440;
    var h = Math.floor(min / 60), m = min % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }
  function korDur(min) {
    var h = Math.floor(min / 60), m = min % 60;
    return (h ? h + "시간" : "") + (h && m ? " " : "") + (m ? m + "분" : "");
  }
  function dateLabel(iso) {
    var d = new Date(iso + "T00:00:00");
    return (d.getMonth() + 1) + "월 " + d.getDate() + "일(" + WD[d.getDay()] + ")";
  }
  function pct(x) { return Math.round(x * 100) + "%"; }
  function cls(x) { return x < 0.6 ? "calm" : x < 0.8 ? "mid" : "busy"; }
  function word(x) { return x < 0.6 ? "적음" : x < 0.8 ? "보통" : "많음"; }

  function demoEvents() {
    var base = new Date(); base.setHours(0, 0, 0, 0);
    function next(dow, plus) {
      var d = new Date(base); d.setDate(d.getDate() + ((dow - d.getDay() + 7) % 7 || 7) + (plus || 0));
      var mm = d.getMonth() + 1, dd = d.getDate();
      return d.getFullYear() + "-" + (mm < 10 ? "0" : "") + mm + "-" + (dd < 10 ? "0" : "") + dd;
    }
    return [
      { date: next(6), venue: "KSPO DOME", title: "가을빛 트로트 큰잔치 (가상 공연)", start: "15:00" },
      { date: next(0), venue: "KSPO DOME", title: "가을빛 트로트 큰잔치 (가상 공연)", start: "14:00" },
      { date: next(6, 7), venue: "올림픽홀", title: "은빛 하모니 콘서트 (가상 공연)", start: "17:00" },
      { date: next(5, 7), venue: "핸드볼경기장", title: "별빛 발라드의 밤 (가상 공연)", start: "19:30" },
      { date: next(0, 14), venue: "우리금융아트홀", title: "추억의 가요 무대 (가상 공연)", start: "16:00" }
    ];
  }

  /* ---------- 1. 공연 목록 ---------- */
  function renderEvents() {
    var box = $("event-list");
    box.innerHTML = "";
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var list = EVENTS.filter(function (e) { return new Date(e.date + "T00:00:00") >= today; })
      .sort(function (a, b) { return (a.date + (a.start || "")).localeCompare(b.date + (b.start || "")); });
    var shown = 0, lastDate = "";
    list.forEach(function (e, i) {
      if (e.date !== lastDate) {
        var hd = el("p", "dhead", dateLabel(e.date)); if (i >= 8) hd.hidden = true;
        box.appendChild(hd); lastDate = e.date;
      }
      var b = el("button", "ev");
      b.type = "button";
      b.setAttribute("role", "listitem");
      b.appendChild(el("span", "d", e.venue));
      b.appendChild(el("span", "s", e.start || "시각 확인"));
      b.appendChild(el("span", "t", e.title));
      if (i >= 8) b.hidden = true;
      b.addEventListener("click", function () { pick(e); });
      box.appendChild(b);
      shown++;
    });
    if (!shown) box.appendChild(el("p", "sub", "다가오는 공연이 목록에 없습니다. 아래 '직접 넣기'를 써 주세요."));
    if (list.length > 8) {
      var more = el("button", "btn ghost more", "공연 더 보기 (" + (list.length - 8) + "개)");
      more.type = "button";
      more.addEventListener("click", function () {
        Array.prototype.forEach.call(box.querySelectorAll(".ev[hidden], .dhead[hidden]"), function (x) { x.hidden = false; });
        more.remove();
      });
      box.appendChild(more);
    }
  }

  function pick(e) {
    if (!e.start) {
      var t = prompt("공연 시작 시각을 넣어 주세요 (예: 18:00)\n안내 문구: " + (e.time_text || ""), "18:00");
      if (!t || !/^\d{1,2}:\d{2}$/.test(t)) return;
      e = Object.assign({}, e, { start: t });
    }
    state.ev = e; state.sel = null;
    $("chosen").textContent = dateLabel(e.date) + " " + e.start + " · " + e.venue + " · " + e.title;
    $("step-group").hidden = false;
    $("step-group").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ---------- 2. 일행 선택 ---------- */
  function bindChoices() {
    document.querySelectorAll("[data-mode]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.mode = b.dataset.mode;
        document.querySelectorAll("[data-mode]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      });
    });
    document.querySelectorAll("[data-limit]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.limit = +b.dataset.limit; state.sel = null;
        document.querySelectorAll("[data-limit]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      });
    });
    $("slow").addEventListener("change", function () { state.slow = this.checked; });
    $("show").addEventListener("click", function () { showResult(false); });
    $("again").addEventListener("click", function () {
      $("step-result").hidden = true; $("step-group").hidden = true;
      $("step-pick").scrollIntoView({ behavior: "smooth" });
    });
    $("m-go").addEventListener("click", function () {
      var d = $("m-date").value, t = $("m-time").value;
      if (!d || !t) { alert("날짜와 시작 시각을 넣어 주세요."); return; }
      pick({ date: d, venue: $("m-venue").value, title: "직접 넣은 공연", start: t, manual: true });
    });
    $("copy").addEventListener("click", copyText);
    $("to-manual").addEventListener("click", function () { $("manual").open = true; $("manual").scrollIntoView({ behavior: "smooth", block: "center" }); });
    $("live-refresh").addEventListener("click", loadLive);
  }

  /* ---------- 3. 결과 ---------- */
  function metricFor(mode) { return mode === "car" ? "entries" : "dropoff"; }

  // 권장 = 고른 '가장 일찍 도착할 수 있는 때'부터 30분.
  // 데이터로 구간을 고르는 규칙은 이 단순 규칙보다 낫지 않았음(scripts/validate_rule.py).
  function choose(metric, limit) {
    return M.arrival_table.filter(function (r) { return r.from_min === limit; })[0];
  }
  function rowAt(from) { return M.arrival_table.filter(function (r) { return r.from_min === from; })[0]; }
  function busiest(metric) {
    return M.arrival_table.slice().sort(function (a, b) { return b[metric].median - a[metric].median; })[0];
  }

  var MAJOR = ["KSPO DOME", "핸드볼경기장", "올림픽홀"];
  // 분석 기준 = 그날 가장 큰 공연장(KSPO DOME → 핸드볼경기장 → 올림픽홀)의 가장 이른 회차
  // 그날 다른 공연 일정을 확인할 수 없으면(목록이 오래됐거나 목록 범위 밖 날짜) 적용 여부를 확정할 수 없어 시간 비교안을 주지 않음
  function scheduleKnown(e) {
    if (DEMO) return true;
    var age = (Date.now() - new Date(M.built).getTime()) / 864e5;
    if (age > 14) return false;
    var maxd = EVENTS.reduce(function (m, x) { return x.date > m ? x.date : m; }, "");
    return e.date <= maxd;
  }
  function applicable(e) {
    if (MAJOR.indexOf(e.venue) < 0) return false;
    if (!scheduleKnown(e)) return false;
    var c = EVENTS.filter(function (x) { return x.date === e.date && x.start && MAJOR.indexOf(x.venue) >= 0; });
    if (!c.some(function (x) { return x.venue === e.venue && x.start === e.start; })) c.push(e);
    c.sort(function (a, b) { return (MAJOR.indexOf(a.venue) - MAJOR.indexOf(b.venue)) || a.start.localeCompare(b.start); });
    return c[0].venue === e.venue && c[0].start === e.start;
  }

  var last = null;
  function showResult(keepSel) {
    var e = state.ev, metric = metricFor(state.mode);
    var s = toMin(e.start), shift = state.slow ? 20 : 0;
    var ok = applicable(e) && state.mode !== "transit";
    if (!keepSel || state.sel == null) state.sel = state.limit;
    var c = rowAt(state.sel), bz = busiest(metric);
    var w0 = s - c.from_min - shift, w1 = s - c.to_min - shift;
    var what = metric === "dropoff" ? "잠깐 들렀다 나간 차(15분 이하: 내려 주기·태우기·돌아 나가기 등, 공원 전체)" : "공원에 들어온 차(공원 전체)";
    $("avoid-box").hidden = !ok;
    $("r-multi").hidden = true;
    if (ok) {
      $("r-label").textContent = state.sel === state.limit ? "첫 도착 비교안 (가장 일찍 올 수 있는 때부터 30분)" : "고르신 30분";
      $("r-window").className = "time-big";
      $("r-window").textContent = fmt(w0) + " - " + fmt(w1);
      $("r-key").hidden = false;
      $("r-key").textContent = "공연까지 " + korDur(c.to_min + shift) + "-" + korDur(c.from_min + shift) + " · 과거 차량 유입 " + pct(c[metric].median) + " (대기 시간·주차 가능성 아님)";
      var q = $("r-quick"); q.innerHTML = ""; q.hidden = false;
      [state.limit, state.limit - 30, state.limit - 60].forEach(function (f, i) {
        var rr = rowAt(f); if (!rr) return;
        var bt = el("button", null, ["첫 비교안", "30분 늦게", "1시간 늦게"][i]);
        bt.type = "button";
        bt.setAttribute("aria-pressed", rr.from_min === c.from_min ? "true" : "false");
        bt.appendChild(el("small", null, fmt(s - f - shift) + " · " + pct(rr[metric].median)));
        bt.addEventListener("click", function () { state.sel = f; showResult(true); });
        q.appendChild(bt);
      });
      $("r-why").textContent = "자세히: " + what + "를 그날 가장 몰린 30분 대비로 본 9일 중앙값(가운데 절반 " + pct(c[metric].p25) + "-" + pct(c[metric].p75) + ")이에요." +
        (c.from_min < 60 ? " 시작 1시간 안 도착은 입장 줄·화장실 여유가 적어요." : "");
      $("r-later").textContent = "다른 30분은 아래 막대를 눌러 고를 수 있어요.";
      var others = EVENTS.filter(function (x) { return x.date === e.date && !(x.venue === e.venue && x.start === e.start); }).map(function (x) { return x.venue + " " + (x.start || ""); });
      if (others.length) { $("r-multi").hidden = false; $("r-multi").textContent = "같은 날 다른 공연도 있어요(" + others.join(", ") + "). 공원 전체 기준 참고값이라 더 붐빌 수 있어요."; }
      $("r-avoid").textContent = fmt(s - bz.from_min) + " - " + fmt(s - bz.to_min);
      $("r-avoid-why").textContent = "공연 시작 " + korDur(bz.from_min) + " 전부터 30분. 9일 중앙값이 가장 높았던 구간(" + pct(bz[metric].median) + ")이에요.";
    } else {
      $("r-later").textContent = "";
      $("r-key").hidden = true; $("r-quick").hidden = true;
      $("r-window").className = "time-big neutral";
      if (state.mode === "transit") {
        $("r-label").textContent = "지하철·버스로 오실 때";
        $("r-window").textContent = "출구에서 모이기";
        $("r-why").textContent = "지하철역·보행 혼잡은 공개 자료가 없어 시간을 권하지 않아요. 모이는 출구: 5·9호선 올림픽공원역 3·4번 출구. 아래 막대는 공원 차량 기준 참고예요.";
      } else {
        $("r-label").textContent = "이 공연은 도착 시간을 비교할 수 없어요";
        $("r-window").textContent = "참고 자료만";
        $("r-why").textContent = !scheduleKnown(e)
          ? "그날 다른 공연장·회차 일정을 확인할 수 없어(공연 목록 밖 날짜이거나 목록이 오래됨) 분석 기준에 맞는지 정할 수 없어요. 아래 공원 전체 과거 참고 범위와 교통 안내만 보여 드려요."
          : "분석 기준은 그날 가장 큰 공연장(KSPO DOME → 핸드볼경기장 → 올림픽홀)의 가장 이른 회차예요. 이 공연은 거기에 해당하지 않아 시간을 권하지 않고, 아래 공원 전체 과거 참고 범위와 교통 안내만 보여 드려요.";
      }
    }
    last = { e: e, ok: ok, w0: w0, w1: w1, b0: s - bz.from_min, b1: s - bz.to_min, metric: metric, lead: c.from_min + shift };
    renderChart(s, metric, ok ? c : null, ok);
    renderInfo(e);
    renderBasis(metric);
    if (!keepSel) {
      $("step-result").hidden = false;
      $("step-result").scrollIntoView({ behavior: "smooth", block: "start" });
      loadLive();
    }
  }

  function renderChart(s, metric, chosen, ok) {
    var box = $("chart"); box.innerHTML = "";
    $("chart-note").textContent = (metric === "dropoff" ? "15분 안에 나간 차(내려 주기·태우기·돌아 나가기 등)" : "공원 주차장에 들어온 모든 차") +
      " 기준. 2024년 7월 공연 날 " + M.concert_days.length + "일을 공연 시작 시각에 맞춰 겹쳐, 공연 전 가장 많았던 30분 대비 %로 나타냈어요. 대기 시간·도로 정체를 잰 값은 아니에요.";
    M.arrival_table.forEach(function (r) {
      var v = r[metric];
      var row = el("div", "row" + (r === chosen ? " pick" : "") + (ok ? "" : " off"));
      if (ok) {
        row.tabIndex = 0; row.setAttribute("role", "button");
        var go = function () { state.sel = r.from_min; showResult(true); $("step-result").scrollIntoView({ behavior: "smooth", block: "start" }); };
        row.addEventListener("click", go);
        row.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); } });
      }
      var tl = el("div", "tl", fmt(s - r.from_min));
      tl.appendChild(el("small", null, "시작 " + korDur(r.from_min) + " 전"));
      var bar = el("div", "bar");
      var rg = el("span", "r"); rg.style.left = (v.p25 * 100) + "%"; rg.style.width = Math.max(1, (v.p75 - v.p25) * 100) + "%";
      var m = el("span", "m " + cls(v.median) + "-c"); m.style.width = (v.median * 100) + "%";
      bar.appendChild(rg); bar.appendChild(m);
      bar.setAttribute("role", "img");
      bar.setAttribute("aria-label", word(v.median) + ", 가장 붐빌 때의 " + pct(v.median));
      row.appendChild(tl); row.appendChild(bar); row.appendChild(el("div", "pct", pct(v.median)));
      box.appendChild(row);
    });
  }

  function venueCong(venue) {
    var ex = (M.congestion.examples || []).filter(function (x) { return x.venue === venue && x.hours_before_start >= 0; });
    if (!ex.length) return null;
    var h = ex.map(function (x) { return x.hours_before_start; }).sort(function (a, b) { return a - b; });
    return { n: ex.length, median: h[Math.floor((h.length - 1) / 2)], zones: ex[0].zones.join("·") };
  }

  function renderInfo(e) {
    var ul = $("info"); ul.innerHTML = "";
    var v = V.venues[e.venue];
    function li(t) { ul.appendChild(el("li", null, t)); }
    if (v) li(e.venue + "에서 가까운 문: " + v.gates.join(" · "));
    if (state.mode === "bus") {
      li("단체버스 내리는 곳은 미리 공원 안내(" + V.phone.split(" ")[1] + ")에 확인해 두세요.");
      li("대형 주차 요금: " + V.fees.large.replace("대형(24인승, 2.5톤 이상) ", ""));
      li(V.fees.free + " (내려 주고 바로 나갈 때)");
    } else if (state.mode === "car") {
      if (v) li("공연장 옆 주차장: " + v.parking + " (" + v.spaces + "면, 걸어서 " + v.walk + ")");
      var cg = venueCong(e.venue);
      if (cg) li("주차장 혼잡도 기록: " + cg.zones + " 주차장은 공연 " + cg.n + "일 중 절반이 시작 " + cg.median + "시간 전 이미 '혼잡·만차'로 적혀 있었어요(기록 시각 기준). 차 여러 대면 한 대로 모아 타거나 지하철을 권해요.");
      li("주차 요금: " + V.fees.small);
      li(V.fees.event);
    } else {
      V.subway.forEach(function (s) { li(s); });
    }
    li(V.entry_hours);
    $("notice").textContent = "공원 안내: " + V.official_notice;
  }

  function renderBasis(metric) {
    var b = $("basis"); b.innerHTML = "";
    var vs = M.validation.summary;
    var p1 = el("p", null, "자료: 2024년 7월 올림픽공원 입출차 기록 215,528건(공공데이터포털 15138735), 주차장 혼잡도 기록 699건(15164156), 실시간 주차현황(15168686), 공연 일정(올림픽공원 홈페이지 공연 안내). 예측 때는 요일·공연장·시작 시각처럼 미리 아는 정보만 씁니다.");
    b.appendChild(p1);
    var p2 = el("p", null, "맞춰 보기: 공연 " + vs.n_days + "일(같은 공연 회차는 묶어 " + vs.n_groups + "묶음)을 하나씩 빼고 나머지로 맞춰 봤습니다. 공연 시작 시각에 맞춘 예측은 '요일·시간대 평균'보다 10분당 입차 수 오차가 작지 않았습니다(" +
      vs.entries_mae.aligned + "대 대 " + vs.entries_mae.baseline + "대). 그래서 이 화면은 '정확한 예측'이 아니라 과거 공연 날의 참고 범위를 보여 줍니다.");
    b.appendChild(p2);
    if (R) {
      var sr = R.simple_rules;
      var t = Object.keys(sr).map(function (k) { return k.replace(" 전부터 30분", " 전") + " " + pct(sr[k].mean); }).join(" · ");
      var s150 = sr["2시간 30분 전부터 30분"];
      b.appendChild(el("p", null, "도착 시점별 실제값(공연 9일 평균, 잠깐 들른 차): " + t + ". '2시간 30분 전'은 " + s150.days + "일 중 " + s150.better_days_vs_hour +
        "일 '1시간 전'보다 적었고, 나머지 날(같은 공연 2회차)은 오히려 많았어요. 데이터로 구간을 따로 고르는 방식도 맞춰 봤지만 '가능한 가장 이른 30분'보다 낫지 않아 이 단순한 방식을 씁니다."));
    }
    var p4 = el("p", null, "한계: 자료가 한 달(공연 9일, 5개 공연)뿐이고 사람이 아니라 차 기록이에요. 15분 이하 차에는 내려 주기 말고 돌아 나가기도 섞여 있어요. 혼잡도 기록은 분·초 칸에 월·일이 들어 있어 '시'만 썼어요. 참고 범위이지 지시가 아니에요.");
    b.appendChild(p4);
  }

  /* ---------- 실시간 주차 ---------- */
  function loadLive() {
    $("live-num").textContent = "불러오는 중";
    fetch(LIVE_URL, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      var n = j && j[0] && j[0].parking_sum;
      if (n == null) throw new Error("no data");
      $("live-num").textContent = Number(n).toLocaleString("ko-KR");
      $("live-num").className = "live muted";
      var now = new Date();
      $("live-note").textContent = fmt(now.getHours() * 60 + now.getMinutes()) + " 기준 · 동2·남2·북2 주차장 합계, 기관 표기 '주차대수'. " +
        (window.LIVE_MEANING || "주차된 차 수인지 남은 자리 수인지 기관 문서에 없어 뜻을 확인하는 중이에요. 도착 시간 계산에는 쓰지 않아요.");
    }).catch(function () {
      $("live-num").textContent = "지금은 못 불러왔어요";
      $("live-note").textContent = "기관 서버가 점검 중이거나 연결이 끊겼습니다. 잠시 뒤 다시 눌러 주세요.";
    });
  }

  /* ---------- 단체방 글 ---------- */
  function copyText() {
    if (!last) return;
    var e = last.e;
    var how = state.mode === "bus" ? "버스 내려서 모이는 시간" : state.mode === "car" ? "주차장 도착" : "공원 도착";
    var v = V.venues[e.venue];
    var lines = ["[" + dateLabel(e.date) + " " + e.title + "]", "공연장: " + e.venue + " (시작 " + e.start + ")"];
    if (last.ok) {
      lines.push(how + ": " + fmt(last.w0) + "-" + fmt(last.w1) + " (공연 시작 " + korDur(last.lead) + " 전, 인솔자가 고른 시간)");
      lines.push("과거에 가장 몰린 30분: " + fmt(last.b0) + "-" + fmt(last.b1));
    } else if (state.mode === "transit") {
      lines.push("모이는 출구: 5·9호선 올림픽공원역 3·4번 출구");
    }
    lines.push("모이는 곳: ________ (인솔자가 적어 주세요)");
    if (v) lines.push("가까운 문: " + v.gates.join("·"));
    if (state.mode === "car") lines.push("지하철: 5·9호선 올림픽공원역 3·4번 출구");
    lines.push("(2024년 7월 공연 날 공원 전체 차량 기록으로 본 참고예요)");
    var text = lines.join("\n");
    var done = function () { $("copied").textContent = "복사했어요. 단체방에 붙여 넣으세요."; };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    else { fallback(text); done(); }
  }
  function fallback(t) {
    var ta = document.createElement("textarea"); ta.value = t; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (x) { /* 무시 */ }
    ta.remove();
  }

  /* ---------- 시작 ---------- */
  Promise.all(["data/model.json", "data/events.json", "data/venues.json", "data/rule_check.json"].map(function (u) {
    return fetch(u).then(function (r) { return r.json(); });
  })).then(function (a) {
    M = a[0]; EVENTS = DEMO ? demoEvents() : a[1]; V = a[2]; R = a[3];
    renderEvents();
    var age = (Date.now() - new Date(M.built).getTime()) / 864e5;
    if (!DEMO && age > 14) {
      var w = el("p", "stale", "공연 목록이 " + Math.floor(age) + "일 전 자료예요. 새 공연은 '직접 넣기'로 확인해 주세요.");
      $("event-list").parentNode.insertBefore(w, $("event-list"));
    }
    bindChoices();
    if (params.get("auto") === "1") { // 화면 녹화용
      var ev = EVENTS.find(function (x) { return x.start; });
      if (ev) { pick(ev); showResult(); }
    }
  }).catch(function () {
    $("event-list").textContent = "자료를 불러오지 못했습니다. 새로고침해 주세요.";
  });
})();
