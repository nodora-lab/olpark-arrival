# 공공데이터 원본 내려받기 (서비스키 필요 없음)
# 실행: python scripts/fetch_data.py   (저장소 맨 위 폴더에서)
# 1) 공공데이터포털 파일데이터 4종 (한국체육산업개발(주) 제공)
# 2) 올림픽공원 홈페이지 공연 안내 화면이 쓰는 공개 목록(월별)
import json, os, re, sys, urllib.request, datetime as dt

UA = {"User-Agent": "Mozilla/5.0 (olpark-arrival data fetch)"}
RAW = os.path.join("data", "raw")
FILES = {
    # 포털 번호: 저장 이름
    "15138735": "inout_202407.csv",              # 올림픽공원 입출차 정보 (2024-07 한 달)
    "15164156": "parking_congestion_20260812.csv",  # 주차장 혼잡도 정보
    "15149169": "perf_en_20260901.csv",          # 영문 공연정보
    "15131671": "monthly_parking_20260727.csv",  # 월별주차현황
}


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def to_utf8(b):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def fetch_portal(pk, name):
    page = get(f"https://www.data.go.kr/data/{pk}/fileData.do").decode("utf-8", "replace")
    detail = re.search(r'id="publicDataDetailPk" name="publicDataDetailPk" value="([^"]+)"', page).group(1)
    meta = json.loads(get(
        "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"
        f"?publicDataPk={pk}&publicDataDetailPk={detail}&fileDetailSn=1"))
    atch = meta["atchFileId"]
    sn = meta.get("fileDetailSn", 1)
    b = get(f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={atch}&fileDetailSn={sn}")
    with open(os.path.join(RAW, name), "w", encoding="utf-8") as f:
        f.write(to_utf8(b))
    print("ok", pk, name)


def fetch_events(months):
    os.makedirs(os.path.join(RAW, "ev"), exist_ok=True)
    for ym in months:
        body = json.dumps({"nowYM": ym, "plcCd": ""}).encode()
        b = get("https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListAjax.es", data=body,
                headers={"Content-Type": "application/json;charset=UTF-8"})
        with open(os.path.join(RAW, "ev", f"{ym}.json"), "wb") as f:
            f.write(b)
    print("ok events", months[0], "-", months[-1])


if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    for pk, name in FILES.items():
        fetch_portal(pk, name)
    today = dt.date.today()
    months = []
    y, m = 2024, 1
    while (y, m) <= (today.year + (today.month + 2 > 12), (today.month + 2 - 1) % 12 + 1):
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    fetch_events(months)
