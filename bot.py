# ============================================================
# 🚀 HOST BOT v10.0 — نسخة كاملة محسّنة
# ✅ حل مشكلة تعليق التثبيت
# ✅ Reverse Proxy للمشاريع
# ✅ Heartbeat ضد Restart Loop
# ✅ أزرار ملونة + تخصيص
# ============================================================

import os, sys, json, time, shutil, signal, sqlite3, subprocess
import threading, socket, re, random, zipfile, platform, urllib.request
from datetime import datetime

import telebot
from telebot import types
from flask import Flask, render_template_string, request, Response

# ============================================================
# 🛠️ ضمان المكتبات
# ============================================================
def ensure_packages():
    pkgs = {"telebot": "pyTelegramBotAPI", "flask": "flask", "requests": "requests"}
    missing = []
    for imp, pip in pkgs.items():
        try:
            __import__(imp)
        except ImportError:
            missing.append(pip)

    if missing:
        print(f"[Setup] مكتبات ناقصة: {missing}")
        for pip_name in missing:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--no-cache-dir", pip_name],
                    timeout=180, check=False
                )
            except Exception as e:
                print(f"[Setup] فشل {pip_name}: {e}")
        print("[Setup] ✅ خلص")

ensure_packages()

# ============================================================
# ⚙️ الإعدادات
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8247238031:AAFPByiRwTLnN-qh559yP7JalKdirk-9tnE")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "7325566792").split(",")]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "hosted_projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "host_v10.db")

RUNNING = {}
user_states = {}
START_TIME = datetime.now()
PORT_COUNTER = 7000
TUNNEL_URL = None  # الرابط العام

# ============================================================
# 🛠️ Utilities عامة
# ============================================================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_public_url():
    """يرجع الرابط العام — يدعم Render / Koyeb / Railway / Fly / Tunnel"""
    global TUNNEL_URL
    if TUNNEL_URL:
        return TUNNEL_URL

    # ✅ Render
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        TUNNEL_URL = render_url.rstrip("/")
        return TUNNEL_URL

    # ✅ Koyeb
    koyeb = os.environ.get("KOYEB_PUBLIC_DOMAIN")
    if koyeb:
        TUNNEL_URL = f"https://{koyeb}"
        return TUNNEL_URL

    # ✅ Railway
    railway = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway:
        TUNNEL_URL = f"https://{railway}"
        return TUNNEL_URL

    # ✅ Fly.io
    fly = os.environ.get("FLY_APP_NAME")
    if fly:
        TUNNEL_URL = f"https://{fly}.fly.dev"
        return TUNNEL_URL

    # من DB (Tunnel سابق)
    try:
        conn = _conn(); c = conn.cursor()
        c.execute("SELECT value FROM ui_settings WHERE key='public_url'")
        r = c.fetchone(); conn.close()
        if r and r[0]:
            TUNNEL_URL = r[0]
            return r[0]
    except: pass

    # من env عام
    env_url = os.environ.get("PUBLIC_URL")
    if env_url:
        return env_url.rstrip("/")

    # fallback محلي
    port = int(os.environ.get("PORT", 8080))
    return f"http://{get_local_ip()}:{port}"

def calc_uptime(start_str):
    if not start_str:
        return "—"
    try:
        s = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        t = int((datetime.now() - s).total_seconds())
        if t < 0: t = 0
        h, m, sec = t // 3600, (t % 3600) // 60, t % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"
    except:
        return "—"

def get_free_port():
    global PORT_COUNTER
    while PORT_COUNTER < 65000:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", PORT_COUNTER))
            s.close()
            p = PORT_COUNTER
            PORT_COUNTER += 1
            return p
        except:
            PORT_COUNTER += 1
        finally:
            try: s.close()
            except: pass
    return 7500

def get_file_size_str(fp):
    try:
        size = os.path.getsize(fp)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except:
        return "?"

def list_dir_files(dirpath):
    result = []
    for root, dirs, files in os.walk(dirpath):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, dirpath)
            result.append(rel)
    return result

# ============================================================
# 🗄️ قاعدة البيانات
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        created_at TEXT, is_banned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, name TEXT,
        ptype TEXT DEFAULT 'bot', path TEXT, entry TEXT, files TEXT DEFAULT '[]',
        requirements TEXT DEFAULT '', bot_token TEXT DEFAULT '',
        bot_username TEXT DEFAULT '', bot_name TEXT DEFAULT '',
        port INTEGER DEFAULT 0, public_url TEXT DEFAULT '',
        installed INTEGER DEFAULT 0, pid INTEGER DEFAULT 0,
        status TEXT DEFAULT 'stopped', created_at TEXT,
        last_start TEXT DEFAULT '', last_stop TEXT DEFAULT '')''')
    c.execute('''CREATE TABLE IF NOT EXISTS ui_settings (
        key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit(); conn.close()

init_db()

def _conn():
    return sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)

# ============================================================
# 👥 Users
# ============================================================
def get_user(uid):
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = c.fetchone(); conn.close(); return r

