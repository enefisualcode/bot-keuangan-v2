"""
BOT PENCATAT KEUANGAN - TELEGRAM (MULTI-USER)
==============================================
Setiap user pakai Google Spreadsheet MILIK SENDIRI.
Mapping user -> spreadsheet disimpan di sheet "Users" pada spreadsheet master
(milik pemilik bot).

Perintah:
  /start           -> panduan
  /daftar <id>     -> hubungkan spreadsheet milik user
  /info            -> lihat spreadsheet yang terhubung
  /catat <nominal> <kategori> <catatan>
  /masuk  <nominal> <catatan>
  kirim foto struk -> dibaca AI

Sheet yang dibuat otomatis di spreadsheet user:
  Pengeluaran : Tanggal | Kategori | Nominal | Merchant | Sumber | Catatan | Tipe Bayar
  Pemasukan   : Tanggal | Kategori | Nominal | Sumber   | Catatan
"""

import logging
import json
import re
import os
import uuid
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==========================================
# KONFIGURASI
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Spreadsheet MASTER milik pemilik bot -> tempat menyimpan daftar user
MASTER_SPREADSHEET_ID = os.environ.get("MASTER_SPREADSHEET_ID", "")
USERS_SHEET = os.environ.get("USERS_SHEET", "Users")

# Nama sheet di spreadsheet masing-masing user
SHEET_PENGELUARAN = os.environ.get("SHEET_PENGELUARAN", "Pengeluaran")
SHEET_PEMASUKAN = os.environ.get("SHEET_PEMASUKAN", "Pemasukan")
SHEET_DASHBOARD = os.environ.get("SHEET_DASHBOARD", "Dashboard")

CREDENTIALS_FILE = "credentials.json"
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if GOOGLE_CREDENTIALS_JSON:
    with open(CREDENTIALS_FILE, "w") as f:
        f.write(GOOGLE_CREDENTIALS_JSON)

# Email service account, dipakai untuk instruksi share ke user
try:
    with open(CREDENTIALS_FILE) as f:
        SERVICE_ACCOUNT_EMAIL = json.load(f).get("client_email", "(cek credentials.json)")
except Exception:
    SERVICE_ACCOUNT_EMAIL = "(cek credentials.json)"

HEADER_PENGELUARAN = ["Tanggal", "Kategori", "Nominal", "Merchant",
                      "Sumber", "Catatan", "Tipe Bayar"]
HEADER_PEMASUKAN = ["Tanggal", "Kategori", "Nominal", "Sumber", "Catatan"]
HEADER_USERS = ["user_id", "username", "spreadsheet_id", "tanggal_daftar"]

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==========================================
# GEMINI
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# GOOGLE SHEETS
# ==========================================
_client = None


def get_client():
    """Satu koneksi gspread dipakai berulang, supaya tidak auth tiap request."""
    global _client
    if _client is None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        _client = gspread.authorize(creds)
    return _client


def get_or_create_worksheet(spreadsheet, nama, header):
    """Ambil worksheet; kalau belum ada, buat sekalian dengan headernya."""
    try:
        return spreadsheet.worksheet(nama)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=nama, rows=1000, cols=len(header) + 3)
        ws.append_row(header, value_input_option="USER_ENTERED")
        return ws



# ------------------------------------------
# Dashboard otomatis di spreadsheet user
# ------------------------------------------
# CATATAN PENTING SOAL FORMULA
# Google Sheets memakai pemisah argumen yang berbeda tergantung lokal:
#   en_US        -> koma      : SUM(A1, B1)   array: {A1, B1}
#   id_ID / dll  -> titik koma: SUM(A1; B1)   array: {A1 \\ B1}
# Semua template di bawah memakai penanda netral:
#   ~  = pemisah argumen
#   ^  = pemisah kolom pada array literal
# Koma di dalam string QUERY ("select A, sum(C)") sengaja dibiarkan apa adanya
# karena itu bagian dari bahasa QUERY, bukan pemisah argumen formula.

T_KEY_PERIODE = '=TEXT(EDATE(TODAY()~IF(DAY(TODAY())>=25~0~-1))~"YYYY-MM")'

T_LABEL_PERIODE = (
    '=IF(DAY(TODAY())>=25~'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())~25)~"d mmm")&" - "&'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())+1~24)~"d mmm yyyy")~'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())-1~25)~"d mmm")&" - "&'
    'TEXT(DATE(YEAR(TODAY())~MONTH(TODAY())~24)~"d mmm yyyy"))'
)


def _t_helper(sheet):
    """Label periode 25-24 untuk tiap baris transaksi."""
    return (
        '=ARRAYFORMULA(IF({s}!A2:A5000=""~""~'
        'TEXT(EDATE({s}!A2:A5000~IF(DAY({s}!A2:A5000)>=25~0~-1))~"YYYY-MM")))'
    ).format(s=sheet)


def deteksi_pemisah(ss):
    """Tentukan pemisah argumen dari lokal spreadsheet.
    Lokal yang memakai koma sebagai desimal (id_ID, de_DE, ...) memakai ';'."""
    try:
        locale = (ss.fetch_sheet_metadata()
                  .get("properties", {}).get("locale", "en_US"))
    except Exception:
        locale = "en_US"
    if locale.startswith(("en", "ms", "ja", "ko", "zh", "th", "he", "iw")):
        return ",", ","
    return ";", "\\"


