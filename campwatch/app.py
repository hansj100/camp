from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import get_db, init_db
from crypto import encrypt_text, decrypt_text
from datetime import datetime as _dt, timedelta
import functools
import bcrypt

app = Flask(__name__)
app.secret_key = 'campwatch-secret-change-me'

APP_VERSION = "1.6.0"
APP_BUILD   = "2026-06-28"

init_db()

@app.template_filter('todatetime')
def todatetime_filter(s):
    try:
        return _dt.strptime(s[:10], '%Y-%m-%d')
    except Exception:
        return _dt.now()

@app.context_processor
def inject_globals():
    return {"app_version": APP_VERSION, "app_build": APP_BUILD, "now": _dt.now()}

# ── 데코레이터 ────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('관리자만 접근 가능합니다.')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ── 기본 라우트 ───────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
        if not username or not password:
            flash('아이디와 비밀번호를 입력하세요.')
            return render_template('register.html')
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (username, password, telegram_chat_id, is_approved, is_admin) VALUES (?, ?, ?, 0, 0)',
                (username, hashed, telegram_chat_id or None)
            )
            db.commit()
            flash('가입 신청이 완료됐습니다. 관리자 승인 후 로그인 가능합니다.')
            return redirect(url_for('login'))
        except Exception:
            flash('이미 사용 중인 아이디입니다.')
        finally:
            db.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()
        if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
            if user['is_approved'] != 1:
                flash('관리자 승인 대기 중입니다. 잠시 후 다시 시도해 주세요.')
                return render_template('login.html')
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('index'))
        flash('아이디 또는 비밀번호가 틀렸습니다.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── 대시보드 ──────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    conditions = db.execute(
        'SELECT * FROM watch_conditions WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    logs = db.execute(
        '''SELECT nl.notified_at, nl.message, wc.camp_name
           FROM notify_log nl
           JOIN watch_conditions wc ON nl.condition_id = wc.id
           WHERE wc.user_id = ?
           ORDER BY nl.notified_at DESC LIMIT 20''',
        (session['user_id'],)
    ).fetchall()
    favs = db.execute(
        'SELECT * FROM favorites WHERE user_id=? LIMIT 5',
        (session['user_id'],)
    ).fetchall()
    db.close()

    today = _dt.now().date()
    days_until_sat = (5 - today.weekday()) % 7
    if days_until_sat == 0:
        days_until_sat = 7
    this_sat = today + timedelta(days=days_until_sat)
    next_sat = this_sat + timedelta(days=7)

    return render_template('dashboard.html', conditions=conditions, logs=logs,
                           favorites=favs, this_sat=str(this_sat), next_sat=str(next_sat))

# ── 감시 조건 ─────────────────────────────────────────────
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        camp_name = request.form['camp_name'].strip()
        site_name = request.form.get('site_name', '').strip()
        check_in  = request.form['check_in']
        check_out = request.form['check_out']
        if not camp_name or not check_in or not check_out:
            flash('캠핑장명과 날짜를 입력하세요.')
            return render_template('add.html')
        db = get_db()
        db.execute(
            'INSERT INTO watch_conditions (user_id, camp_name, site_name, check_in, check_out) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], camp_name, site_name or None, check_in, check_out)
        )
        db.commit()
        db.close()
        flash('감시 조건이 추가됐습니다.')
        return redirect(url_for('dashboard'))
    return render_template('add.html')

@app.route('/delete/<int:cid>', methods=['POST'])
@login_required
def delete(cid):
    db = get_db()
    db.execute('DELETE FROM watch_conditions WHERE id = ? AND user_id = ?', (cid, session['user_id']))
    db.commit()
    db.close()
    flash('삭제됐습니다.')
    return redirect(url_for('dashboard'))

