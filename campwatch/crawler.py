import time
import random
import logging
import requests
from models import get_db, init_db

# foresttrip 로그인 세션 캐시: {user_id: (session, fetched_at)}
_FT_SESSION_CACHE = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

GOCAMPING_API_KEY = 'YOUR_GOCAMPING_API_KEY'
GOCAMPING_BASE    = 'https://apis.data.go.kr/B551011/GoCamping'

KNPS_CAMPS = {
    "B131002": ("백운동", "가야산"), "B131001": ("삼정", "가야산"), "B131003": ("치인", "가야산"),
    "B161004": ("갑사", "계룡산"), "B161001": ("동학사", "계룡산"),
    "B041001": ("가인", "내장산"), "B042001": ("내장", "내장산"), "B042004": ("내장호", "내장산"),
    "B091004": ("구계등", "다도해해상"), "B092003": ("시목", "다도해해상"),
    "B091003": ("염포", "다도해해상"), "B091001": ("팔영산", "다도해해상"),
    "B051002": ("덕유대1", "덕유산"), "B051007": ("덕유대2", "덕유산"), "B051006": ("덕유대3", "덕유산"),
    "B172002": ("도원", "무등산"),
    "B181002": ("고사포1", "변산반도"), "B181004": ("고사포2", "변산반도"), "B181005": ("직소천", "변산반도"),
    "B141003": ("사기막", "북한산"),
    "B031005": ("설악동", "설악산"),
    "B122001": ("남천", "소백산"), "B121001": ("삼가", "소백산"),
    "B061001": ("소금강산", "오대산"),
    "B111003": ("닷돈재1", "월악산"), "B111001": ("닷돈재2", "월악산"), "B111007": ("덕주", "월악산"),
    "B111002": ("송계", "월악산"), "B111004": ("용하", "월악산"), "B111008": ("하선암", "월악산"),
    "B201001": ("천황", "월출산"),
    "B071001": ("상의", "주왕산"),
    "B011005": ("내원", "지리산"), "B012005": ("달궁1", "지리산"), "B012002": ("달궁2", "지리산"),
    "B012003": ("덕동", "지리산"), "B011007": ("백무동", "지리산"), "B011006": ("소막골", "지리산"),
    "B012010": ("학천", "지리산"),
    "B101001": ("구룡", "치악산"), "B101002": ("금대", "치악산"),
    "B221004": ("소도", "태백산"),
    "B081002": ("몽산포", "태안해안"), "B081001": ("학암포", "태안해안"),
    "B252001": ("갓바위", "팔공산"), "B251001": ("도학", "팔공산"),
    "B022003": ("덕신", "한려해상"), "B021001": ("학동", "한려해상"),
}


def get_foresttrip_session_for_user(user_id):
    """foresttrip.go.kr에 로그인한 세션 반환. 1시간마다 갱신, 실패 시 None."""
    from bs4 import BeautifulSoup as BS
    now = time.time()
    cached = _FT_SESSION_CACHE.get(user_id)
    if cached and now - cached[1] < 3600:
        return cached[0]

    db = get_db()
    user = db.execute("SELECT foresttrip_id, foresttrip_pw FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()

    if not user or not user["foresttrip_id"] or not user["foresttrip_pw"]:
        return None

    s = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.foresttrip.go.kr/"
    }
    try:
        r = s.get("https://www.foresttrip.go.kr/", headers=headers, timeout=10)
        soup = BS(r.text, "lxml")
        csrf = ""
        csrf_tag = soup.find("meta", {"name": "_csrf"}) or soup.find("input", {"name": "_csrf"})
        if csrf_tag:
            csrf = csrf_tag.get("content") or csrf_tag.get("value", "")

        r2 = s.post("https://www.foresttrip.go.kr/member/login/memberLoginProc.do",
                    data={"userId": user["foresttrip_id"], "userPwd": user["foresttrip_pw"], "_csrf": csrf},
                    headers=headers, timeout=10, allow_redirects=True)

        if "logout" in r2.text.lower() or "로그아웃" in r2.text:
            log.info(f"foresttrip login ok (user_id={user_id})")
            _FT_SESSION_CACHE[user_id] = (s, now)
            return s
        log.warning(f"foresttrip login failed (user_id={user_id})")
        return None
    except Exception as e:
        log.warning(f"foresttrip login error (user_id={user_id}): {e}")
        return None