def _isi_dashboard(ws, sep, colsep):
    """Tulis semua formula ke sheet Dashboard memakai pemisah yang sesuai."""

    def f(t):
        return t.replace("~", sep).replace("^", colsep)

    P, M = SHEET_PENGELUARAN, SHEET_PEMASUKAN

    ws.batch_update([
        # --- Blok ringkasan (A:B) ---
        {"range": "A1", "values": [["  RINGKASAN PERIODE BERJALAN"]]},
        {"range": "A2:A6", "values": [
            ["Periode"], ["Total Pemasukan"], ["Total Pengeluaran"],
            ["Selisih"], ["Rata-rata Harian"],
        ]},
        {"range": "B2", "values": [[f(T_LABEL_PERIODE)]]},
        {"range": "B3", "values": [[f(
            '=SUMIF($M$2:$M$5000~$K$1~' + M + '!$C$2:$C$5000)')]]},
        {"range": "B4", "values": [[f(
            '=SUMIF($L$2:$L$5000~$K$1~' + P + '!$C$2:$C$5000)')]]},
        {"range": "B5", "values": [["=B3-B4"]]},
        {"range": "B6", "values": [[f(
            '=IFERROR(B4/COUNTA(UNIQUE(FILTER(' + P + '!$A$2:$A$5000~'
            '$L$2:$L$5000=$K$1)))~0)')]]},

        # --- Blok pengeluaran per kategori (A8:B) ---
        {"range": "A8", "values": [["  PENGELUARAN PER KATEGORI"]]},
        {"range": "A9:B9", "values": [["Kategori", "Total"]]},
        {"range": "A10", "values": [[f(
            '=IFERROR(SORT(UNIQUE(FILTER($N$2:$N$5000~'
            '$N$2:$N$5000<>""))~1~TRUE)~"")')]]},
        {"range": "B10", "values": [[f(
            '=ARRAYFORMULA(IF($A$10:$A$40=""~""~'
            'SUMIF($N$2:$N$5000~$A$10:$A$40~'
            + P + '!$C$2:$C$5000)))')]]},

        # --- Blok rekap harian (D:E) ---
        {"range": "D1", "values": [["  REKAP HARIAN"]]},
        {"range": "D2", "values": [[f(
            '=IFERROR(QUERY(' + P + '!A2:C5000~'
            '"select A, sum(C) where A is not null '
            'group by A order by A desc '
            "label A 'Tanggal', sum(C) 'Total'\"~0)~\"\")"
        )]]},

        # --- Blok riwayat per periode (G:I) ---
        {"range": "G1", "values": [["  RIWAYAT PER PERIODE"]]},
        {"range": "G2:I2", "values": [["Periode", "Pengeluaran", "Pemasukan"]]},
        {"range": "G3", "values": [[f(
            '=IFERROR(SORT(UNIQUE(FILTER($L$2:$L$5000~'
            '$L$2:$L$5000<>""))~1~FALSE)~"")')]]},
        {"range": "H3", "values": [[f(
            '=ARRAYFORMULA(IF($G$3:$G$300=""~""~'
            'SUMIF($L$2:$L$5000~$G$3:$G$300~' + P + '!$C$2:$C$5000)))')]]},
        {"range": "I3", "values": [[f(
            '=ARRAYFORMULA(IF($G$3:$G$300=""~""~'
            'SUMIF($M$2:$M$5000~$G$3:$G$300~' + M + '!$C$2:$C$5000)))')]]},

        # --- Sel bantuan (K:M), disembunyikan ---
        {"range": "K1", "values": [[f(T_KEY_PERIODE)]]},
        {"range": "L2", "values": [[f(_t_helper(P))]]},
        {"range": "M2", "values": [[f(_t_helper(M))]]},
        {"range": "N2", "values": [[f(
            '=ARRAYFORMULA(IF(($L$2:$L$5000=$K$1)*'
            '(' + P + '!$B$2:$B$5000<>"")~'
            + P + '!$B$2:$B$5000~""))')]]},
    ], value_input_option="USER_ENTERED")


def _rapikan_dashboard(ss, ws):
    sid = ws.id
    judul = {"textFormat": {"bold": True, "fontSize": 10,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
             "backgroundColor": {"red": 0.25, "green": 0.25, "blue": 0.25},
             "verticalAlignment": "MIDDLE"}
    tebal = {"textFormat": {"bold": True, "fontSize": 10},
             "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}}
    angka = {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}

    def rng(r1, c1, r2, c2):
        return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2}

    def repeat(r, fmt, fields):
        return {"repeatCell": {"range": r, "cell": {"userEnteredFormat": fmt},
                               "fields": fields}}

    reqs = [
        {"mergeCells": {"range": rng(0, 0, 1, 2), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(0, 3, 1, 5), "mergeType": "MERGE_ALL"}},
        {"mergeCells": {"range": rng(0, 6, 1, 9), "mergeType": "MERGE_ALL"}},
        repeat(rng(0, 0, 1, 2), judul, "userEnteredFormat"),
        repeat(rng(0, 3, 1, 5), judul, "userEnteredFormat"),
        repeat(rng(0, 6, 1, 9), judul, "userEnteredFormat"),
        {"mergeCells": {"range": rng(7, 0, 8, 2), "mergeType": "MERGE_ALL"}},
        repeat(rng(7, 0, 8, 2), judul, "userEnteredFormat"),
        repeat(rng(8, 0, 9, 2), tebal, "userEnteredFormat"),
        repeat(rng(9, 1, 40, 2), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(1, 3, 2, 5), tebal, "userEnteredFormat"),
        repeat(rng(1, 6, 2, 9), tebal, "userEnteredFormat"),
        repeat(rng(2, 1, 6, 2), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(2, 3, 300, 4),
               {"numberFormat": {"type": "DATE",
                                 "pattern": "ddd, dd mmm yyyy"}},
               "userEnteredFormat.numberFormat"),
        repeat(rng(2, 4, 300, 5), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(2, 7, 300, 9), angka, "userEnteredFormat.numberFormat"),
        repeat(rng(4, 0, 5, 2),
               {"textFormat": {"bold": True, "fontSize": 10}},
               "userEnteredFormat.textFormat"),
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 10, "endIndex": 14},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "index": 0,
                           "gridProperties": {"hideGridlines": True}},
            "fields": "index,gridProperties.hideGridlines"}},
    ]
    for c1, c2, px in [(0, 1, 165), (1, 2, 135), (2, 3, 24),
                       (3, 4, 150), (4, 5, 110), (5, 6, 24),
                       (6, 7, 100), (7, 8, 120), (8, 9, 120)]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": c1, "endIndex": c2},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})

    ss.batch_update({"requests": reqs})