@app.route('/toggle/<int:cid>', methods=['POST'])
@login_required
def toggle(cid):
    db = get_db()
    cond = db.execute('SELECT active FROM watch_conditions WHERE id = ? AND user_id = ?', (cid, session['user_id'])).fetchone()
    if cond:
        db.execute('UPDATE watch_conditions SET active = ? WHERE id = ?', (0 if cond['active'] else 1, cid))
        db.commit()
    db.close()
    return redirect(url_for('dashboard'))

@app.route('/quick-add', methods=['POST'])
@login_required
def quick_add():
    camp_name = request.form['camp_name'].strip()
    site_name = request.form.get('site_name', '').strip() or None
    check_in  = request.form['check_in'].strip()
    check_out = request.form['check_out'].strip()
    nights    = int(request.form.get('nights', 1))
    zone_id   = request.form.get('zone_id', '').strip()
    source    = request.form.get('source', 'foresttrip').strip()
    if source not in ('foresttrip', 'knps'):
        source = 'foresttrip'
    if not zone_id and source == 'foresttrip':
        flash('Zone ID를 입력해 주세요. 숲나들e 예약 페이지 URL에서 확인하세요.', 'error')
        return redirect(url_for('campsites_page'))
    if not camp_name or not check_in or not check_out:
        flash('입력값을 확인해 주세요.')
        return redirect(url_for('campsites_page'))
    db = get_db()
    db.execute(
        'INSERT INTO watch_conditions (user_id, camp_name, site_name, check_in, check_out, nights, zone_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (session['user_id'], camp_name, site_name, check_in, check_out, nights, zone_id, source)
    )
    db.commit()
    db.close()
    flash(f"'{camp_name}' 알림이 등록됐습니다!")
    return redirect(url_for('dashboard'))

# ── 설정 ──────────────────────────────────────────────────
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    if request.method == 'POST':
        telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
        db.execute('UPDATE users SET telegram_chat_id = ? WHERE id = ?', (telegram_chat_id or None, session['user_id']))
        db.commit()
        flash('저장됐습니다.')
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    db.close()
    return render_template('settings.html', user=user)

@app.route('/settings/telegram', methods=['GET', 'POST'])
@login_required
def telegram_settings():
    msg = None
    chat_id_found = None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    db.close()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'find_chatid':
            token = request.form.get('bot_token', '').strip()
            if token:
                import requests as _req
                try:
                    r = _req.get(f'https://api.telegram.org/bot{token}/getUpdates', timeout=10)
                    data = r.json()
                    updates = data.get('result', [])
                    if updates:
                        last = updates[-1]
                        chat = last.get('message', last.get('channel_post', {})).get('chat', {})
                        chat_id_found = chat.get('id')
                        chat_name = chat.get('first_name', '') or chat.get('title', '')
                        msg = f'✅ Chat ID 찾음: {chat_id_found} ({chat_name})'
                    else:
                        msg = '⚠ 메시지 없음. 봇에게 아무 메시지나 보낸 후 다시 시도하세요.'
                except Exception as e:
                    msg = f'❌ 오류: {e}'

        elif action == 'save':
            token   = request.form.get('bot_token', '').strip()
            chat_id = request.form.get('chat_id', '').strip()
            db = get_db()
            db.execute('UPDATE users SET telegram_token=?, telegram_chat_id=? WHERE id=?',
                       (token or None, chat_id or None, session['user_id']))
            db.commit()
            db.close()
            flash('텔레그램 설정이 저장됐습니다.')
            return redirect(url_for('telegram_settings'))

        elif action == 'test':
            db = get_db()
            user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
            db.close()
            token   = user['telegram_token'] or ''
            chat_id = user['telegram_chat_id'] or ''
            if token and chat_id:
                import requests as _req
                try:
                    r = _req.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                  data={'chat_id': chat_id, 'text': '🏕️ CampWatch 테스트 알림입니다!'}, timeout=10)
                    if r.json().get('ok'):
                        msg = '✅ 텔레그램 테스트 메시지를 보냈습니다.'
                    else:
                        msg = f'❌ 전송 실패: {r.json()}'
                except Exception as e:
                    msg = f'❌ 오류: {e}'
            else:
                msg = '❌ 봇 토큰과 Chat ID를 먼저 저장해 주세요.'

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    db.close()
    return render_template('telegram.html', user=user, msg=msg, chat_id_found=chat_id_found)