def add_user(uid, username="", first_name=""):
    conn = _conn(); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
                  (uid, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def get_all_users():
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    r = [x[0] for x in c.fetchall()]; conn.close(); return r

def get_user_count():
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    r = c.fetchone()[0]; conn.close(); return r

def get_all_users_full():
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    r = c.fetchall(); conn.close(); return r

# ============================================================
# 📦 Projects
# ============================================================
def add_project(owner_id, name, ptype, path, entry):
    conn = _conn(); c = conn.cursor()
    c.execute("""INSERT INTO projects (owner_id, name, ptype, path, entry, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (owner_id, name, ptype, path, entry,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    pid = c.lastrowid; conn.commit(); conn.close(); return pid

def get_projects_by_owner(owner_id):
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE owner_id=? ORDER BY id DESC", (owner_id,))
    r = c.fetchall(); conn.close(); return r

def get_project(pid):
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id=?", (pid,))
    r = c.fetchone(); conn.close(); return r

def get_all_projects():
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT * FROM projects ORDER BY id DESC")
    r = c.fetchall(); conn.close(); return r

def update_project(project_id, **kw):
    if not kw: return
    conn = _conn(); c = conn.cursor()
    for k, v in kw.items():
        c.execute(f"UPDATE projects SET {k}=? WHERE id=?", (v, project_id))
    conn.commit(); conn.close()

def delete_project(pid):
    conn = _conn(); c = conn.cursor()
    c.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit(); conn.close()

# ============================================================
# 🎨 UI Settings
# ============================================================
DEFAULT_UI = {
    "btn_my_projects": "📦 مشاريعي",
    "btn_new_project": "➕ مشروع جديد",
    "btn_account": "👤 حسابي",
    "btn_help": "❓ مساعدة",
    "btn_admin": "👑 لوحة المطور",
    "welcome_text": "👋 أهلاً بك في Host Bot v10!",
    "dashboard_title": "🚀 HOST BOT v10",
}

def get_ui(key):
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT value FROM ui_settings WHERE key=?", (key,))
    r = c.fetchone(); conn.close()
    return r[0] if r else DEFAULT_UI.get(key, "")

def set_ui(key, value):
    conn = _conn(); c = conn.cursor()
    c.execute("REPLACE INTO ui_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit(); conn.close()

def get_all_ui():
    result = dict(DEFAULT_UI)
    conn = _conn(); c = conn.cursor()
    c.execute("SELECT key, value FROM ui_settings")
    for k, v in c.fetchall():
        result[k] = v
    conn.close()
    return result

# ============================================================
# 🎨 أزرار ملونة (style)
# ============================================================
def btn(text, cb=None, url=None, style=None):
    b = types.InlineKeyboardButton(text=text, callback_data=cb, url=url)
    if style:
        try:
            b.style = style  # success / danger / primary
        except:
            pass
    return b

def btn_green(t, cb=None, url=None):  return btn(t, cb=cb, url=url, style="success")
def btn_red(t, cb=None, url=None):    return btn(t, cb=cb, url=url, style="danger")
def btn_blue(t, cb=None, url=None):   return btn(t, cb=cb, url=url, style="primary")
def btn_gray(t, cb=None, url=None):   return btn(t, cb=cb, url=url)

# ============================================================
# 🔍 فحص الملفات
# ============================================================
def check_python_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
        try:
            compile(src, fp, "exec")
            return True, "✅ Python: سليم"
        except SyntaxError as e:
            return False, (f"❌ <b>خطأ Python</b>\n\n"
                          f"📄 <code>{os.path.basename(fp)}</code>\n"
                          f"📍 السطر: <b>{e.lineno}</b> | العمود: <b>{e.offset}</b>\n"
                          f"🔤 <code>{e.msg}</code>\n\n"
                          f"<b>السطر:</b>\n<code>{(e.text or '').strip()}</code>")
    except Exception as e:
        return False, f"❌ خطأ: {e}"

def check_json_file(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            json.load(f)
        return True, "✅ JSON: سليم"
    except json.JSONDecodeError as e:
        return False, f"❌ <b>خطأ JSON</b>\n📍 السطر: <b>{e.lineno}</b>\n🔤 <code>{e.msg}</code>"
    except Exception as e:
        return False, f"❌ خطأ: {e}"

def check_shell_file(fp):
    try:
        r = subprocess.run(["bash", "-n", fp], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, "✅ Shell: سليم"
        return False, f"❌ <b>خطأ Shell</b>\n<pre>{r.stderr[-400:]}</pre>"
    except FileNotFoundError:
        return True, "ℹ️ Shell: تم التخطي"
    except Exception as e:
        return False, f"❌ خطأ: {e}"

def check_yaml_file(fp):
    try:
        import yaml
        with open(fp, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
        return True, "✅ YAML: سليم"
    except ImportError:
        return True, "ℹ️ YAML: تم التخطي"
    except Exception as e:
        return False, f"❌ خطأ YAML: {str(e)[:200]}"

def check_any_file(fp):
    if not os.path.exists(fp):
        return False, "❌ الملف غير موجود"
    name = os.path.basename(fp).lower()
    if name.endswith(".py"):
        return check_python_file(fp)
    elif name.endswith(".json"):
        return check_json_file(fp)
    elif name.endswith(".sh"):
        return check_shell_file(fp)
    elif name.endswith((".yml", ".yaml")):
        return check_yaml_file(fp)
    return True, f"✅ {name}: مدعوم"

# ============================================================
# 📦 إدارة ملفات المشروع
# ============================================================
def get_project_files(pid):
    p = get_project(pid)
    if not p: return []
    try:
        return json.loads(p[7] or "[]")
    except:
        return []

def add_project_file(pid, filename):
    files = get_project_files(pid)
    if filename not in files:
        files.append(filename)
    update_project(pid, files=json.dumps(files))

# ✅ استخراج توكن البوت (يتجاهل API_ID / API_HASH)
def extract_bot_info(fp):
    info = {"token": None, "username": None, "name": None}
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        patterns = [
            r'BOT_TOKEN\s*=\s*["\']([0-9]{8,12}:[A-Za-z0-9_-]{30,50})["\']',
            r'BOT_TOKEN\s*:\s*["\']([0-9]{8,12}:[A-Za-z0-9_-]{30,50})["\']',
            r'["\']BOT_TOKEN["\']\s*:\s*["\']([0-9]{8,12}:[A-Za-z0-9_-]{30,50})["\']',
            r'bot_token\s*=\s*["\']([0-9]{8,12}:[A-Za-z0-9_-]{30,50})["\']',
        ]
        for p in patterns:
            m = re.search(p, content)
            if m:
                info["token"] = m.group(1)
                break

        if info["token"]:
            try:
                import requests
                r = requests.get(f"https://api.telegram.org/bot{info['token']}/getMe", timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("ok"):
                        info["username"] = d["result"].get("username")
                        info["name"] = d["result"].get("first_name")
                    else:
                        info["token"] = None
                else:
                    info["token"] = None
            except:
                info["token"] = None
    except:
        pass
    return info

# ============================================================
# ⚙️ تثبيت مكتبة — ✅ النسخة الجديدة (بدون تعليق)
# ============================================================
def install_single_pkg(pid, pkg):
    """يثبت مكتبة بدون تعليق العملية الرئيسية"""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check", pkg],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            preexec_fn=os.setsid if os.name != "nt" else None
        )
        try:
            out, _ = proc.communicate(timeout=300)
            if proc.returncode == 0:
                return True, f"✅ {pkg}"
            return False, f"❌ {pkg}: {out[-200:] if out else 'فشل'}"
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except: pass
            return False, f"⏱️ {pkg}: انتهت المهلة (5 دقائق)"
    except Exception as e:
        return False, f"❌ {pkg}: {str(e)[:80]}"

# ============================================================
# 🚀 تشغيل / إيقاف المشاريع
# ============================================================
def start_project(pid):
    p = get_project(pid)
    if not p: return False, "❌ غير موجود"
    key = f"p{pid}"
    if key in RUNNING and RUNNING[key].poll() is None:
        return False, "⚠️ شغال بالفعل"

    entry_path = os.path.join(p[4], p[5])
    if not os.path.exists(entry_path):
        return False, f"❌ {p[5]} غير موجود"

    if p[5].endswith(".py"):
        ok, msg = check_python_file(entry_path)
        if not ok:
            return False, f"❌ فحص:\n{msg[:400]}"

    try:
        env = os.environ.copy()
        port = 0
        public_url = ""

        if p[3] == "web":
            port = get_free_port()
            env["PORT"] = str(port)
            env["FLASK_RUN_PORT"] = str(port)
            env["HOST"] = "0.0.0.0"
            env["FLASK_APP"] = p[5]
            # ✅ الرابط العام عبر البروكسي
            base = get_public_url()
            public_url = f"{base}/proxy/{pid}"

        log_path = os.path.join(p[4], "output.log")
        lf = open(log_path, "a", encoding="utf-8")
        lf.write(f"\n\n===== START {datetime.now()} =====\n")
        lf.flush()

        cmd = [sys.executable, "-u", p[5]] if p[5].endswith(".py") else ["bash", p[5]]
        kw = {"preexec_fn": os.setsid} if os.name != "nt" else {}

        proc = subprocess.Popen(
            cmd, cwd=p[4], stdout=lf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=env, **kw
        )
        RUNNING[key] = proc

        update_project(
            pid, pid=proc.pid, status="running", port=port,
            public_url=public_url,
            last_start=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        # ✅ نستنى ونتأكد إنه لسه شغال
        time.sleep(5)
        if proc.poll() is not None:
            error_msg = "(لا توجد تفاصيل)"
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    error_msg = "".join(f.readlines()[-15:])
            except: pass
            update_project(pid, status="stopped", pid=0)
            return False, f"❌ المشروع مات فوراً!\n\n<pre>{error_msg[-800:]}</pre>"

        return True, "✅ شغال"
    except Exception as e:
        return False, f"❌ {e}"

def stop_project(pid):
    p = get_project(pid)
    if not p: return False, "غير موجود"
    key = f"p{pid}"
    stopped = False

    if key in RUNNING:
        proc = RUNNING[key]
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            proc.wait(timeout=5); stopped = True
        except:
            try: proc.kill(); stopped = True
            except: pass
        RUNNING.pop(key, None)

    if p[14]:
        try:
            os.kill(p[14], signal.SIGTERM)
            stopped = True
        except: pass

    update_project(
        pid, pid=0, status="stopped",
        last_stop=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    return True, "🛑 تم الإيقاف" if stopped else "ℹ️ كان متوقف"

def is_running(pid):
    key = f"p{pid}"
    if key in RUNNING:
        p = RUNNING[key]
        if p.poll() is None:
            return True
        RUNNING.pop(key, None)
        update_project(pid, pid=0, status="stopped")
    return False

def get_logs(pid, n=60):
    p = get_project(pid)
    if not p: return "غير موجود"
    lp = os.path.join(p[4], "output.log")
    if not os.path.exists(lp): return "(لا توجد Logs)"
    try:
        with open(lp, "r", encoding="utf-8", errors="ignore") as f:
            return "".join(f.readlines()[-n:])
    except Exception as e:
        return f"خطأ: {e}"

# ============================================================
# 💓 Heartbeat — يحل مشكلة Restart Loop
# ============================================================
def keep_alive():
    while True:
        time.sleep(30)
        running_count = sum(1 for p in get_all_projects() if is_running(p[0]))
        print(f"[Heartbeat] {datetime.now().strftime('%H:%M:%S')} | "
              f"projects_running={running_count} | tunnel={TUNNEL_URL or 'none'}")
              
# ============================================================
# 🤖 بوت تلجرام
# ============================================================
bot = telebot.TeleBot(BOT_TOKEN)

def is_admin(uid):
    return uid in ADMIN_IDS

def main_menu(uid):
    ui = get_all_ui()
    m = types.InlineKeyboardMarkup(row_width=2)

    # 🌐 زر التحكم في الاستضافة (WebApp لو HTTPS)
    dashboard_url = get_public_url()
    if dashboard_url.startswith("https://"):
        try:
            m.add(types.InlineKeyboardButton(
                "↗️ تحكم في استضافتك",
                web_app=types.WebAppInfo(url=dashboard_url)
            ))
        except:
            m.add(btn_blue("↗️ تحكم في استضافتك", "open_dashboard"))
    else:
        m.add(btn_blue("↗️ تحكم في استضافتك", "open_dashboard"))

    m.row(
        btn_blue(ui["btn_my_projects"], "my_projs"),
        btn_green(ui["btn_new_project"], "new_proj")
    )
    m.row(
        btn_blue(ui["btn_account"], "my_account"),
        btn_gray(ui["btn_help"], "help")
    )

    if is_admin(uid):
        m.add(btn_red(ui["btn_admin"], "admin_panel"))
    return m

@bot.message_handler(commands=['start'])
def cmd_start(msg):
    uid = msg.from_user.id
    if not get_user(uid):
        add_user(uid, msg.from_user.username or "", msg.from_user.first_name or "")
    name = msg.from_user.first_name or "صديقي"
    ui = get_all_ui()
    txt = (
        "╔══════════════════════════════╗\n"
        "║   🚀 <b>HOST BOT v10</b>       ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👋 أهلاً <b>{name}</b>!\n\n"
        f"{ui['welcome_text']}\n\n"
        "📌 <b>البوت يخليك:</b>\n"
        "  • 📤 ترفع أي نوع ملف\n"
        "  • 🔍 فحص تلقائي\n"
        "  • ⚙️ تثبيت مكتبات (بدون تعليق)\n"
        "  • 🌐 رابط شغال لكل مشروع ويب\n"
        "  • 📊 لوحة تحكم Web\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>اختر من القائمة:</b>"
    )
    bot.send_message(msg.chat.id, txt, parse_mode="HTML", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def cb_main(call):
    try:
        bot.edit_message_text(
            "🏠 <b>القائمة الرئيسية</b>",
            call.message.chat.id, call.message.message_id,
            reply_markup=main_menu(call.from_user.id),
            parse_mode="HTML"
        )
    except:
        bot.send_message(call.message.chat.id, "🏠 القائمة الرئيسية",
                        reply_markup=main_menu(call.from_user.id))

# ============================================================
# 🌐 زر لوحة التحكم
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "open_dashboard")
def cb_open_dashboard(call):
    url = get_public_url()
    is_https = url.startswith("https://")

    txt = (
        "🌐 <b>لوحة التحكم Web</b>\n\n"
        "📊 <b>تشوف فيها:</b>\n"
        "  • 📦 كل المشاريع\n"
        "  • ▶️ تشغيل/إيقاف\n"
        "  • 📄 Logs\n"
        "  • 📈 إحصائيات\n\n"
        f"🔗 <b>الرابط:</b>\n<code>{url}</code>\n\n"
    )
    if not is_https:
        txt += "⚠️ <b>ملاحظة:</b> الرابط ده داخلي حاليًا.\n"
        txt += "لو عايزه يشتغل من أي مكان → انتظر Tunnel.\n\n"
    txt += "👇 اضغط الزر لفتحه:"

    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(btn_blue("↗️ افتح لوحة التحكم", url=url))
    m.add(btn_gray("🔙 رجوع", "main_menu"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except:
        bot.send_message(call.message.chat.id, txt, reply_markup=m, parse_mode="HTML")
    bot.answer_callback_query(call.id, "🌐 جاري الفتح")

# ============================================================
# 📦 مشاريعي
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "my_projs")
def cb_my_projs(call):
    uid = call.from_user.id
    projs = get_projects_by_owner(uid)
    if not projs:
        m = types.InlineKeyboardMarkup()
        m.add(btn_green("➕ مشروع جديد", "new_proj"))
        m.add(btn_gray("رجوع", "main_menu"))
        bot.edit_message_text("📭 <b>لا توجد مشاريع</b>",
                             call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
        return
    txt = f"📦 <b>مشاريعك ({len(projs)}):</b>\n\n"
    m = types.InlineKeyboardMarkup(row_width=1)
    for p in projs:
        pid = p[0]
        running = is_running(pid)
        up = calc_uptime(p[18]) if running else "—"
        icon = "🐍" if p[3] == "bot" else "🌐"
        if running:
            m.add(btn_green(f"{icon} {p[2]} | ⏱️ {up}", f"proj_{pid}"))
        else:
            m.add(btn_red(f"{icon} {p[2]} | 🔴 متوقف", f"proj_{pid}"))
    m.add(btn_gray("رجوع", "main_menu"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except: pass

# ============================================================
# 📦 تفاصيل مشروع
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("proj_"))
def cb_proj(call):
    pid = int(call.data[5:])
    uid = call.from_user.id
    p = get_project(pid)
    if not p: return
    if p[1] != uid and not is_admin(uid):
        bot.answer_callback_query(call.id, "غير مصرح"); return

    running = is_running(pid)
    up = calc_uptime(p[18]) if running else "—"
    icon = "🐍" if p[3] == "bot" else "🌐"
    bot_user = f"@{p[10]}" if p[10] else "غير معروف"
    files = get_project_files(pid)

    txt = (
        f"╔══════════════════════════════╗\n"
        f"║   {icon} <b>{p[2]}</b>\n"
        f"╚══════════════════════════════╝\n\n"
        f"📄 <b>الملف:</b> <code>{p[5]}</code>\n"
        f"📁 <b>الملفات:</b> {len(files)}\n"
        f"🤖 <b>البوت:</b> {bot_user}\n"
        f"📊 <b>الحالة:</b> {'🟢 شغال' if running else '🔴 متوقف'}\n"
        f"⏱️ <b>المدة:</b> {up}\n"
        f"🆔 PID: {p[14] or '—'}"
    )
    if p[3] == "web" and p[12]:
        txt += f"\n🔗 <b>الرابط:</b>\n<code>{p[12]}</code>"

    m = types.InlineKeyboardMarkup(row_width=2)
    if running:
        m.row(btn_red("⏹️ إيقاف", f"stop_{pid}"), btn_blue("📄 Logs", f"logs_{pid}"))
    else:
        m.row(btn_green("▶️ تشغيل", f"start_{pid}"), btn_blue("📄 Logs", f"logs_{pid}"))

    if p[3] == "web":
        m.row(btn_blue("🌐 فتح الموقع", f"openweb_{pid}"))

    m.row(btn_blue("📁 الملفات", f"files_{pid}"), btn_blue("➕ ملف جديد", f"addfile_{pid}"))
    m.row(btn_blue("🔍 فحص", f"check_{pid}"), btn_blue("⚙️ مكتبة", f"addpkg_{pid}"))
    m.add(btn_red("🗑️ حذف", f"del_{pid}"))
    m.add(btn_gray("رجوع", "my_projs"))

    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except: pass

# ============================================================
# ▶️ تشغيل
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("start_"))
def cb_start(call):
    pid = int(call.data[6:])
    uid = call.from_user.id
    p = get_project(pid)
    if not p or (p[1] != uid and not is_admin(uid)): return

    msg = bot.send_message(call.message.chat.id, "⏳ <b>جاري التجهيز...</b>", parse_mode="HTML")

    def do_start():
        for i in range(5, 0, -1):
            try:
                bot.edit_message_text(
                    f"⏳ <b>جاري التجهيز...</b>\n\n"
                    f"⏱️ <b>يبدأ خلال:</b> {i} ثانية\n\n"
                    f"{'█' * (5-i)}{'░' * i}",
                    msg.chat.id, msg.message_id, parse_mode="HTML")
            except: pass
            time.sleep(1)

        ok, m = start_project(pid)
        if ok:
            pp = get_project(pid)
            bot_user = f"@{pp[10]}" if pp[10] else "غير معروف"
            text = (
                "🎉 <b>تم التشغيل!</b>\n\n"
                f"📦 <b>المشروع:</b> {pp[2]}\n"
                f"🤖 <b>يوزر البوت:</b> {bot_user}\n"
                f"⏱️ <b>العدّاد بدأ:</b> الآن"
            )
            if pp[3] == "web" and pp[12]:
                text += f"\n🔗 <b>الرابط:</b>\n<code>{pp[12]}</code>"

            markup = types.InlineKeyboardMarkup(row_width=2)
            if pp[3] == "web" and pp[12]:
                markup.add(btn_blue("🌐 فتح الموقع", url=pp[12]))
            if bot_user != "غير معروف":
                markup.add(btn_blue("🤖 افتح البوت", url=f"https://t.me/{pp[10]}"))
            markup.row(btn_blue("📄 Logs", f"logs_{pid}"), btn_gray("🔙 رجوع", f"proj_{pid}"))

            bot.edit_message_text(text, msg.chat.id, msg.message_id,
                                 reply_markup=markup, parse_mode="HTML")
        else:
            bot.edit_message_text(
                f"❌ <b>فشل التشغيل</b>\n\n{m}",
                msg.chat.id, msg.message_id, parse_mode="HTML")

    threading.Thread(target=do_start, daemon=True).start()

# ============================================================
# ⏹️ إيقاف
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("stop_"))
def cb_stop(call):
    pid = int(call.data[5:])
    uid = call.from_user.id
    p = get_project(pid)
    if not p or (p[1] != uid and not is_admin(uid)): return
    ok, msg = stop_project(pid)
    bot.answer_callback_query(call.id, msg, show_alert=True)
    call.data = f"proj_{pid}"
    cb_proj(call)

# ============================================================
# 📄 Logs
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("logs_"))
def cb_logs(call):
    pid = int(call.data[5:])
    logs = get_logs(pid, 60)
    if len(logs) > 3000:
        logs = logs[-3000:]
    p = get_project(pid)
    txt = f"📄 <b>Logs: {p[2]}</b>\n\n<pre>{logs}</pre>"
    m = types.InlineKeyboardMarkup()
    m.row(btn_blue("🔄 تحديث", f"logs_{pid}"), btn_gray("رجوع", f"proj_{pid}"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except:
        bot.send_message(call.message.chat.id, txt, reply_markup=m, parse_mode="HTML")

# ============================================================
# 🌐 فتح الموقع (يستخدم الرابط العام)
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("openweb_"))
def cb_openweb(call):
    pid = int(call.data[8:])
    p = get_project(pid)
    if not p or not p[12]:
        bot.answer_callback_query(call.id, "❌ لا يوجد رابط"); return
    bot.answer_callback_query(call.id, "🌐 جاري الفتح", show_alert=False)
    m = types.InlineKeyboardMarkup()
    m.add(btn_blue("🌐 فتح الموقع", url=p[12]))
    m.add(btn_gray("رجوع", f"proj_{pid}"))
    bot.send_message(
        call.message.chat.id,
        f"🔗 <b>رابط موقعك:</b>\n\n<code>{p[12]}</code>\n\n👇 اضغط لفتحه:",
        reply_markup=m, parse_mode="HTML"
    )

# ============================================================
# 🔍 فحص
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def cb_check(call):
    pid = int(call.data[6:])
    p = get_project(pid)
    if not p: return
    fp = os.path.join(p[4], p[5])
    ok, msg = check_any_file(fp)
    if ok:
        bot.answer_callback_query(call.id, "✅ سليم", show_alert=True)
    else:
        bot.send_message(call.message.chat.id, msg, parse_mode="HTML")

# ============================================================
# 📁 الملفات
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("files_"))
def cb_files(call):
    pid = int(call.data[6:])
    p = get_project(pid)
    if not p: return
    files = list_dir_files(p[4])
    if not files:
        txt = "📭 <b>لا توجد ملفات</b>"
    else:
        txt = f"📁 <b>ملفات {p[2]} ({len(files)}):</b>\n\n"
        for f in files[:30]:
            fp = os.path.join(p[4], f)
            size = get_file_size_str(fp)
            txt += f"📄 <code>{f}</code> ({size})\n"
        if len(files) > 30:
            txt += f"\n... +{len(files)-30} ملف تاني"
    m = types.InlineKeyboardMarkup()
    m.add(btn_blue("➕ إضافة ملف", f"addfile_{pid}"))
    m.add(btn_gray("🔙 رجوع", f"proj_{pid}"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except:
        bot.send_message(call.message.chat.id, txt, reply_markup=m, parse_mode="HTML")

# ============================================================
# ➕ إضافة ملف
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("addfile_"))
def cb_addfile(call):
    pid = int(call.data[8:])
    user_states[call.from_user.id] = f"waiting_addfile_{pid}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("❌ إلغاء", f"proj_{pid}"))
    bot.edit_message_text(
        "📤 <b>أرسل الملف</b>\n\n"
        "الأنواع المدعومة:\n"
        "<code>.py .txt .json .env .sh .html .css .js .yml .yaml .zip .xml .md</code>",
        call.message.chat.id, call.message.message_id,
        reply_markup=m, parse_mode="HTML"
    )

# ============================================================
# ⚙️ إضافة مكتبة (يدوي)
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("addpkg_"))
def cb_addpkg(call):
    pid = int(call.data[7:])
    user_states[call.from_user.id] = f"waiting_pkg_{pid}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", f"proj_{pid}"))
    bot.edit_message_text(
        "📝 <b>أرسل اسم المكتبة</b>\n\nمثال: <code>requests</code>",
        call.message.chat.id, call.message.message_id,
        reply_markup=m, parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, "").startswith("waiting_pkg_"))
def do_addpkg(msg):
    pid = int(user_states[msg.from_user.id].replace("waiting_pkg_", ""))
    pkg = msg.text.strip()
    del user_states[msg.from_user.id]
    bot.reply_to(msg, f"⏳ جاري تثبيت <code>{pkg}</code>...", parse_mode="HTML")

    def do():
        ok, m = install_single_pkg(pid, pkg)
        emoji = "✅" if ok else "❌"
        bot.send_message(msg.chat.id, f"{emoji} {m}", parse_mode="HTML")

    threading.Thread(target=do, daemon=True).start()

# ============================================================
# 👤 حسابي
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "my_account")
def cb_account(call):
    uid = call.from_user.id
    projs = get_projects_by_owner(uid)
    running = sum(1 for p in projs if is_running(p[0]))
    txt = (
        "╔══════════════════════════════╗\n"
        "║   👤 <b>حسابك</b>\n"
        "╚══════════════════════════════╝\n\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"👤 <b>الاسم:</b> {call.from_user.first_name or '—'}\n"
        f"📦 <b>المشاريع:</b> {len(projs)}\n"
        f"🟢 <b>شغّالة:</b> {running}"
    )
    m = types.InlineKeyboardMarkup()
    m.add(btn_gray("رجوع", "main_menu"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

# ============================================================
# ❓ مساعدة
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "help")
def cb_help(call):
    txt = (
        "📚 <b>المساعدة</b>\n\n"
        "<b>خطوات إنشاء مشروع:</b>\n"
        "1️⃣ ➕ مشروع جديد\n"
        "2️⃣ اختر النوع (بوت / ويب)\n"
        "3️⃣ أرسل اسم المشروع\n"
        "4️⃣ أرسل ملف .py الرئيسي\n"
        "5️⃣ أرسل requirements.txt (اختياري)\n"
        "6️⃣ ابدأ التثبيت\n"
        "7️⃣ اضغط ▶️ تشغيل\n\n"
        "🌐 <b>للمشاريع الويب:</b>\n"
        "البوت هيديك رابط شغال تلقائي."
    )
    m = types.InlineKeyboardMarkup()
    m.add(btn_gray("رجوع", "main_menu"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

# ============================================================
# ➕ مشروع جديد
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "new_proj")
def cb_new(call):
    txt = (
        "╔══════════════════════════════╗\n"
        "║   ➕ <b>مشروع جديد</b>\n"
        "╚══════════════════════════════╝\n\n"
        "🎯 <b>اختر نوع الخدمة:</b>"
    )
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(
        btn_green("🐍 بوت Python", "type_bot"),
        btn_blue("🌐 موقع Web", "type_web")
    )
    m.add(btn_gray("❌ إلغاء", "main_menu"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("type_"))
def cb_type(call):
    ptype = call.data[5:]
    uid = call.from_user.id
    user_states[uid] = f"waiting_name_{ptype}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", "main_menu"))
    type_name = "بوت Python" if ptype == "bot" else "موقع Web"
    bot.edit_message_text(
        f"✅ النوع: <b>{type_name}</b>\n\n"
        f"📝 <b>الخطوة 1/3</b>\n\n"
        f"أرسل اسم المشروع (بدون مسافات):",
        call.message.chat.id, call.message.message_id,
        reply_markup=m, parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, "").startswith("waiting_name_"))
def msg_name(msg):
    uid = msg.from_user.id
    ptype = user_states[uid].replace("waiting_name_", "")
    name = msg.text.strip().replace(" ", "_")[:30]
    if not name:
        bot.reply_to(msg, "اسم غير صالح"); return
    projs = get_projects_by_owner(uid)
    if any(p[2] == name for p in projs):
        bot.reply_to(msg, "الاسم موجود"); return
    user_states[uid] = f"waiting_file_{ptype}_{name}"
    bot.reply_to(
        msg,
        f"✅ <b>{name}</b>\n\n"
        f"📝 <b>الخطوة 2/3</b>\n\n"
        f"📤 أرسل ملف <code>.py</code> الرئيسي",
        parse_mode="HTML"
    )

# ============================================================
# 📤 استقبال الملفات
# ============================================================
ALLOWED_EXTS = [
    ".py", ".txt", ".json", ".env", ".sh", ".html", ".css",
    ".js", ".yml", ".yaml", ".zip", ".xml", ".md", ".toml",
    ".ini", ".cfg"
]
ALLOWED_FILENAMES = [
    "Procfile", "Makefile", "Dockerfile", "LICENSE", "README", ".gitignore"
]

@bot.message_handler(content_types=['document'])
def handle_doc(msg):
    uid = msg.from_user.id
    state = user_states.get(uid, "")

    # 1) الملف الرئيسي
    if state.startswith("waiting_file_"):
        parts = state.replace("waiting_file_", "").split("_", 1)
        ptype = parts[0]
        name = parts[1] if len(parts) > 1 else "proj"
        filename = msg.document.file_name
        ext = os.path.splitext(filename)[1].lower()
        basename = os.path.basename(filename)

        if ext not in ALLOWED_EXTS and basename not in ALLOWED_FILENAMES:
            bot.send_message(msg.chat.id,
                f"❌ <b>نوع غير مدعوم:</b> <code>{ext}</code>",
                parse_mode="HTML")
            return

        try:
            fi = bot.get_file(msg.document.file_id)
            data = bot.download_file(fi.file_path)
            pdir = os.path.join(PROJECTS_DIR, f"{uid}_{name}")
            os.makedirs(pdir, exist_ok=True)

            if ext == ".zip":
                zip_path = os.path.join(pdir, filename)
                with open(zip_path, "wb") as f:
                    f.write(data)
                try:
                    with zipfile.ZipFile(zip_path, "r") as z:
                        z.extractall(pdir)
                    os.remove(zip_path)
                    all_files = list_dir_files(pdir)
                    py_files = [f for f in all_files if f.endswith(".py")]
                    if not py_files:
                        bot.send_message(msg.chat.id, "❌ لا يوجد ملف .py في الـ zip")
                        return
                    entry = py_files[0]
                    if "main.py" in py_files: entry = "main.py"
                    elif "app.py" in py_files: entry = "app.py"
                    elif "bot.py" in py_files: entry = "bot.py"
                    bot.send_message(msg.chat.id, f"📦 تم فك ZIP ({len(all_files)} ملف)")
                except Exception as e:
                    bot.send_message(msg.chat.id, f"❌ خطأ ZIP: {e}")
                    return
            else:
                entry = filename
                fp = os.path.join(pdir, entry)
                with open(fp, "wb") as f:
                    f.write(data)

            entry_path = os.path.join(pdir, entry)
            ok, chk = check_any_file(entry_path)
            if not ok:
                bot.send_message(msg.chat.id,
                    f"⚠️ <b>خطأ:</b>\n\n{chk}\n\n📤 أرسل ملف معدل",
                    parse_mode="HTML")
                return

            info = extract_bot_info(entry_path) if ptype == "bot" else {"token": None, "username": None, "name": None}
            pid = add_project(uid, name, ptype, pdir, entry)
            add_project_file(pid, entry)

            if info.get("token"):
                update_project(
                    pid,
                    bot_token=info["token"],
                    bot_username=info["username"] or "",
                    bot_name=info["name"] or ""
                )

            txt = (
                f"✅ <b>تم رفع الملف!</b>\n\n"
                f"📦 {name}\n📄 {entry}\n"
                f"📊 الحجم: {get_file_size_str(entry_path)}\n"
                f"🔍 الفحص: ✅ سليم\n\n"
            )
            if info.get("username"):
                txt += (
                    f"🤖 <b>تم استخراج التوكن!</b>\n"
                    f"👤 اليوزر: @{info['username']}\n"
                    f"🔗 https://t.me/{info['username']}\n\n"
                )
            txt += "📝 <b>الخطوة 3/3</b>\n\nهل عندك requirements.txt؟"

            user_states[uid] = f"waiting_req_{pid}"
            m = types.InlineKeyboardMarkup()
            m.row(
                btn_green("✅ نعم، سأرفعه", f"upload_req_{pid}"),
                btn_blue("⏭️ تخطي", f"proj_{pid}")
            )
            bot.send_message(msg.chat.id, txt, parse_mode="HTML", reply_markup=m)
        except Exception as e:
            bot.reply_to(msg, f"❌ {e}")

    # 2) requirements.txt
    elif state.startswith("waiting_req_"):
        pid = int(state.replace("waiting_req_", ""))
        try:
            fi = bot.get_file(msg.document.file_id)
            data = bot.download_file(fi.file_path)
            p = get_project(pid)
            rp = os.path.join(p[4], "requirements.txt")
            with open(rp, "wb") as f:
                f.write(data)
            with open(rp, "r", encoding="utf-8") as f:
                reqs = f.read().strip()
            update_project(pid, requirements=reqs)
            add_project_file(pid, "requirements.txt")
            del user_states[uid]

            txt = f"📋 <b>requirements.txt</b>\n\n<pre>{reqs[:400]}</pre>\n\n⚙️ ابدأ التثبيت؟"
            m = types.InlineKeyboardMarkup()
            m.row(
                btn_green("⚙️ نعم، ثبّت", f"install_{pid}"),
                btn_blue("⏭️ تخطي", f"proj_{pid}")
            )
            bot.send_message(msg.chat.id, txt, parse_mode="HTML", reply_markup=m)
        except Exception as e:
            bot.reply_to(msg, f"❌ {e}")

    # 3) ملف إضافي
    elif state.startswith("waiting_addfile_"):
        pid = int(state.replace("waiting_addfile_", ""))
        try:
            p = get_project(pid)
            if not p:
                bot.reply_to(msg, "❌ غير موجود")
                del user_states[uid]; return
            filename = msg.document.file_name
            ext = os.path.splitext(filename)[1].lower()
            basename = os.path.basename(filename)
            if ext not in ALLOWED_EXTS and basename not in ALLOWED_FILENAMES:
                bot.send_message(msg.chat.id, f"❌ نوع غير مدعوم: {ext}")
                return
            fi = bot.get_file(msg.document.file_id)
            data = bot.download_file(fi.file_path)
            fp = os.path.join(p[4], filename)
            with open(fp, "wb") as f:
                f.write(data)
            ok, chk = check_any_file(fp)
            add_project_file(pid, filename)
            del user_states[uid]
            emoji = "✅" if ok else "⚠️"
            txt = (
                f"{emoji} <b>تم إضافة الملف</b>\n\n"
                f"📄 <code>{filename}</code>\n"
                f"📊 الحجم: {get_file_size_str(fp)}\n\n"
            )
            if not ok: txt += chk
            else: txt += "🔍 الفحص: ✅ سليم"
            m = types.InlineKeyboardMarkup()
            m.add(btn_gray("🔙 رجوع", f"proj_{pid}"))
            bot.send_message(msg.chat.id, txt, parse_mode="HTML", reply_markup=m)
        except Exception as e:
            bot.reply_to(msg, f"❌ {e}")

# ============================================================
# 📤 زر رفع requirements
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("upload_req_"))
def cb_upload_req(call):
    pid = int(call.data[11:])
    user_states[call.from_user.id] = f"waiting_req_{pid}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", f"proj_{pid}"))
    bot.edit_message_text("📤 أرسل ملف requirements.txt",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

# ============================================================
# ⚙️ التثبيت المتدرج (بدون تعليق)
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("install_"))
def cb_install(call):
    pid = int(call.data[8:])
    p = get_project(pid)
    if not p: return
    reqs = p[8] or ""
    lines = [l.strip() for l in reqs.split("\n") if l.strip() and not l.startswith("#")]
    if not lines:
        bot.answer_callback_query(call.id, "⚠️ لا توجد مكتبات"); return

    bot.answer_callback_query(call.id, f"⏳ بدء تثبيت {len(lines)} مكتبة...")
    bot.send_message(
        call.message.chat.id,
        f"⚙️ <b>بدء التثبيت المتدرج</b>\n\n📦 {len(lines)} مكتبة",
        parse_mode="HTML"
    )

    def do_install():
        results = []
        for i, pkg in enumerate(lines, 1):
            bot.send_message(
                call.message.chat.id,
                f"⚙️ [{i}/{len(lines)}] جاري تثبيت: <code>{pkg}</code>",
                parse_mode="HTML"
            )
            ok, m = install_single_pkg(pid, pkg)
            results.append(m)
        update_project(pid, installed=1)

        final_txt = "📊 <b>نتيجة التثبيت:</b>\n\n" + "\n".join(results)
        final_txt += "\n\n🎯 <b>الخطوة التالية:</b>"
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(btn_green("▶️ تشغيل المشروع", f"start_{pid}"))
        m.add(btn_blue("📤 إرسال ملف تاني", f"addreq_{pid}"))
        m.add(btn_gray("🔙 رجوع", f"proj_{pid}"))
        bot.send_message(call.message.chat.id, final_txt,
                        parse_mode="HTML", reply_markup=m)

    threading.Thread(target=do_install, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("addreq_"))
def cb_addreq(call):
    pid = int(call.data[7:])
    user_states[call.from_user.id] = f"waiting_req_{pid}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", f"proj_{pid}"))
    bot.edit_message_text("📤 أرسل requirements.txt إضافي",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

# ============================================================
# 🗑️ حذف
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("del_"))
def cb_del(call):
    pid = int(call.data[4:])
    m = types.InlineKeyboardMarkup()
    m.row(
        btn_red("✅ نعم", f"cdel_{pid}"),
        btn_green("❌ إلغاء", f"proj_{pid}")
    )
    bot.edit_message_text("⚠️ <b>تأكيد الحذف؟</b>",
        call.message.chat.id, call.message.message_id,
        reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("cdel_"))
def cb_cdel(call):
    pid = int(call.data[5:])
    p = get_project(pid)
    stop_project(pid)
    if p:
        try: shutil.rmtree(p[4])
        except: pass
    delete_project(pid)
    bot.answer_callback_query(call.id, "تم الحذف")
    call.data = "my_projs"
    cb_my_projs(call)

# ============================================================
# 👑 لوحة المطور
# ============================================================
@bot.callback_query_handler(func=lambda c: c.data == "admin_panel")
def cb_admin(call):
    if not is_admin(call.from_user.id): return
    projs = get_all_projects()
    running = sum(1 for p in projs if is_running(p[0]))
    txt = (
        "╔══════════════════════════════╗\n"
        "║   👑 <b>لوحة المطور</b>\n"
        "╚══════════════════════════════╝\n\n"
        f"👥 <b>المستخدمين:</b> {get_user_count()}\n"
        f"📦 <b>المشاريع:</b> {len(projs)}\n"
        f"🟢 <b>شغّالة:</b> {running}\n"
        f"⏱️ <b>Uptime:</b> {calc_uptime(START_TIME.strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"🌐 <b>Tunnel:</b> {TUNNEL_URL or 'غير متصل'}"
    )
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(btn_red("📢 إعلان", "broadcast"), btn_blue("📊 إحصائيات", "admin_stats"))
    m.row(btn_blue("👥 المستخدمين", "admin_users"), btn_blue("📦 المشاريع", "admin_projs"))
    m.row(btn_green("🎨 تخصيص UI", "admin_ui"), btn_blue("🔗 تحديث Tunnel", "admin_tunnel"))
    m.add(btn_gray("🔙 رجوع", "main_menu"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data == "admin_ui")
def cb_admin_ui(call):
    if not is_admin(call.from_user.id): return
    ui = get_all_ui()
    txt = "🎨 <b>تخصيص الواجهة</b>\n\n"
    txt += f"👋 الترحيب: <code>{ui['welcome_text'][:40]}</code>\n"
    txt += f"📦 مشاريعي: <code>{ui['btn_my_projects']}</code>\n"
    txt += f"➕ مشروع جديد: <code>{ui['btn_new_project']}</code>\n"
    txt += f"👤 حسابي: <code>{ui['btn_account']}</code>\n"
    txt += f"❓ مساعدة: <code>{ui['btn_help']}</code>\n\n"
    txt += "اختر اللي عايز تعدله:"
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(btn_blue("👋 نص الترحيب", "ui_edit_welcome_text"))
    m.add(btn_blue("📦 اسم زر مشاريعي", "ui_edit_btn_my_projects"))
    m.add(btn_blue("➕ اسم زر مشروع جديد", "ui_edit_btn_new_project"))
    m.add(btn_blue("👤 اسم زر حسابي", "ui_edit_btn_account"))
    m.add(btn_blue("❓ اسم زر مساعدة", "ui_edit_btn_help"))
    m.add(btn_gray("🔙 رجوع", "admin_panel"))
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                             reply_markup=m, parse_mode="HTML")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("ui_edit_"))
def cb_ui_edit(call):
    if not is_admin(call.from_user.id): return
    key = call.data.replace("ui_edit_", "")
    user_states[call.from_user.id] = f"waiting_ui_{key}"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", "admin_ui"))
    current = get_ui(key)
    bot.edit_message_text(
        f"✏️ <b>عدّل:</b> <code>{key}</code>\n\n"
        f"القيمة الحالية:\n<code>{current}</code>\n\n"
        f"أرسل القيمة الجديدة:",
        call.message.chat.id, call.message.message_id,
        reply_markup=m, parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, "").startswith("waiting_ui_"))
def do_ui_edit(msg):
    if not is_admin(msg.from_user.id): return
    key = user_states[msg.from_user.id].replace("waiting_ui_", "")
    value = msg.text.strip()
    set_ui(key, value)
    del user_states[msg.from_user.id]
    bot.reply_to(msg, f"✅ تم تحديث <code>{key}</code>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "admin_tunnel")
def cb_admin_tunnel(call):
    if not is_admin(call.from_user.id): return
    bot.answer_callback_query(call.id, "🔄 جاري تحديث Tunnel...")
    def refresh():
        url = start_tunnel()
        if url:
            set_ui("public_url", url)
            bot.send_message(call.message.chat.id, f"✅ الرابط الجديد:\n<code>{url}</code>",
                            parse_mode="HTML")
        else:
            bot.send_message(call.message.chat.id, "❌ فشل تحديث Tunnel")
    threading.Thread(target=refresh, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data == "admin_users")
def cb_admin_users(call):
    if not is_admin(call.from_user.id): return
    users = get_all_users_full()
    txt = f"👥 <b>كل المستخدمين ({len(users)}):</b>\n\n"
    for u in users[:20]:
        projs = get_projects_by_owner(u[0])
        txt += f"🆔 <code>{u[0]}</code>\n"
        txt += f"   👤 {u[2] or 'N/A'} | @{u[1] or 'N/A'}\n"
        txt += f"   📦 {len(projs)} مشروع\n\n"
    if len(users) > 20:
        txt += f"... +{len(users)-20} مستخدم\n"
    m = types.InlineKeyboardMarkup()
    m.add(btn_gray("🔙 رجوع", "admin_panel"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "admin_projs")
def cb_admin_projs(call):
    if not is_admin(call.from_user.id): return
    projs = get_all_projects()
    txt = f"📦 <b>كل المشاريع ({len(projs)}):</b>\n\n"
    for p in projs[:20]:
        s = "🟢" if is_running(p[0]) else "🔴"
        owner = get_user(p[1])
        owner_name = owner[2] if owner else "N/A"
        txt += f"{s} <b>{p[2]}</b>\n"
        txt += f"   👤 {owner_name} (<code>{p[1]}</code>)\n"
        txt += f"   📁 {len(get_project_files(p[0]))} ملف\n\n"
    if len(projs) > 20:
        txt += f"... +{len(projs)-20} مشروع\n"
    m = types.InlineKeyboardMarkup()
    m.add(btn_gray("🔙 رجوع", "admin_panel"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "admin_stats")
def cb_admin_stats(call):
    if not is_admin(call.from_user.id): return
    projs = get_all_projects()
    running = sum(1 for p in projs if is_running(p[0]))
    txt = (f"📊 <b>إحصائيات</b>\n\n"
           f"👥 {get_user_count()} مستخدم\n"
           f"📦 {len(projs)} مشروع\n"
           f"🟢 {running} شغال\n"
           f"🌐 Tunnel: {TUNNEL_URL or 'غير متصل'}")
    m = types.InlineKeyboardMarkup()
    m.add(btn_gray("🔙 رجوع", "admin_panel"))
    bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "broadcast")
def cb_broadcast(call):
    if not is_admin(call.from_user.id): return
    user_states[call.from_user.id] = "broadcast_msg"
    m = types.InlineKeyboardMarkup()
    m.add(btn_red("إلغاء", "admin_panel"))
    bot.edit_message_text("📢 اكتب الرسالة:",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=m, parse_mode="HTML")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "broadcast_msg")
def do_broadcast(msg):
    if not is_admin(msg.from_user.id): return
    text = msg.text
    del user_states[msg.from_user.id]
    users = get_all_users()
    sent = 0
    bot.send_message(msg.chat.id, f"📢 جاري الإرسال لـ {len(users)}...")
    for uid in users:
        try:
            bot.send_message(uid, f"📢 <b>إعلان</b>\n\n{text}", parse_mode="HTML")
            sent += 1
            time.sleep(0.05)
        except: pass
    bot.send_message(msg.chat.id, f"✅ نجح: {sent}/{len(users)}")
    
# ============================================================
# 🌐 Web Dashboard + Reverse Proxy
# ============================================================
web = Flask(__name__)

WEB_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { margin:0; padding:0; box-sizing:border-box; font-family: system-ui, sans-serif; }
body { background: radial-gradient(circle at 20% 0%, #1a0033 0%, #0a0015 60%, #000 100%); color: #fff; min-height: 100vh; padding: 20px; }
.container { max-width: 1100px; margin: 0 auto; }
h1 { text-align: center; font-size: 2.4em; margin-bottom: 30px;
     background: linear-gradient(90deg, #00ffff, #ff00ff, #00ffff);
     background-size: 200% 200%; -webkit-background-clip: text;
     -webkit-text-fill-color: transparent; animation: shine 3s linear infinite; }
@keyframes shine { 0%{background-position:0% 50%} 100%{background-position:200% 50%} }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 25px; }
.card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,0,255,0.2); border-radius: 14px; padding: 20px; text-align: center; }
.card .num { font-size: 2.2em; font-weight: 700;
             background: linear-gradient(90deg, #00ffff, #ff00ff);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.card .lbl { color: #999; margin-top: 6px; font-size: 0.9em; }
.prj { background: rgba(255,255,255,0.03); border: 1px solid rgba(0,255,255,0.15);
       border-radius: 16px; padding: 20px; margin-bottom: 15px; }
.prj h3 { color: #00ffff; margin-bottom: 12px; }
.row { display: flex; justify-content: space-between; padding: 5px 0; color: #bbb; font-size: 0.9em; }
.badge { padding: 4px 14px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }
.badge.run { background: rgba(0,255,136,0.15); color: #00ff88; border: 1px solid #00ff88; }
.badge.stop { background: rgba(255,50,50,0.15); color: #ff5555; border: 1px solid #ff5555; }
.actions { margin-top: 15px; display: flex; gap: 8px; flex-wrap: wrap; }
.btn { padding: 10px 20px; border: none; border-radius: 10px; text-decoration: none;
       color: #fff; font-weight: 600; font-size: 0.9em; cursor: pointer; }
.btn-s { background: linear-gradient(135deg, #10b981, #059669); }
.btn-x { background: linear-gradient(135deg, #ef4444, #b91c1c); }
.btn-l { background: linear-gradient(135deg, #3b82f6, #1d4ed8); }
.btn-p { background: linear-gradient(135deg, #a855f7, #7e22ce); }
.tunnel { background: rgba(0,255,255,0.05); border: 1px solid #00ffff;
          border-radius: 12px; padding: 15px; margin-bottom: 20px; text-align: center; }
.tunnel a { color: #00ffff; word-break: break-all; text-decoration: none; }
.empty { text-align: center; color: #666; padding: 60px 20px; font-size: 1.2em; }
</style>
</head>
<body>
<div class="container">
  <h1>{{ title }}</h1>

  <div class="grid">
    <div class="card"><div class="num">{{ total }}</div><div class="lbl">📦 المشاريع</div></div>
    <div class="card"><div class="num" style="background:linear-gradient(90deg,#00ff88,#00ffff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ running }}</div><div class="lbl">🟢 شغّالة</div></div>
    <div class="card"><div class="num" style="background:linear-gradient(90deg,#ff5555,#ff00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ stopped }}</div><div class="lbl">🔴 موقوفة</div></div>
    <div class="card"><div class="num" style="background:linear-gradient(90deg,#a855f7,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ users }}</div><div class="lbl">👥 المستخدمين</div></div>
  </div>

  {% if tunnel %}
  <div class="tunnel">
    🌐 <b>الرابط العام:</b><br>
    <a href="{{ tunnel }}" target="_blank">{{ tunnel }}</a>
  </div>
  {% endif %}

  {% if projects %}
    {% for p in projects %}
    <div class="prj">
      <h3>{{ '🐍' if p[3] == 'bot' else '🌐' }} {{ p[2] }}</h3>
      <div class="row"><span>📄 الملف:</span><span><code>{{ p[5] }}</code></span></div>
      <div class="row"><span>🤖 البوت:</span><span>@{{ p[10] or '—' }}</span></div>
      {% if p[12] %}
      <div class="row"><span>🔗 الرابط:</span>
        <span><a href="{{ p[12] }}" target="_blank" style="color:#00ffff">{{ p[12] }}</a></span>
      </div>
      {% endif %}
      <div class="row"><span>⏱️ المدة:</span>
        <span>{{ uptime(p[18]) if running_map[p[0]] else '—' }}</span>
      </div>
      <div class="row"><span>📊 الحالة:</span>
        <span class="badge {{ 'run' if running_map[p[0]] else 'stop' }}">
          {{ '🟢 شغال' if running_map[p[0]] else '🔴 موقوف' }}
        </span>
      </div>
      <div class="actions">
        <a href="/start/{{ p[0] }}" class="btn btn-s">▶️ تشغيل</a>
        <a href="/stop/{{ p[0] }}" class="btn btn-x">⏹️ إيقاف</a>
        <a href="/logs/{{ p[0] }}" class="btn btn-l">📄 Logs</a>
        {% if p[3] == 'web' and p[12] %}
        <a href="{{ p[12] }}" target="_blank" class="btn btn-p">🌐 فتح الموقع</a>
        {% endif %}
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">📭 لا توجد مشاريع بعد</div>
  {% endif %}
</div>
</body>
</html>
"""

@web.route('/')
def home():
    projs = get_all_projects()
    running_map = {p[0]: is_running(p[0]) for p in projs}
    running = sum(1 for v in running_map.values() if v)
    return render_template_string(
        WEB_HTML,
        title=get_ui("dashboard_title"),
        projects=projs, total=len(projs),
        running=running, stopped=len(projs) - running,
        users=get_user_count(),
        running_map=running_map, uptime=calc_uptime,
        tunnel=get_public_url() if get_public_url().startswith("https://") else None
    )

@web.route('/start/<int:pid>')
def w_start(pid):
    ok, msg = start_project(pid)
    return f"""<body style='background:#000;color:#0f0;text-align:center;padding:100px;font-family:sans-serif'>
    <h1>{msg}</h1><a href='/' style='color:#0ff'>← رجوع</a></body>"""

@web.route('/stop/<int:pid>')
def w_stop(pid):
    ok, msg = stop_project(pid)
    return f"""<body style='background:#000;color:#0f0;text-align:center;padding:100px;font-family:sans-serif'>
    <h1>{msg}</h1><a href='/' style='color:#0ff'>← رجوع</a></body>"""

@web.route('/logs/<int:pid>')
def w_logs(pid):
    logs = get_logs(pid, 200)
    return f"""<body style='background:#000;color:#0f0;font-family:monospace;padding:20px'>
    <pre style='white-space:pre-wrap'>{logs}</pre>
    <a href='/' style='color:#0ff'>← رجوع</a></body>"""

# ============================================================
# 🔄 Reverse Proxy — يوجه الطلبات للمشاريع المستخدمة
# ============================================================
@web.route('/proxy/status')
def proxy_status():
    return {"status": "ok", "message": "Reverse Proxy شغال ✅"}

@web.route('/proxy/<int:pid>', defaults={'path': ''},
           methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@web.route('/proxy/<int:pid>/<path:path>',
           methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy(pid, path):
    """يوجه الطلبات للمشروع المستخدم"""
    p = get_project(pid)
    if not p:
        return "<h1>❌ المشروع غير موجود</h1>", 404
    if p[3] != "web":
        return "<h1>⚠️ ده مش مشروع Web</h1>", 400
    if not is_running(pid):
        return """
        <body style='background:#000;color:#f55;text-align:center;padding:100px;font-family:sans-serif'>
        <h1>⚠️ المشروع متوقف حالياً</h1>
        <p>صاحب المشروع لازم يشغله من البوت</p>
        </body>
        """, 503

    port = p[11]
    if not port:
        return "<h1>⚠️ لا يوجد بورت محدد</h1>", 500

    target = f"http://127.0.0.1:{port}/{path}"

    headers = {k: v for k, v in request.headers if k.lower() != 'host'}
    headers['X-Forwarded-For'] = request.remote_addr or ''
    headers['X-Forwarded-Proto'] = request.scheme
    headers['X-Forwarded-Host'] = request.host

    try:
        import requests as req
        resp = req.request(
            method=request.method, url=target,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            params=request.args,
            allow_redirects=False,
            timeout=60,
            stream=False
        )
        excluded = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        out_headers = [(k, v) for k, v in resp.raw.headers.items()
                       if k.lower() not in excluded]
        return Response(resp.content, resp.status_code, out_headers)

    except req.exceptions.ConnectionError:
        return """
        <body style='background:#000;color:#f55;text-align:center;padding:100px;font-family:sans-serif'>
        <h1>❌ فشل الاتصال بالمشروع</h1>
        <p>المشروع شغال بس مش بيرد على البورت</p>
        </body>
        """, 502
    except req.exceptions.Timeout:
        return "<h1>⏱️ انتهت مهلة الاتصال</h1>", 504
    except Exception as e:
        return f"<h1>❌ خطأ</h1><pre>{str(e)[:300]}</pre>", 500

# ============================================================
# 🔗 Tunnel (SSH + Cloudflare Fallback)
# ============================================================
def start_ssh_tunnel():
    """يستخدم localhost.run (SSH Tunnel مجاني)"""
    port = int(os.environ.get("PORT", 8080))
    print(f"[Tunnel/SSH] جاري تشغيل SSH Tunnel على البورت {port}...")
    try:
        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ServerAliveInterval=30",
             "-R", f"80:localhost:{port}",
             "nokey@localhost.run"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            bufsize=1
        )
        start = time.time()
        for line in proc.stdout:
            if time.time() - start > 45:
                break
            m = re.search(r'https://[a-zA-Z0-9-]+\.lhr\.life', line)
            if m:
                url = m.group(0)
                print(f"[Tunnel/SSH] ✅ {url}")
                return url
        print("[Tunnel/SSH] ⚠️ مفيش رابط، بنجرب Cloudflare...")
        return None
    except FileNotFoundError:
        print("[Tunnel/SSH] ❌ ssh مش موجود")
        return None
    except Exception as e:
        print(f"[Tunnel/SSH] ❌ {e}")
        return None

def start_cloudflare_tunnel():
    """Fallback: Cloudflare Tunnel"""
    cf_bin = "/tmp/cloudflared"
    tunnel_log = "/tmp/cloudflare_tunnel.log"
    print("[Tunnel/CF] جاري التشغيل...")
    try:
        if not os.path.exists(cf_bin):
            arch = platform.machine()
            if arch in ["aarch64", "arm64"]:
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
            else:
                url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
            try:
                urllib.request.urlretrieve(url, cf_bin)
                os.chmod(cf_bin, 0o755)
                print("[Tunnel/CF] ✅ اتنزّل")
            except Exception as e:
                print(f"[Tunnel/CF] ❌ فشل التنزيل: {e}")
                return None

        port = int(os.environ.get("PORT", 8080))
        log_fp = open(tunnel_log, "w")
        proc = subprocess.Popen(
            [cf_bin, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
            stdout=log_fp, stderr=subprocess.STDOUT
        )
        for _ in range(30):
            time.sleep(2)
            try:
                with open(tunnel_log, "r") as f:
                    content = f.read()
                m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', content)
                if m:
                    url = m.group(0)
                    print(f"[Tunnel/CF] ✅ {url}")
                    return url
            except: pass
        print("[Tunnel/CF] ⚠️ فشل الحصول على الرابط")
        return None
    except Exception as e:
        print(f"[Tunnel/CF] ❌ {e}")
        return None

def start_tunnel():
    """يشغل Tunnel — SSH أولاً، ثم Cloudflare"""
    global TUNNEL_URL
    url = start_ssh_tunnel()
    if not url:
        url = start_cloudflare_tunnel()
    if url:
        TUNNEL_URL = url
        set_ui("public_url", url)
        # إشعار الأدمنز
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    admin_id,
                    f"🌐 <b>الرابط العام جاهز!</b>\n\n"
                    f"🔗 <code>{url}</code>\n\n"
                    f"افتحه من أي مكان ✅",
                    parse_mode="HTML"
                )
            except: pass
        return url
    return None

# ============================================================
# ▶️ التشغيل
# ============================================================
def run_bot():
    print("[*] Bot started")
    while True:
        try:
            bot.polling(non_stop=False, timeout=30)
        except Exception as e:
            print(f"[Bot] Polling error: {e}")
            time.sleep(5)

def run_web():
    port = int(os.environ.get("PORT", 8080))
    print(f"[*] Web: http://0.0.0.0:{port}")
    web.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

# ============================================================
# 🚀 نقطة البداية
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("🚀 HOST BOT v10.0 — STARTING")
    print("=" * 55)

    # ✅ هل إحنا على منصة سحابية؟ (Render / Koyeb / Railway)
    on_cloud = any([
        os.environ.get("RENDER_EXTERNAL_URL"),
        os.environ.get("KOYEB_PUBLIC_DOMAIN"),
        os.environ.get("RAILWAY_PUBLIC_DOMAIN"),
        os.environ.get("FLY_APP_NAME"),
    ])

    # 1) Heartbeat
    threading.Thread(target=keep_alive, daemon=True).start()
    print("[*] Heartbeat started ✅")

    # 2) البوت
    threading.Thread(target=run_bot, daemon=True).start()
    print("[*] Bot thread started ✅")

    # 3) Tunnel — بس لو إحنا مش على منصة سحابية
    if not on_cloud:
        def delayed_tunnel():
            time.sleep(5)
            start_tunnel()
        threading.Thread(target=delayed_tunnel, daemon=True).start()
        print("[*] Tunnel thread started ✅ (local mode)")
    else:
        print(f"[*] Cloud mode — الرابط: {get_public_url()}")

    # 4) Flask (رئيسي)
    run_web()