def rapikan_header(ss, ws, jumlah_kolom, warna):
    """Percantik baris header sheet data: tebal, berwarna, dibekukan."""
    sid = ws.id
    lebar = {SHEET_PENGELUARAN: [(0, 1, 110), (1, 2, 120), (2, 3, 110),
                                 (3, 4, 200), (4, 5, 85), (5, 6, 190),
                                 (6, 7, 100)],
             SHEET_PEMASUKAN: [(0, 1, 110), (1, 2, 165), (2, 3, 120),
                               (3, 4, 85), (4, 5, 200)]}
    reqs = [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": jumlah_kolom},
            "cell": {"userEnteredFormat": {
                "backgroundColor": warna,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid,
                           "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
            "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {
                "numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
            "fields": "userEnteredFormat.numberFormat"}},
    ]
    for c1, c2, px in lebar.get(ws.title, []):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": c1, "endIndex": c2},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    try:
        ss.batch_update({"requests": reqs})
    except Exception as e:
        logger.error(f"Gagal merapikan header {ws.title}: {e}")


def hapus_sheet_bawaan(ss):
    """Hapus Sheet1 bawaan Google kalau memang kosong dan bukan satu-satunya."""
    bawaan = {"sheet1", "sheet 1", "lembar1", "lembar 1"}
    try:
        semua = ss.worksheets()
        if len(semua) <= 1:
            return
        for ws in semua:
            if ws.title.strip().lower() in bawaan and not ws.get_all_values():
                ss.del_worksheet(ws)
                logger.info(f"Sheet bawaan '{ws.title}' dihapus")
                break
    except Exception as e:
        logger.error(f"Gagal hapus sheet bawaan: {e}")


SHEET_GRAFIK = os.environ.get("SHEET_GRAFIK", "Grafik")


def setup_grafik(ss, dash_id):
    """Buat sheet Grafik berisi 3 chart yang menarik data dari Dashboard."""
    try:
        ss.worksheet(SHEET_GRAFIK)
        return False
    except gspread.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=SHEET_GRAFIK, rows=120, cols=12)
    gid = ws.id

    def sumber(r1, c1, r2, c2):
        """Rentang data di sheet Dashboard."""
        return {"sources": [{"sheetId": dash_id,
                             "startRowIndex": r1, "endRowIndex": r2,
                             "startColumnIndex": c1, "endColumnIndex": c2}]}

    def posisi(baris):
        return {"overlayPosition": {
            "anchorCell": {"sheetId": gid, "rowIndex": baris, "columnIndex": 0},
            "offsetXPixels": 10, "offsetYPixels": 10,
            "widthPixels": 760, "heightPixels": 380}}

    def sumbu(judul_x, judul_y):
        return [{"position": "BOTTOM_AXIS", "title": judul_x},
                {"position": "LEFT_AXIS", "title": judul_y}]

    # 1. Pie: komposisi pengeluaran per kategori (periode berjalan)
    pie = {"addChart": {"chart": {
        "spec": {
            "title": "Pengeluaran per Kategori — Periode Berjalan",
            "pieChart": {
                "legendPosition": "RIGHT_LEGEND",
                "threeDimensional": False,
                "pieHole": 0.4,
                "domain": {"sourceRange": sumber(9, 0, 40, 1)},   # A10:A40
                "series": {"sourceRange": sumber(9, 1, 40, 2)},   # B10:B40
            }},
        "position": posisi(0)}}}

    # 2. Kolom: pengeluaran harian
    harian = {"addChart": {"chart": {
        "spec": {
            "title": "Pengeluaran Harian",
            "basicChart": {
                "chartType": "COLUMN",
                "legendPosition": "NO_LEGEND",
                "headerCount": 1,
                "axis": sumbu("Tanggal", "Rupiah"),
                "domains": [{"domain": {"sourceRange": sumber(1, 3, 33, 4)}}],
                "series": [{"series": {"sourceRange": sumber(1, 4, 33, 5)},
                            "targetAxis": "LEFT_AXIS"}],
            }},
        "position": posisi(20)}}}

    # 3. Kolom ganda: pemasukan vs pengeluaran tiap periode
    periode = {"addChart": {"chart": {
        "spec": {
            "title": "Pemasukan vs Pengeluaran per Periode",
            "basicChart": {
                "chartType": "COLUMN",
                "legendPosition": "BOTTOM_LEGEND",
                "headerCount": 1,
                "axis": sumbu("Periode", "Rupiah"),
                "domains": [{"domain": {"sourceRange": sumber(1, 6, 20, 7)}}],
                "series": [
                    {"series": {"sourceRange": sumber(1, 8, 20, 9)},
                     "targetAxis": "LEFT_AXIS"},   # Pemasukan
                    {"series": {"sourceRange": sumber(1, 7, 20, 8)},
                     "targetAxis": "LEFT_AXIS"},   # Pengeluaran
                ],
            }},
        "position": posisi(40)}}}

    try:
        ss.batch_update({"requests": [
            pie, harian, periode,
            {"updateSheetProperties": {
                "properties": {"sheetId": gid,
                               "gridProperties": {"hideGridlines": True}},
                "fields": "gridProperties.hideGridlines"}},
        ]})
    except Exception as e:
        logger.error(f"Gagal membuat grafik: {e}")
        return False
    return True