@app.route('/settings/foresttrip', methods=['GET', 'POST'])
@login_required
def settings_foresttrip():
    db = get_db()
    if request.method == 'POST':
        fid = request.form.get('foresttrip_id', '').strip()
        fpw = request.form.get('foresttrip_pw', '').strip()
        if fid and fpw:
            # 아이디+비밀번호 둘 다 입력 → 둘 다 갱신
            db.execute('UPDATE users SET foresttrip_id=?, foresttrip_pw=? WHERE id=?',
                       (encrypt_text(fid), encrypt_text(fpw), session['user_id']))
        elif fid:
            # 아이디만 입력 → 아이디만 갱신 (비밀번호 유지)
            db.execute('UPDATE users SET foresttrip_id=? WHERE id=?',
                       (encrypt_text(fid), session['user_id']))
        elif not fid and not fpw:
            # 둘 다 비움 → 연동 해제
            db.execute('UPDATE users SET foresttrip_id=NULL, foresttrip_pw=NULL WHERE id=?',
                       (session['user_id'],))
        db.commit()
        flash('저장됐습니다.', 'success')
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    db.close()
    foresttrip_id_display = decrypt_text(user['foresttrip_id']) if user['foresttrip_id'] else None
    return render_template('settings_foresttrip.html', user=user,
                           foresttrip_id_display=foresttrip_id_display)

@app.route('/restart', methods=['POST'])
@login_required
@admin_required
def restart_server():
    import subprocess, threading, os
    def do_restart():
        import time
        time.sleep(1)
        cwd = os.path.dirname(__file__)
        # GitHub에서 최신 코드 pull
        try:
            subprocess.run(
                ['git', 'pull', 'origin', 'main'],
                cwd=cwd, timeout=30, capture_output=True
            )
        except Exception:
            pass
        # restart.sh 실행 (Flask + crawler 재시작)
        script = os.path.join(cwd, 'restart.sh')
        subprocess.Popen(['bash', script])
    threading.Thread(target=do_restart, daemon=True).start()
    flash('GitHub에서 최신 코드를 받아 재시작합니다. 5초 후 새로고침해 주세요.')
    return redirect(url_for('dashboard'))

