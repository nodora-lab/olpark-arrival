# 올림픽공원 공연 일정(기관 홈페이지 공연 안내 화면의 공개 목록)을 날짜·공연장·시작 시각 행으로 바꾼다.
# 실행: python scripts/parse_events.py  (저장소 맨 위 폴더에서)
import json, glob, re, datetime as dt, csv
WD='월화수목금토일'
EN={'MON':0,'TUE':1,'WED':2,'THU':3,'FRI':4,'SAT':5,'SUN':6}
def norm_venue(p):
    p=(p or '').replace('　',' ').strip()
    for k,v in [('KSPO','KSPO DOME'),('체조','KSPO DOME'),('올림픽홀','올림픽홀'),('핸드볼','핸드볼경기장'),('우리금융','우리금융아트홀'),('뮤즈','뮤즈라이브'),('K-아트','K-아트홀'),('K아트','K-아트홀'),('잔디','88잔디마당'),('수변','88호수수변무대'),('평화의','평화의 광장'),('티켓링크','티켓링크 라이브 아레나'),('테니스','테니스장')]:
        if k in p: return v
    return p or '기타'
TIME=re.compile(r'(오후|오전|PM|AM|pm|am)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시\s*(?:(\d{1,2})\s*분)?|\s*(PM|AM|pm|am))')
def to_min(m):
    ap1,h,ap2=m.group(1),int(m.group(2)),m.group(5)
    mi=m.group(3) or m.group(4)
    mi=int(mi) if mi and mi.isdigit() else 0
    ap=(ap1 or ap2 or '').upper()
    if ap in ('오후','PM') and h<12: h+=12
    if not ap and 1<=h<=10: h+=12  # 공연은 오후로 가정 (11시 공연은 그대로)
    if h>23 or mi>59: return None
    return h*60+mi
def mentioned(s,d):
    w=WD[d.weekday()]
    has_dates=bool(re.search(r'\d{1,2}월\s*\d{1,2}일|\d{1,2}\s*\.\s*\d{1,2}',s))
    if has_dates:
        return bool(re.search(rf'(?<!\d){d.month}월\s*0?{d.day}일|(?<![\d.]){d.month}\s*\.\s*0?{d.day}(?!\d)|(?<!\d){d.day}일',s))
    has_wd=bool(re.search(r'[월화수목금토일]\)|\([월화수목금토일]|[월화수목금토일]\s*(오후|\d)|토일|토·일|평일|주말|월.금',s))
    if has_wd:
        if d.weekday()<5 and re.search(r'평일|월\s*[~-]\s*금',s): return True
        if d.weekday()>=5 and re.search(r'주말|토일|토·일',s): return True
        return bool(re.search(rf'\(?{w}\)?\s*(오후|오전|\d|\))|\({w}\)',s))
    return True
def start_for(tm,d,ndays):
    s=tm or ''
    if ndays>1 and not mentioned(s,d): return -1
    w=WD[d.weekday()]
    cands=[]
    # 날짜 표기 (11월 13일, 11.13, 2026.11.21)
    for pat in [rf'{d.month}월\s*{d.day}일[^0-9]{{0,12}}', rf'{d.month}\.\s*{d.day}\.?\s*\(?[^0-9]{{0,8}}', rf'{d.year}\.{d.month}\.{d.day}\.?[^0-9]{{0,10}}']:
        for m in re.finditer(pat,s):
            t=TIME.search(s,m.end()); 
            if t and t.start()-m.end()<25: cands.append(to_min(t))
    if not cands:
        for m in re.finditer(r'\(?'+w+r'\)?',s):
            t=TIME.search(s,m.end())
            if t and t.start()-m.end()<12: cands.append(to_min(t)); break
    if not cands:
        en=[k for k,v in EN.items() if v==d.weekday()][0]
        m=re.search(en,s.upper())
        if m:
            t=TIME.search(s,m.end()); 
            if t and t.start()-m.end()<12: cands.append(to_min(t))
    if not cands:
        ts=[to_min(t) for t in TIME.finditer(s)]
        ts=[x for x in ts if x]
        if len(set(ts))==1 or (ndays==1 and ts): cands.append(ts[0])
        elif ndays>1 and d.weekday()<5:
            # 평일 문구
            m=re.search(r'평일',s); t=TIME.search(s,m.end()) if m else None
            if t: cands.append(to_min(t))
        elif ndays>1:
            m=re.search(r'주말|토[·,/]?일',s); t=TIME.search(s,m.end()) if m else None
            if t: cands.append(to_min(t))
    c=[x for x in cands if x]
    return c[0] if c else None
seen={}
for f in sorted(glob.glob('data/raw/ev/*.json')):
    for grp in json.load(open(f,encoding='utf-8')):
        for it in grp: seen[it['evtSeq']]=it
rows=[]
for it in seen.values():
    b=dt.date.fromisoformat(it['beginDt']); e=dt.date.fromisoformat(it['endDt'])
    n=(e-b).days+1
    v=norm_venue(it.get('plc'))
    if n>45: continue  # 장기 상설 공연 제외
    for k in range(n):
        d=b+dt.timedelta(days=k)
        st=start_for(it.get('tm'),d,n)
        if st==-1: continue
        rows.append({'date':d.isoformat(),'venue':v,'title':it['title'],'start':(f'{st//60:02d}:{st%60:02d}' if st is not None else ''),'tm':(it.get('tm') or '').replace('\n',' '),'evtSeq':it['evtSeq'],'n':n})
rows.sort(key=lambda r:(r['date'],r['venue']))
with open('data/events_all.csv','w',encoding='utf-8-sig',newline='') as fp:
    w=csv.DictWriter(fp,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(seen),len(rows), sum(1 for r in rows if not r['start']), file=open('data/parse_stats.txt','w'))