def setup_dashboard(ss):
    """Buat sheet Dashboard berisi ringkasan otomatis.
    Kalau sudah ada, dibiarkan supaya kustomisasi user tidak hilang."""
    try:
        return ss.worksheet(SHEET_DASHBOARD), False
    except gspread.WorksheetNotFound:
        pass

    ws = ss.add_worksheet(title=SHEET_DASHBOARD, rows=300, cols=14)

    sep, colsep = deteksi_pemisah(ss)
    _isi_dashboard(ws, sep, colsep)

    # Verifikasi: kalau sel bantuan K1 error, berarti tebakan pemisah salah.
    # Tulis ulang memakai pemisah satunya.
    try:
        cek = ws.acell("K1", value_render_option="UNFORMATTED_VALUE").value
        if isinstance(cek, str) and cek.startswith("#"):
            alt = (";", "\\") if sep == "," else (",", ",")
            logger.warning(f"Pemisah '{sep}' ditolak, coba '{alt[0]}'")
            _isi_dashboard(ws, alt[0], alt[1])
    except Exception as e:
        logger.error(f"Gagal verifikasi formula dashboard: {e}")

    _rapikan_dashboard(ss, ws)
    return ws, True


# ------------------------------------------
# Daftar user (mapping user_id -> spreadsheet_id)
# ------------------------------------------
_user_map = None  # cache di memori


def get_users_sheet():
    ss = get_client().open_by_key(MASTER_SPREADSHEET_ID)
    return get_or_create_worksheet(ss, USERS_SHEET, HEADER_USERS)


def load_user_map(force=False):
    global _user_map
    if _user_map is not None and not force:
        return _user_map
    mapping = {}
    try:
        rows = get_users_sheet().get_all_records()
        for r in rows:
            uid = str(r.get("user_id", "")).strip()
            sid = str(r.get("spreadsheet_id", "")).strip()
            if uid and sid:
                mapping[uid] = sid
    except Exception as e:
        logger.error(f"Gagal load daftar user: {e}")
    _user_map = mapping
    return _user_map


def simpan_user(user_id, username, spreadsheet_id):
    """Tambah user baru, atau update spreadsheet_id kalau user sudah pernah daftar."""
    ws = get_users_sheet()
    uid = str(user_id)
    try:
        cell = ws.find(uid, in_column=1)
    except Exception:
        cell = None
    tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
    if cell:
        ws.update(
            f"A{cell.row}:D{cell.row}",
            [[uid, username or "-", spreadsheet_id, tgl]],
            value_input_option="USER_ENTERED",
        )
    else:
        ws.append_row(
            [uid, username or "-", spreadsheet_id, tgl],
            value_input_option="USER_ENTERED",
        )
    load_user_map(force=True)


def get_spreadsheet_id(user_id):
    return load_user_map().get(str(user_id))


# ------------------------------------------
# Tulis transaksi ke spreadsheet milik user
# ------------------------------------------
def simpan_pengeluaran(user_id, tanggal, kategori, nominal, merchant,
                       sumber, catatan, tipe_bayar):
    sid = get_spreadsheet_id(user_id)
    ss = get_client().open_by_key(sid)
    ws = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
    ws.append_row(
        [tanggal, kategori, nominal, merchant, sumber, catatan, tipe_bayar],
        value_input_option="USER_ENTERED",
    )


def simpan_pemasukan(user_id, tanggal, kategori, nominal, sumber, catatan):
    sid = get_spreadsheet_id(user_id)
    ss = get_client().open_by_key(sid)
    ws = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)
    ws.append_row(
        [tanggal, kategori, nominal, sumber, catatan],
        value_input_option="USER_ENTERED",
    )


# ==========================================
# DATA SEMENTARA
# Pakai token unik per transaksi, supaya kirim beberapa struk sekaligus
# tidak saling menimpa (bug versi sebelumnya).
# ==========================================
pending = {}  # token -> dict data


def buat_token(data):
    token = uuid.uuid4().hex[:10]
    pending[token] = data
    if len(pending) > 500:  # jaga-jaga supaya memori tidak menumpuk
        for k in list(pending)[:100]:
            pending.pop(k, None)
    return token


# ==========================================
# KEYBOARD
# ==========================================
def keyboard_tipe_bayar(token):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 Cash", callback_data=f"bayar_cash|{token}"),
        InlineKeyboardButton("💳 Pay Later", callback_data=f"bayar_paylater|{token}"),
    ]])


def keyboard_konfirmasi_struk(token):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Simpan", callback_data=f"struk_simpan|{token}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"struk_batal|{token}"),
    ]])


