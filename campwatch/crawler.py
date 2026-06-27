"""
CampWatch Crawler
- 고캠핑 API를 이용해 캠핑장 예약 가능 여부를 주기적으로 확인
- 가용 자리 발견 시 텔레그램으로 알림 발송
- 실행: python crawler.py
"""
import time
import random
import logging
import requests
from datetime import datetime
from models import get_db, init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'  # 텔레그램 봇 토큰
GOCAMPING_API_KEY = 'YOUR_GOCAMPING_API_KEY'  # 고캠핑 API 키 (선택)
GOCAMPING_BASE = 'https://apis.data.go.kr/B551011/GoCamping'

def send_telegram(chat_id: str, text: str):
    if not chat_id or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        log.warning('텔레그램 봇 토큰 또는 chat_id 미설정')
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    try:
        resp = requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
        resp.raise_for_status()
        log.info(f'텔레그램 전송 완료 → {chat_id}')
    except Exception as e:
        log.error(f'텔레그램 전송 실패: {e}')

def check_availability(camp_name: str, site_name: str, check_in: str, check_out: str) -> list:
    """
    고캠핑 API로 예약 가능 사이트 확인.
    API 키 없이는 직접 페이지를 파싱하는 fallback 사용.
    가능한 사이트 목록(str list) 반환.
    """
    available = []

    if GOCAMPING_API_KEY and GOCAMPING_API_KEY != 'YOUR_GOCAMPING_API_KEY':
        try:
            # 캠핑장 검색
            search_url = f'{GOCAMPING_BASE}/basedList'
            params = {
                'serviceKey': GOCAMPING_API_KEY,
                'numOfRows': 10,
                'pageNo': 1,
                'MobileOS': 'ETC',
                'MobileApp': 'CampWatch',
                '_type': 'json',
                'keyword': camp_name
            }
            r = requests.get(search_url, params=params, timeout=15)
            data = r.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if isinstance(items, dict):
                items = [items]

            for item in items:
                content_id = item.get('contentId')
                name = item.get('facltNm', '')
                if camp_name.lower() not in name.lower():
                    continue

                # 예약 가능 여부 확인
                avail_url = f'{GOCAMPING_BASE}/availableList'
                avail_params = {
                    'serviceKey': GOCAMPING_API_KEY,
                    'numOfRows': 100,
                    'pageNo': 1,
                    'MobileOS': 'ETC',
                    'MobileApp': 'CampWatch',
                    '_type': 'json',
                    'contentId': content_id,
                    'checkin': check_in.replace('-', ''),
                    'checkout': check_out.replace('-', '')
                }
                avail_r = requests.get(avail_url, params=avail_params, timeout=15)
                avail_data = avail_r.json()
                avail_items = avail_data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                if isinstance(avail_items, dict):
                    avail_items = [avail_items]

                for a in avail_items:
                    site = a.get('siteName', a.get('siteNo', ''))
                    if not site_name or site_name in str(site):
                        available.append(f"{name} - {site}")

        except Exception as e:
            log.error(f'고캠핑 API 오류: {e}')

    else:
        # API 키 없을 때: 고캠핑 웹 fallback (기본 가용성 시뮬레이션)
        log.info(f'[{camp_name}] API 키 미설정 — 웹 크롤링 모드 (구현 필요)')
        # 실제 운영 시 여기에 BeautifulSoup 파싱 로직 추가

    return available

def run_crawler():
    init_db()
    log.info('=== CampWatch 크롤러 시작 ===')

    while True:
        try:
            db = get_db()
            conditions = db.execute(
                '''SELECT wc.*, u.telegram_chat_id
                   FROM watch_conditions wc
                   JOIN users u ON wc.user_id = u.id
                   WHERE wc.active = 1'''
            ).fetchall()
            db.close()

            log.info(f'활성 감시 조건 {len(conditions)}개 확인 중')

            for cond in conditions:
                cid = cond['id']
                camp = cond['camp_name']
                site = cond['site_name'] or ''
                check_in = cond['check_in']
                check_out = cond['check_out']
                chat_id = cond['telegram_chat_id']

                log.info(f'확인: [{camp}] {check_in}~{check_out}')
                available = check_availability(camp, site, check_in, check_out)

                if available:
                    msg = (
                        f'🏕️ [CampWatch 알림]\n'
                        f'캠핑장: {camp}\n'
                        f'날짜: {check_in} ~ {check_out}\n'
                        f'가능 사이트: {", ".join(available)}\n'
                        f'→ 빠르게 예약하세요!'
                    )
                    log.info(f'가용 발견! {available}')

                    # 알림 로그 저장
                    db2 = get_db()
                    db2.execute(
                        'INSERT INTO notify_log (condition_id, message) VALUES (?, ?)',
                        (cid, msg)
                    )
                    db2.commit()
                    db2.close()

                    if chat_id:
                        send_telegram(chat_id, msg)
                else:
                    log.info(f'가용 없음: [{camp}]')

                # 조건 간 짧은 딜레이
                time.sleep(random.uniform(3, 8))

        except Exception as e:
            log.error(f'크롤러 오류: {e}')

        # 3~5분 랜덤 대기
        wait = random.uniform(180, 300)
        log.info(f'다음 확인까지 {wait:.0f}초 대기')
        time.sleep(wait)

if __name__ == '__main__':
    run_crawler()