# ── 관리자 ────────────────────────────────────────────────
@app.route('/admin')
@login_required
@admin_required
def admin_page():
    db = get_db()
    pending  = db.execute("SELECT * FROM users WHERE is_approved=0 ORDER BY created_at DESC").fetchall()
    approved = db.execute("SELECT * FROM users WHERE is_approved=1 AND is_admin=0 ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template('admin.html', pending=pending, approved=approved)

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_approved=1 WHERE id=?", (user_id,))
    db.commit()
    db.close()
    flash('승인됐습니다.')
    return redirect(url_for('admin_page'))

@app.route('/admin/reject/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reject_user(user_id):
    db = get_db()
    db.execute("UPDATE users SET is_approved=-1 WHERE id=?", (user_id,))
    db.commit()
    db.close()
    flash('거부됐습니다.')
    return redirect(url_for('admin_page'))

@app.route('/admin/level/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def set_level(user_id):
    level = int(request.form.get('level', 1))
    db = get_db()
    db.execute('UPDATE users SET level=? WHERE id=?', (level, user_id))
    db.commit()
    db.close()
    flash(f'레벨이 {level}로 변경됐습니다.')
    return redirect(url_for('admin_page'))

@app.route('/admin/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id=? AND is_admin=0", (user_id,))
    db.commit()
    db.close()
    flash('삭제됐습니다.')
    return redirect(url_for('admin_page'))

# ── 캠핑장 검색 ───────────────────────────────────────────
CAMPSITE_CACHE = {"data": [], "fetched_at": 0}
KNPS_CACHE     = {"data": [], "fetched_at": 0}

# 국립공원 야영장 dept_id 매핑 (res.knps.or.kr 페이지에서 추출)
KNPS_CAMPS = {
    "B131002": {"camp":"백운동","park":"가야산","sido":"경남"},
    "B131001": {"camp":"삼정","park":"가야산","sido":"경남"},
    "B131003": {"camp":"치인","park":"가야산","sido":"경남"},
    "B161004": {"camp":"갑사","park":"계룡산","sido":"충남"},
    "B161001": {"camp":"동학사","park":"계룡산","sido":"충남"},
    "B041001": {"camp":"가인","park":"내장산","sido":"전북"},
    "B042001": {"camp":"내장","park":"내장산","sido":"전북"},
    "B042004": {"camp":"내장호","park":"내장산","sido":"전북"},
    "B091004": {"camp":"구계등","park":"다도해해상","sido":"전남"},
    "B092003": {"camp":"시목","park":"다도해해상","sido":"전남"},
    "B091003": {"camp":"염포","park":"다도해해상","sido":"전남"},
    "B091001": {"camp":"팔영산","park":"다도해해상","sido":"전남"},
    "B051002": {"camp":"덕유대1","park":"덕유산","sido":"전북"},
    "B051007": {"camp":"덕유대2","park":"덕유산","sido":"전북"},
    "B051006": {"camp":"덕유대3","park":"덕유산","sido":"전북"},
    "B172002": {"camp":"도원","park":"무등산","sido":"광주"},
    "B181002": {"camp":"고사포1","park":"변산반도","sido":"전북"},
    "B181004": {"camp":"고사포2","park":"변산반도","sido":"전북"},
    "B181005": {"camp":"직소천","park":"변산반도","sido":"전북"},
    "B141003": {"camp":"사기막","park":"북한산","sido":"경기"},
    "B031005": {"camp":"설악동","park":"설악산","sido":"강원"},
    "B122001": {"camp":"남천","park":"소백산","sido":"충북"},
    "B121001": {"camp":"삼가","park":"소백산","sido":"충북"},
    "B061001": {"camp":"소금강산","park":"오대산","sido":"강원"},
    "B111003": {"camp":"닷돈재1","park":"월악산","sido":"충북"},
    "B111001": {"camp":"닷돈재2","park":"월악산","sido":"충북"},
    "B111007": {"camp":"덕주","park":"월악산","sido":"충북"},
    "B111002": {"camp":"송계","park":"월악산","sido":"충북"},
    "B111004": {"camp":"용하","park":"월악산","sido":"충북"},
    "B111008": {"camp":"하선암","park":"월악산","sido":"충북"},
    "B201001": {"camp":"천황","park":"월출산","sido":"전남"},
    "B071001": {"camp":"상의","park":"주왕산","sido":"경북"},
    "B011005": {"camp":"내원","park":"지리산","sido":"경남"},
    "B012005": {"camp":"달궁1","park":"지리산","sido":"경남"},
    "B012002": {"camp":"달궁2","park":"지리산","sido":"경남"},
    "B012003": {"camp":"덕동","park":"지리산","sido":"경남"},
    "B011007": {"camp":"백무동","park":"지리산","sido":"경남"},
    "B011006": {"camp":"소막골","park":"지리산","sido":"경남"},
    "B012010": {"camp":"학천","park":"지리산","sido":"경남"},
    "B101001": {"camp":"구룡","park":"치악산","sido":"강원"},
    "B101002": {"camp":"금대","park":"치악산","sido":"강원"},
    "B221004": {"camp":"소도","park":"태백산","sido":"강원"},
    "B081002": {"camp":"몽산포","park":"태안해안","sido":"충남"},
    "B081001": {"camp":"학암포","park":"태안해안","sido":"충남"},
    "B252001": {"camp":"갓바위","park":"팔공산","sido":"경북"},
    "B251001": {"camp":"도학","park":"팔공산","sido":"경북"},
    "B022003": {"camp":"덕신","park":"한려해상","sido":"경남"},
    "B021001": {"camp":"학동","park":"한려해상","sido":"경남"},
}

FALLBACK_KNPS_CAMPSITES = [
    {
        "fcltNm": f"{v['park']}국립공원 {v['camp']}야영장",
        "zoneId": k,
        "sido": v['sido'],
        "source": "knps",
        "type": "야영장",
        "addr": "",
        "url": f"https://res.knps.or.kr/reservation/searchSimpleCampReservation.do",
    }
    for k, v in KNPS_CAMPS.items()
]

def fetch_campsites_from_foresttrip():
    import time as _time, requests as _req
    now = _time.time()
    if CAMPSITE_CACHE["data"] and now - CAMPSITE_CACHE["fetched_at"] < 3600:
        return CAMPSITE_CACHE["data"]
    campsites = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.foresttrip.go.kr/",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        resp = _req.post(
            "https://www.foresttrip.go.kr/pot/is/fs/selectFcltSrchList.do",
            headers=headers,
            data={"pageIndex":"1","pageUnit":"200","searchGb":"","sido":"","sigungu":"","fcltNm":"","hmpgId":"FRIP"},
            timeout=15,
        )
        data = resp.json()
        for item in (data.get("list") or data.get("resultList") or []):
            campsites.append({
                "fcltNm": item.get("fcltNm", ""),
                "sido":   item.get("ctpvNm", item.get("sido", "")),
                "addr":   item.get("rdnmadr", item.get("lnmadr", "")),
                "zoneId": item.get("zoneId", item.get("fcltCd", "")),
                "source": "foresttrip",
                "type":   "휴양림",
                "url":    "",
            })
    except Exception as e:
        import logging; logging.warning(f'foresttrip fetch error: {e}')
    if not campsites:
        campsites = [
            {"fcltNm":"유명산자연휴양림","zoneId":"0101","sido":"경기","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"산음자연휴양림","zoneId":"0103","sido":"경기","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"중미산자연휴양림","zoneId":"0108","sido":"경기","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"화야산자연휴양림","zoneId":"0106","sido":"경기","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"운악산자연휴양림","zoneId":"0224","sido":"경기","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"방태산자연휴양림","zoneId":"0109","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"대관령자연휴양림","zoneId":"0111","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"가리왕산자연휴양림","zoneId":"0113","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"검봉산자연휴양림","zoneId":"0244","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"용화산자연휴양림","zoneId":"0222","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"청태산자연휴양림","zoneId":"0114","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"칠갑산자연휴양림","zoneId":"0155","sido":"충남","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"만인산자연휴양림","zoneId":"0163","sido":"충남","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"장태산자연휴양림","zoneId":"0165","sido":"충남","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"운장산자연휴양림","zoneId":"0185","sido":"전북","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"변산자연휴양림","zoneId":"0189","sido":"전북","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"천관산자연휴양림","zoneId":"0196","sido":"전남","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"비슬산자연휴양림","zoneId":"0216","sido":"경북","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"축령산자연휴양림","zoneId":"0202","sido":"전남","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"민둥산자연휴양림","zoneId":"0246","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"미천골자연휴양림","zoneId":"0112","sido":"강원","addr":"","source":"foresttrip","type":"휴양림","url":""},
            {"fcltNm":"구병산자연휴양림","zoneId":"0149","sido":"충북","addr":"","source":"foresttrip","type":"휴양림","url":""},
        ]
    if campsites:
        CAMPSITE_CACHE["data"] = campsites
        CAMPSITE_CACHE["fetched_at"] = now
    return campsites

# 하위 호환성 유지
def fetch_campsites():
    return fetch_campsites_from_foresttrip()

def fetch_campsites_from_knps():
    """KNPS_CAMPS 딕셔너리에서 직접 야영장 목록 반환 (res.knps.or.kr 페이지 파싱 기반)"""
    return list(FALLBACK_KNPS_CAMPSITES)


def get_foresttrip_session(user_id):
    """foresttrip.go.kr에 로그인한 requests.Session 반환. 실패 시 None."""
    import requests as _req
    db = get_db()
    user = db.execute("SELECT foresttrip_id, foresttrip_pw FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()

    if not user or not user["foresttrip_id"] or not user["foresttrip_pw"]:
        return None

    fid = decrypt_text(user["foresttrip_id"])
    fpw = decrypt_text(user["foresttrip_pw"])
    if not fid or not fpw:
        return None

    s = _req.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.foresttrip.go.kr/"
    }
    try:
        r = s.get("https://www.foresttrip.go.kr/", headers=headers, timeout=10)
        from bs4 import BeautifulSoup as BS
        soup = BS(r.text, "lxml")
        csrf = ""
        csrf_tag = soup.find("meta", {"name": "_csrf"}) or soup.find("input", {"name": "_csrf"})
        if csrf_tag:
            csrf = csrf_tag.get("content") or csrf_tag.get("value", "")

        login_data = {
            "userId": fid,
            "userPwd": fpw,
            "_csrf": csrf,
        }
        r2 = s.post("https://www.foresttrip.go.kr/member/login/memberLoginProc.do",
                    data=login_data, headers=headers, timeout=10, allow_redirects=True)

        if "logout" in r2.text.lower() or "로그아웃" in r2.text:
            return s
        return None
    except Exception:
        return None


def check_foresttrip_availability(zone_id: str, date: str, nights: int = 1, user_id=None) -> int:
    """숲나들e 빈자리 수 반환 (srchInsttId 방식). 오류 시 -1."""
    if not zone_id:
        return -1
    from datetime import datetime as _datetime, timedelta
    import requests as _req
    from bs4 import BeautifulSoup as BS
    date_str = date.replace("-", "")
    try:
        dt = _datetime.strptime(date_str, "%Y%m%d")
        end_str = (dt + timedelta(days=nights)).strftime("%Y%m%d")
    except Exception:
        return -1

    s = None
    if user_id:
        s = get_foresttrip_session(user_id)
    if s is None:
        s = _req.Session()
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
        if r.status_code != 200:
            return -1
        soup = BS(r.text, "lxml")
        available_count = len(soup.find_all(string=lambda t: t and '예약하기' in t))
        if available_count == 0:
            available_count = len([tag for tag in soup.find_all(['a', 'button'])
                                   if '예약하기' in tag.get_text()])
        return available_count
    except Exception:
        return -1



def check_knps_availability(zone_id, date):
    """KNPS availability check. Returns count of available sites, -1 on error."""
    import requests as _req
    from bs4 import BeautifulSoup as BS

    date_compact = date.replace("-", "")
    camp_info = KNPS_CAMPS.get(zone_id, {})
    dept_name = camp_info.get("camp", zone_id)
    parent_dept_name = camp_info.get("park", "")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://res.knps.or.kr/reservation/searchSimpleCampReservation.do",
    }
    try:
        s = _req.Session()
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
        available = set()
        for el in soup.find_all(attrs={"data-use_df": date_compact}):
            if el.get("data-reser_tp") in ("R", "W"):
                key = el.get("data-title") or el.get("data-prod-id") or el.get("data-use_df")
                if key:
                    available.add(key)
        return len(available)
    except Exception as e:
        import logging; logging.warning(f"knps check error [{zone_id}]: {e}")
        return -1


@app.route('/campsites')
def campsites_page():
    region = request.args.get('region', '')
    forest_camps = fetch_campsites_from_foresttrip()
    knps_camps   = fetch_campsites_from_knps()
    all_camps    = forest_camps + knps_camps
    return render_template('campsites.html', campsites=all_camps, selected_region=region)

# -- status
@app.route('/status')
def show_status():
    zone_id  = request.args.get('zone_id', '')
    date     = request.args.get('date', '')
    campsite = request.args.get('campsite', '')
    available, full, error = [], [], None
    if zone_id and date:
        try:
            count = check_foresttrip_availability(zone_id, date, user_id=session.get('user_id'))
            if count > 0:
                available = [f'예약 가능 {count}건']
            elif count == 0:
                full = ['예약 불가']
            else:
                error = '숲나들e 서버 인증 오류 (로그인 필요 또는 URL 변경). 아래 링크에서 직접 확인하세요.'
        except Exception as e:
            error = str(e)
    foresttrip_url = (
        f'https://www.foresttrip.go.kr/rep/or/sssn/fcfsRsrvtPssblGoodsDetls.do'
        f'?srchInsttId={zone_id}&srchRsrvtBgDt={date.replace("-","")}'
        f'&menuId=001001&hmpgId=FRIP'
    ) if zone_id else 'https://www.foresttrip.go.kr/'
    return render_template('status.html', zone_id=zone_id, date=date,
                           campsite=campsite, available=available, full=full, error=error,
                           foresttrip_url=foresttrip_url)

# -- api_check
@app.route('/api/check/<int:cond_id>')
@login_required
def api_check(cond_id):
    from flask import jsonify
    db = get_db()
    cond = db.execute('SELECT * FROM watch_conditions WHERE id=? AND user_id=?',
                      (cond_id, session['user_id'])).fetchone()
    db.close()
    if not cond:
        return jsonify({'error': 'not found'}), 404
    if not cond['zone_id']:
        return jsonify({'error': 'no zone_id', 'count': -1})
    try:
        source = cond['source'] or 'foresttrip'
    except Exception:
        source = 'foresttrip'
    nights = cond['nights'] or 1
    site_name = cond['site_name'] or ''
    if source == 'knps':
        count = check_knps_availability(cond['zone_id'], cond['check_in'])
        return jsonify({'count': count, 'source': 'knps'})
    try:
        count = check_foresttrip_availability(cond['zone_id'], cond['check_in'], nights, user_id=session.get('user_id'))
        return jsonify({'count': count, 'source': 'foresttrip'})
    except Exception as e:
        return jsonify({'error': str(e), 'count': -1})

# -- favorites
@app.route("/api/favorite/<zone_id>", methods=["POST"])
@login_required
def toggle_favorite(zone_id):
    campsite = request.form.get("campsite", "")
    sido     = request.form.get("sido", "")
    db = get_db()
    existing = db.execute("SELECT id FROM favorites WHERE user_id=? AND zone_id=?",
                          (session["user_id"], zone_id)).fetchone()
    if existing:
        db.execute("DELETE FROM favorites WHERE user_id=? AND zone_id=?",
                   (session["user_id"], zone_id))
        result = "removed"
    else:
        db.execute("INSERT OR IGNORE INTO favorites (user_id,zone_id,campsite,sido) VALUES (?,?,?,?)",
                   (session["user_id"], zone_id, campsite, sido))
        result = "added"
    db.commit()
    db.close()
    return {"result": result}

@app.route("/api/favorites/list")
@login_required
def favorites_list_api():
    db = get_db()
    favs = db.execute("SELECT zone_id FROM favorites WHERE user_id=?", (session["user_id"],)).fetchall()
    db.close()
    return [f["zone_id"] for f in favs]

@app.route("/favorites")
@login_required
def favorites_page():
    db = get_db()
    favs = db.execute("SELECT * FROM favorites WHERE user_id=? ORDER BY created_at DESC",
                      (session["user_id"],)).fetchall()
    db.close()
    return render_template("favorites.html", favorites=favs)

@app.route("/api/check-date")
def api_check_date():
    zone_id = request.args.get("zone_id", "")
    date    = request.args.get("date", "")
    source  = request.args.get("source", "foresttrip")
    if not zone_id or not date:
        return {"count": -1}
    if source == "knps":
        count = check_knps_availability(zone_id, date)
    else:
        count = check_foresttrip_availability(zone_id, date, user_id=session.get('user_id'))
    return {"count": count}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