KATEGORI_MASUK = {
    "gaji": "💼 Gaji/Tunjangan",
    "freelance": "💸 Freelance",
    "bonus": "🎁 Bonus/THR",
    "investasi": "📈 Investasi",
    "transfer": "🔄 Transfer Masuk",
    "lainnya": "📦 Lainnya",
}


def keyboard_kategori_pemasukan(token):
    keys = list(KATEGORI_MASUK.items())
    rows = []
    for i in range(0, len(keys), 2):
        rows.append([
            InlineKeyboardButton(label, callback_data=f"masuk_{kode}|{token}")
            for kode, label in keys[i:i + 2]
        ])
    return InlineKeyboardMarkup(rows)


# ==========================================
# PANDUAN PENDAFTARAN
# ==========================================
def pesan_belum_daftar():
    return (
        "🔐 *Kamu belum menghubungkan spreadsheet.*\n\n"
        "Bot ini menulis ke Google Spreadsheet milikmu sendiri, "
        "jadi datamu tidak tercampur dengan pengguna lain.\n\n"
        "*Cara menghubungkan (5 menit):*\n\n"
        "1️⃣ Buka Google Sheets, buat spreadsheet baru (boleh kosong).\n\n"
        "2️⃣ Klik *Bagikan*, masukkan email ini sebagai *Editor*:\n"
        f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
        "3️⃣ Copy *ID spreadsheet* dari URL. Contoh URL:\n"
        "`docs.google.com/spreadsheets/d/`*`1AbCdEfGh123`*`/edit`\n"
        "yang dicetak tebal itu ID-nya.\n\n"
        "4️⃣ Kirim ke saya:\n"
        "`/daftar 1AbCdEfGh123`\n\n"
        "Kolom, sheet, dan dashboard akan saya buat otomatis.\n"
        "_Sheet1 bawaan boleh kamu hapus setelah terhubung._"
    )


# ==========================================
# HANDLER: /start
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return
    await update.message.reply_text(
        "👋 Halo! Saya bot pencatat keuangan kamu.\n\n"
        "📝 *Cara pakai:*\n\n"
        "1️⃣ *Pengeluaran manual*\n"
        "`/catat 50000 Makan nasi goreng kantor`\n\n"
        "2️⃣ *Pemasukan*\n"
        "`/masuk 5000000 Gaji bulan ini`\n\n"
        "3️⃣ *Dari struk*\n"
        "Kirim foto struk, saya baca otomatis. Kirim satu foto per struk.\n\n"
        "ℹ️ `/info` lihat spreadsheet yang terhubung\n"
        "🧪 `/dummy` isi data contoh untuk mencoba Dashboard\n"
        "🧹 `/hapusdummy` hapus lagi data contoh itu",
        parse_mode="Markdown",
    )


# ==========================================
# HANDLER: /daftar
# ==========================================
async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    raw = args[0].strip()
    # Terima ID mentah maupun URL lengkap
    m = re.search(r"/d/([a-zA-Z0-9-_]{20,})", raw)
    spreadsheet_id = m.group(1) if m else raw

    if len(spreadsheet_id) < 20 or "/" in spreadsheet_id:
        await update.message.reply_text(
            "⚠️ ID spreadsheet sepertinya tidak valid.\n"
            "Kirim ID-nya saja (bagian setelah `/d/` di URL), "
            "atau tempel URL lengkapnya.",
            parse_mode="Markdown",
        )
        return

    await update.message.reply_text("🔍 Mengecek akses ke spreadsheet...")

    try:
        ss = get_client().open_by_key(spreadsheet_id)
        judul = ss.title
        ws_out = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
        ws_in = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)
        rapikan_header(ss, ws_out, len(HEADER_PENGELUARAN),
                       {"red": 0.15, "green": 0.35, "blue": 0.55})   # biru tua
        rapikan_header(ss, ws_in, len(HEADER_PEMASUKAN),
                       {"red": 0.13, "green": 0.42, "blue": 0.31})   # hijau tua
        ws_dash, _ = setup_dashboard(ss)
        setup_grafik(ss, ws_dash.id)
        hapus_sheet_bawaan(ss)
    except gspread.SpreadsheetNotFound:
        await update.message.reply_text(
            "❌ Spreadsheet tidak ditemukan atau saya belum diberi akses.\n\n"
            "Pastikan sudah kamu *Bagikan* ke email ini sebagai *Editor*:\n"
            f"`{SERVICE_ACCOUNT_EMAIL}`\n\n"
            "Lalu coba `/daftar` lagi.",
            parse_mode="Markdown",
        )
        return
    except Exception as e:
        logger.error(f"Gagal daftar {user.id}: {e}")
        await update.message.reply_text(
            "❌ Gagal menghubungkan spreadsheet. "
            "Cek ID dan izin aksesnya, lalu coba lagi."
        )
        return

    try:
        simpan_user(user.id, user.username, spreadsheet_id)
    except Exception as e:
        logger.error(f"Gagal simpan user {user.id}: {e}")
        await update.message.reply_text(
            "❌ Spreadsheet bisa diakses, tapi pendaftaran gagal disimpan. "
            "Coba lagi beberapa saat."
        )
        return

    await update.message.reply_text(
        f"✅ *Berhasil terhubung!*\n\n"
        f"📄 Spreadsheet: *{judul}*\n"
        f"📑 Sheet *{SHEET_PENGELUARAN}*, *{SHEET_PEMASUKAN}*, "
        f"*{SHEET_DASHBOARD}*, dan *{SHEET_GRAFIK}* sudah siap.\n\n"
        f"📊 Dashboard akan terisi sendiri begitu ada transaksi.\n\n"
        f"Coba sekarang:\n`/catat 15000 Makan nasi goreng`",
        parse_mode="Markdown",
    )