def send_telegram(msg, token='', chat_id=''):
    if not token or not chat_id:
        log.warning('telegram not configured')
        return
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': msg},
            timeout=10
        )
        if resp.json().get('ok'):
            log.info(f'telegram sent -> {chat_id}')
        else:
            log.warning(f'telegram failed: {resp.json()}')
    except Exception as e:
        log.warning(f'telegram error: {e}')


def check_knps_availability(zone_id, date):
    from bs4 import BeautifulSoup as BS
    date_compact = date.replace("-", "")
    camp_info = KNPS_CAMPS.get(zone_id, (zone_id, ""))
    dept_name, parent_dept_name = camp_info if isinstance(camp_info, tuple) else (camp_info, "")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://res.knps.or.kr/reservation/searchSimpleCampReservation.do",
    }
    try:
        s = requests.Session()
        s.get("https://res.knps.or.kr/reservation/searchSimpleCampReservation.do",
              headers=headers, timeout=15)
        resp = s.post(
            "https://res.knps.or.kr/reservation/campsiteList.do",
            headers={**headers, "AJAX": "true",
                     "X-Requested-With": "XMLHttpRequest",
                     "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            data={"dept_id": zone_id, "dept_name": dept_name,
                  "parent_dept_name": parent_dept_name,
                  "prd_ctg_id": "", "isGreenpoint": "N"},
            timeout=20,
        )
        soup = BS(resp.text, "lxml")
        available = []
        for el in soup.find_all(attrs={"data-use_df": date_compact}):
            if el.get("data-reser_tp") in ("R", "W"):
                title = el.get("data-title") or el.get("data-prod-id") or ""
                if title and title not in available:
                    available.append(title)
        return available
    except Exception as e:
        log.warning(f"knps check error [{zone_id}]: {e}")
        return []


