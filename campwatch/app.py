from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import get_db, init_db
import functools
import bcrypt

app = Flask(__name__)
app.secret_key = 'campwatch-secret-change-me'

init_db()

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
    db.close()
    return render_template('dashboard.html', conditions=conditions, logs=logs)

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
    if not camp_name or not check_in or not check_out:
        flash('입력값을 확인해 주세요.')
        return redirect(url_for('campsites_page'))
    db = get_db()
    db.execute(
        'INSERT INTO watch_conditions (user_id, camp_name, site_name, check_in, check_out) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], camp_name, site_name, check_in, check_out)
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

@app.route('/restart', methods=['POST'])
@login_required
def restart_server():
    import subprocess, threading, os
    def do_restart():
        import time
        time.sleep(1)
        script = os.path.join(os.path.dirname(__file__), 'restart.sh')
        subprocess.Popen(['bash', script])
    threading.Thread(target=do_restart, daemon=True).start()
    flash('서버를 재시작합니다. 3~5초 후 새로고침해 주세요.')
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

def fetch_campsites():
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
            })
    except Exception as e:
        import logging; logging.warning(f'foresttrip fetch error: {e}')
    if campsites:
        CAMPSITE_CACHE["data"] = campsites
        CAMPSITE_CACHE["fetched_at"] = now
    return campsites

@app.route('/campsites')
@login_required
def campsites_page():
    region = request.args.get('region', '전체')
    sites  = fetch_campsites()
    return render_template('campsites.html', campsites=sites, selected_region=region)

# ── 예약 현황 ─────────────────────────────────────────────
@app.route('/status')
@login_required
def show_status():
    zone_id  = request.args.get('zone_id', '')
    date     = request.args.get('date', '')
    campsite = request.args.get('campsite', '')
    available, full, error = [], [], None
    if zone_id and date:
        import requests as _req
        from bs4 import BeautifulSoup as BS
        url = (f'https://www.foresttrip.go.kr/resv/selectFrpResveAbsmapView.do'
               f'?zoneId={zone_id}&arvDe={date}&stayCnt=1')
        try:
            resp = _req.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'ko-KR,ko;q=0.9',
                'Referer': 'https://www.foresttrip.go.kr/'
            }, timeout=15)
            soup = BS(resp.text, 'lxml')
            for cls in ['resve_able', 'possible', 'status_able']:
                for tag in soup.find_all(class_=cls):
                    name = tag.get('title') or tag.get('data-site-nm') or tag.get_text(strip=True)
                    if name and name not in available:
                        available.append(name)
            for tag in soup.find_all(attrs={'data-status': True}):
                name = tag.get('data-site-nm') or tag.get('title') or tag.get_text(strip=True)
                if tag['data-status'].lower() in ('available', 'y', 'able'):
                    if name and name not in available:
                        available.append(name)
                else:
                    if name and name not in full:
                        full.append(name)
        except Exception as e:
            error = str(e)
    return render_template('status.html', zone_id=zone_id, date=date,
                           campsite=campsite, available=available, full=full, error=error)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