# ==========================================
# HANDLER: /info
# ==========================================
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = get_spreadsheet_id(update.effective_user.id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return
    try:
        judul = get_client().open_by_key(sid).title
    except Exception:
        judul = "(tidak bisa diakses — cek izin share)"
    await update.message.reply_text(
        f"📄 Spreadsheet terhubung: *{judul}*\n"
        f"🔗 https://docs.google.com/spreadsheets/d/{sid}/edit\n\n"
        f"Mau ganti spreadsheet? Kirim `/daftar <id_baru>`",
        parse_mode="Markdown",
    )


# ==========================================
# HANDLER: /dummy dan /hapusdummy (untuk uji coba)
# ==========================================
def _tanggal_periode(offset_hari):
    from datetime import timedelta
    return (datetime.now() - timedelta(days=offset_hari)).strftime("%Y-%m-%d")


DUMMY_PENGELUARAN = [
    (1, "Makan", 25000, "Warteg Bahari", "Nasi Ayam", "Cash"),
    (2, "Transport", 12000, "Gojek", "Ke Kantor", "Pay Later"),
    (3, "Makan", 43500, "BreadTalk", "Roti", "Cash"),
    (5, "Belanja", 87000, "Indomaret", "Belanja Bulanan", "Cash"),
    (7, "Makan", 18000, "Fore Coffee", "Kopi", "Pay Later"),
    (9, "Tagihan", 150000, "PLN", "Listrik", "Cash"),
    (12, "Transport", 3000, "KRL", "Stasiun Bogor", "Cash"),
    (16, "Makan", 65000, "Shabu Hachi", "Makan Siang", "Pay Later"),
    (22, "Belanja", 45000, "Tokopedia", "Aksesoris", "Pay Later"),
    (28, "Makan", 30000, "Kopi Kenangan", "Nongkrong", "Cash"),
    (34, "Transport", 8000, "Parkir", "Mall", "Cash"),
    (40, "Lainnya", 20000, "Barbershop", "Cukur Rambut", "Cash"),
]

DUMMY_PEMASUKAN = [
    (2, "💼 Gaji/Tunjangan", 5500000, "Gaji Bulan Ini"),
    (10, "💸 Freelance", 750000, "Proyek Desain"),
    (33, "💼 Gaji/Tunjangan", 5500000, "Gaji Bulan Lalu"),
    (38, "🎁 Bonus/THR", 300000, "Bonus Kinerja"),
]


async def dummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("🧪 Membuat data contoh...")
    try:
        ss = get_client().open_by_key(sid)
        ws_out = get_or_create_worksheet(ss, SHEET_PENGELUARAN, HEADER_PENGELUARAN)
        ws_in = get_or_create_worksheet(ss, SHEET_PEMASUKAN, HEADER_PEMASUKAN)

        baris_out = [[_tanggal_periode(h), kat, nom, mer, "Dummy", cat, tipe]
                     for h, kat, nom, mer, cat, tipe in DUMMY_PENGELUARAN]
        baris_in = [[_tanggal_periode(h), kat, nom, "Dummy", cat]
                    for h, kat, nom, cat in DUMMY_PEMASUKAN]

        ws_out.append_rows(baris_out, value_input_option="USER_ENTERED")
        ws_in.append_rows(baris_in, value_input_option="USER_ENTERED")

        await update.message.reply_text(
            f"✅ *Data contoh dibuat*\n\n"
            f"📤 {len(baris_out)} pengeluaran\n"
            f"📥 {len(baris_in)} pemasukan\n"
            f"Tersebar di periode ini dan periode sebelumnya.\n\n"
            f"Buka sheet *{SHEET_DASHBOARD}* untuk melihat hasilnya.\n"
            f"Hapus lagi dengan `/hapusdummy`",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Gagal buat dummy {user_id}: {e}")
        await update.message.reply_text("❌ Gagal membuat data contoh.")


def _hapus_baris_dummy(ss, nama_sheet, kolom_sumber, header):
    """Hapus semua baris yang kolom Sumber-nya bertuliskan 'Dummy'."""
    ws = get_or_create_worksheet(ss, nama_sheet, header)
    semua = ws.get_all_values()
    target = [i for i, r in enumerate(semua)
              if i > 0 and len(r) > kolom_sumber and r[kolom_sumber] == "Dummy"]
    if not target:
        return 0
    reqs = []
    for i in sorted(target, reverse=True):  # dari bawah, supaya indeks tidak geser
        reqs.append({"deleteDimension": {"range": {
            "sheetId": ws.id, "dimension": "ROWS",
            "startIndex": i, "endIndex": i + 1}}})
    ss.batch_update({"requests": reqs})
    return len(target)


async def hapusdummy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sid = get_spreadsheet_id(user_id)
    if not sid:
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("🧹 Menghapus data contoh...")
    try:
        ss = get_client().open_by_key(sid)
        n1 = _hapus_baris_dummy(ss, SHEET_PENGELUARAN, 4, HEADER_PENGELUARAN)
        n2 = _hapus_baris_dummy(ss, SHEET_PEMASUKAN, 3, HEADER_PEMASUKAN)
        await update.message.reply_text(
            f"✅ Data contoh dihapus.\n"
            f"📤 {n1} pengeluaran, 📥 {n2} pemasukan.\n\n"
            f"Data asli kamu tidak tersentuh."
        )
    except Exception as e:
        logger.error(f"Gagal hapus dummy {user_id}: {e}")
        await update.message.reply_text("❌ Gagal menghapus data contoh.")


# ==========================================
# HANDLER: /catat
# ==========================================
async def catat_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Format salah.\n\n"
            "Contoh: `/catat 50000 Makan nasi goreng`\n"
            "Format: /catat [nominal] [kategori] [catatan opsional]",
            parse_mode="Markdown",
        )
        return

    try:
        nominal = int(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus angka. Contoh: /catat 50000 Makan")
        return

    data = {
        "user_id": user_id,
        "jenis": "pengeluaran",
        "tanggal": datetime.now().strftime("%Y-%m-%d"),
        "kategori": args[1].title(),
        "nominal": nominal,
        "merchant": "-",
        "sumber": "Manual",
        "catatan": " ".join(args[2:]).title() if len(args) > 2 else "",
    }
    token = buat_token(data)

    await update.message.reply_text(
        f"📋 *Detail Pengeluaran:*\n\n"
        f"📅 Tanggal: {data['tanggal']}\n"
        f"🏷️ Kategori: {data['kategori']}\n"
        f"💰 Nominal: Rp{nominal:,}\n"
        f"📝 Catatan: {data['catatan'] or '-'}\n\n"
        f"Pilih tipe pembayaran:",
        parse_mode="Markdown",
        reply_markup=keyboard_tipe_bayar(token),
    )


# ==========================================
# HANDLER: /masuk
# ==========================================
async def catat_masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "⚠️ Format salah.\n\n"
            "Contoh: `/masuk 5000000 Gaji bulan ini`\n"
            "Format: /masuk [nominal] [catatan opsional]",
            parse_mode="Markdown",
        )
        return

    try:
        nominal = int(args[0].replace(".", "").replace(",", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus angka. Contoh: /masuk 5000000")
        return

    data = {
        "user_id": user_id,
        "jenis": "pemasukan",
        "tanggal": datetime.now().strftime("%Y-%m-%d"),
        "nominal": nominal,
        "catatan": " ".join(args[1:]).title() if len(args) > 1 else "",
    }
    token = buat_token(data)

    await update.message.reply_text(
        f"📋 *Detail Pemasukan:*\n\n"
        f"📅 Tanggal: {data['tanggal']}\n"
        f"💰 Nominal: Rp{nominal:,}\n"
        f"📝 Catatan: {data['catatan'] or '-'}\n\n"
        f"Pilih kategori pemasukan:",
        parse_mode="Markdown",
        reply_markup=keyboard_kategori_pemasukan(token),
    )


# ==========================================
# HANDLER: foto struk
# ==========================================
async def terima_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_spreadsheet_id(user_id):
        await update.message.reply_text(pesan_belum_daftar(), parse_mode="Markdown")
        return

    await update.message.reply_text("📸 Struk diterima, sedang dibaca...")
    hari_ini = datetime.now().strftime("%Y-%m-%d")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        prompt = f"""
        Kamu adalah asisten yang membaca struk belanja/pembayaran.
        Hari ini adalah {hari_ini}. Gunakan ini sebagai acuan tahun,
        JANGAN menebak tahun lain kecuali struk mencantumkan tahun dengan jelas.

        Baca gambar struk ini dan balas dengan JSON saja, tanpa teks lain,
        tanpa markdown backticks:

        {{
            "merchant": "nama toko/tempat",
            "tanggal": "YYYY-MM-DD (kalau tidak jelas gunakan {hari_ini})",
            "nominal": angka_total_tanpa_titik_atau_koma,
            "kategori": "Makan / Transport / Belanja / Tagihan / Lainnya"
        }}

        Ambil TOTAL akhir yang dibayar.
        Jika gambar berisi LEBIH DARI SATU struk, isi nominal dengan -1.
        Jika gambar tidak jelas atau bukan struk, isi nominal dengan 0.
        """

        response = gemini_model.generate_content(
            [prompt, {"mime_type": "image/jpeg", "data": bytes(photo_bytes)}]
        )
        teks = re.sub(r"^```json\s*|\s*```$", "", response.text.strip()).strip()
        hasil = json.loads(teks)
        nominal = hasil.get("nominal", 0)

        if nominal == -1:
            await update.message.reply_text(
                "⚠️ Sepertinya ada beberapa struk dalam satu gambar.\n"
                "Kirim satu foto untuk satu struk ya, supaya nominalnya akurat."
            )
            return

        if not nominal or nominal == 0:
            await update.message.reply_text(
                "⚠️ Struk tidak terbaca jelas.\n"
                "Coba foto ulang lebih dekat, atau catat manual:\n"
                "`/catat 50000 Makan catatan`",
                parse_mode="Markdown",
            )
            return

        data = {
            "user_id": user_id,
            "jenis": "pengeluaran",
            "tanggal": hasil.get("tanggal") or hari_ini,
            "kategori": hasil.get("kategori", "Lainnya"),
            "nominal": nominal,
            "merchant": hasil.get("merchant", "-"),
            "sumber": "Struk",
            "catatan": "",
        }
        token = buat_token(data)

        await update.message.reply_text(
            f"📋 *Hasil baca struk:*\n\n"
            f"🏪 Merchant: {data['merchant']}\n"
            f"📅 Tanggal: {data['tanggal']}\n"
            f"🏷️ Kategori: {data['kategori']}\n"
            f"💰 Nominal: Rp{nominal:,}\n\n"
            f"Simpan data ini?",
            parse_mode="Markdown",
            reply_markup=keyboard_konfirmasi_struk(token),
        )

    except Exception as e:
        logger.error(f"Gagal proses struk: {e}")
        await update.message.reply_text(
            "❌ Gagal membaca struk. Coba lagi atau catat manual dengan /catat"
        )


# ==========================================
# HANDLER: tombol
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    raw = query.data or ""
    aksi, _, token = raw.partition("|")
    data = pending.get(token)

    if not data:
        await query.edit_message_text(
            "⚠️ Data ini sudah kedaluwarsa (bot mungkin baru restart). "
            "Coba input ulang ya."
        )
        return

    # Pastikan yang menekan tombol adalah pemilik data
    if data.get("user_id") != query.from_user.id:
        return

    user_id = data["user_id"]

    # --- Batal ---
    if aksi == "struk_batal":
        pending.pop(token, None)
        await query.edit_message_text("❌ Dibatalkan, data tidak disimpan.")
        return

    # --- Konfirmasi struk, lanjut pilih tipe bayar ---
    if aksi == "struk_simpan":
        await query.edit_message_text(
            f"📋 *Detail Pengeluaran:*\n\n"
            f"🏪 Merchant: {data['merchant']}\n"
            f"📅 Tanggal: {data['tanggal']}\n"
            f"🏷️ Kategori: {data['kategori']}\n"
            f"💰 Nominal: Rp{data['nominal']:,}\n\n"
            f"Pilih tipe pembayaran:",
            parse_mode="Markdown",
            reply_markup=keyboard_tipe_bayar(token),
        )
        return

    # --- Tipe pembayaran ---
    if aksi in ("bayar_cash", "bayar_paylater"):
        tipe = "Cash" if aksi == "bayar_cash" else "Pay Later"
        ikon = "💵" if aksi == "bayar_cash" else "💳"
        try:
            simpan_pengeluaran(
                user_id=user_id,
                tanggal=data["tanggal"],
                kategori=data["kategori"],
                nominal=data["nominal"],
                merchant=data.get("merchant", "-"),
                sumber=data.get("sumber", "Manual"),
                catatan=data.get("catatan", ""),
                tipe_bayar=tipe,
            )
            pending.pop(token, None)
            await query.edit_message_text(
                f"✅ *Pengeluaran tersimpan!*\n\n"
                f"📅 {data['tanggal']}\n"
                f"🏷️ {data['kategori']}\n"
                f"💰 Rp{data['nominal']:,}\n"
                f"{ikon} Tipe: *{tipe}*",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Gagal simpan pengeluaran {user_id}: {e}")
            await query.edit_message_text(
                "❌ Gagal menyimpan ke spreadsheet. "
                "Cek apakah akses Editor masih aktif, lalu coba lagi."
            )
        return

    # --- Kategori pemasukan ---
    if aksi.startswith("masuk_"):
        kode = aksi.replace("masuk_", "")
        kategori = KATEGORI_MASUK.get(kode, "📦 Lainnya")
        try:
            simpan_pemasukan(
                user_id=user_id,
                tanggal=data["tanggal"],
                kategori=kategori,
                nominal=data["nominal"],
                sumber="Manual",
                catatan=data.get("catatan", ""),
            )
            pending.pop(token, None)
            await query.edit_message_text(
                f"✅ *Pemasukan tersimpan!*\n\n"
                f"📅 {data['tanggal']}\n"
                f"{kategori}\n"
                f"💰 Rp{data['nominal']:,}\n"
                f"📝 {data.get('catatan') or '-'}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Gagal simpan pemasukan {user_id}: {e}")
            await query.edit_message_text(
                "❌ Gagal menyimpan ke spreadsheet. "
                "Cek akses Editor, lalu coba lagi."
            )
        return


# ==========================================
# ERROR HANDLER
# ==========================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"!!! ERROR: {context.error}", exc_info=context.error)


# ==========================================
# MAIN
# ==========================================
def cek_konfigurasi():
    """Pastikan semua environment variable wajib sudah diisi."""
    wajib = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "MASTER_SPREADSHEET_ID": MASTER_SPREADSHEET_ID,
        "GOOGLE_CREDENTIALS_JSON": GOOGLE_CREDENTIALS_JSON,
    }
    kurang = [k for k, v in wajib.items() if not v]
    if kurang:
        print("\n[!] Environment variable belum diisi: " + ", ".join(kurang))
        print("    Isi dulu di Railway/VPS, lalu jalankan lagi.\n")
        raise SystemExit(1)


def main():
    cek_konfigurasi()
    load_user_map(force=True)
    logger.info(f"Jumlah user terdaftar: {len(_user_map or {})}")
    logger.info(f"Service account: {SERVICE_ACCOUNT_EMAIL}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daftar", daftar))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("catat", catat_manual))
    app.add_handler(CommandHandler("masuk", catat_masuk))
    app.add_handler(CommandHandler("dummy", dummy))
    app.add_handler(CommandHandler("hapusdummy", hapusdummy))
    app.add_handler(MessageHandler(filters.PHOTO, terima_foto))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_error_handler(error_handler)

    print("🤖 Bot multi-user sedang berjalan... Tekan CTRL+C untuk berhenti.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