def check_foresttrip_availability(camp_name, site_name, zone_id, check_in, check_out, nights=1, user_id=None):
    """숲나들e 빈자리 조회 (srchInsttId 방식). 가용 슬롯 목록 반환, 오류 시 []."""
    from bs4 import BeautifulSoup as BS
    from datetime import datetime as _dt, timedelta
    if not zone_id:
        return []
    date_str = check_in.replace("-", "")
    try:
        end_str = (_dt.strptime(date_str, "%Y%m%d") + timedelta(days=nights)).strftime("%Y%m%d")
    except Exception:
        return []

    s = None
    if user_id:
        s = get_foresttrip_session_for_user(user_id)
    if s is None:
        s = requests.Session()
        s.get("https://www.foresttrip.go.kr/", timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    try:
        url = "https://www.foresttrip.go.kr/rep/or/sssn/fcfsRsrvtPssblGoodsDetls.do"
        params = {
            "srchInsttId": zone_id,
            "srchRsrvtBgDt": date_str,
            "srchRsrvtEdDt": end_str,
            "srchStngNofpr": "2",
            "srchSthngCnt": "1",
            "rsrvtPssblYn": "N",
            "menuId": "001001",
            "hmpgId": "FRIP",
        }
        r = s.get(url, params=params, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.foresttrip.go.kr/",
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        soup = BS(r.text, "lxml")
        available_count = len(soup.find_all(string=lambda t: t and '예약하기' in t))
        if available_count == 0:
            available_count = len([tag for tag in soup.find_all(['a', 'button'])
                                   if '예약하기' in tag.get_text()])
        return [f'예약가능-{i+1}' for i in range(available_count)]
    except Exception as e:
        log.warning(f"foresttrip check error [{camp_name}]: {e}")
        return []


def check_availability(camp_name, site_name, check_in, check_out):
    available = []
    if GOCAMPING_API_KEY and GOCAMPING_API_KEY != 'YOUR_GOCAMPING_API_KEY':
        try:
            r = requests.get(f'{GOCAMPING_BASE}/basedList', params={
                'serviceKey': GOCAMPING_API_KEY,
                'numOfRows': 10, 'pageNo': 1,
                'MobileOS': 'ETC', 'MobileApp': 'CampWatch',
                '_type': 'json', 'keyword': camp_name
            }, timeout=15)
            items = r.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if camp_name.lower() not in item.get('facltNm', '').lower():
                    continue
                avail_r = requests.get(f'{GOCAMPING_BASE}/availableList', params={
                    'serviceKey': GOCAMPING_API_KEY,
                    'numOfRows': 100, 'pageNo': 1,
                    'MobileOS': 'ETC', 'MobileApp': 'CampWatch',
                    '_type': 'json',
                    'contentId': item.get('contentId'),
                    'checkin': check_in.replace('-', ''),
                    'checkout': check_out.replace('-', '')
                }, timeout=15)
                avail_items = avail_r.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
                if isinstance(avail_items, dict):
                    avail_items = [avail_items]
                for a in avail_items:
                    site = a.get('siteName', a.get('siteNo', ''))
                    if not site_name or site_name in str(site):
                        available.append(f"{item.get('facltNm')} - {site}")
        except Exception as e:
            log.error(f'gocamping API error: {e}')
    else:
        log.info(f'[{camp_name}] API key not set - skip')
    return available


def run_crawler():
    init_db()
    log.info('=== CampWatch crawler start ===')

    while True:
        try:
            db = get_db()
            conditions = db.execute(
                '''SELECT wc.*, u.telegram_token, u.telegram_chat_id, u.level,
                          u.foresttrip_id, u.foresttrip_pw
                   FROM watch_conditions wc
                   JOIN users u ON wc.user_id = u.id
                   WHERE wc.active = 1'''
            ).fetchall()
            db.close()

            max_level = max((c['level'] or 1 for c in conditions), default=1)
            if max_level >= 3:
                delay_min, delay_max = 30, 60
            elif max_level == 2:
                delay_min, delay_max = 60, 180
            else:
                delay_min, delay_max = 180, 300

            log.info(f'active conditions: {len(conditions)}, max level: {max_level}, delay: {delay_min}~{delay_max}s')

            for cond in conditions:
                cid      = cond['id']
                camp     = cond['camp_name']
                site     = cond['site_name'] or ''
                check_in = cond['check_in']
                check_out= cond['check_out']
                zone_id  = cond['zone_id'] or ''
                nights   = cond['nights'] or 1
                token    = cond['telegram_token'] or ''
                chat_id  = cond['telegram_chat_id'] or ''
                try:
                    source = cond['source'] or 'foresttrip'
                except Exception:
                    source = 'foresttrip'

                log.info(f'check: [{camp}] {check_in}~{check_out} source={source}')

                user_id = cond['user_id']
                if source == 'knps' and zone_id:
                    available = check_knps_availability(zone_id, check_in)
                elif zone_id:
                    available = check_foresttrip_availability(camp, site, zone_id, check_in, check_out, nights, user_id=user_id)
                else:
                    available = check_availability(camp, site, check_in, check_out)

                if available:
                    src_label = 'KNPS' if source == 'knps' else 'foresttrip'
                    sites_str = ', '.join(str(s) for s in available[:5])
                    if len(available) > 5:
                        sites_str += f' +{len(available)-5}'
                    msg = (
                        f'[CampWatch {src_label}]\n'
                        f'{camp}\n'
                        f'{check_in} ~ {check_out}\n'
                        f'available: {sites_str}'
                    )
                    log.info(f'available! {available[:3]}')
                    db2 = get_db()
                    db2.execute('INSERT INTO notify_log (condition_id, message) VALUES (?, ?)', (cid, msg))
                    db2.commit()
                    db2.close()
                    send_telegram(msg, token, chat_id)
                else:
                    log.info(f'no availability: [{camp}]')

                time.sleep(random.uniform(3, 8))

        except Exception as e:
            log.error(f'crawler error: {e}')

        wait = random.uniform(delay_min, delay_max)
        log.info(f'next check in {wait:.0f}s')
        time.sleep(wait)


if __name__ == '__main__':
    run_crawler()
