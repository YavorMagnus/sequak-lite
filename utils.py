import streamlit as st
from supabase import create_client, Client
import pandas as pd
import re

# --- СВЪРЗВАНЕ С БАЗАТА ДАННИ ---
SUPABASE_URL = "https://cymfodenkklcjhjgfeau.supabase.co"
SUPABASE_KEY = st.secrets["SUPABASE_SECRET_KEY"]

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# --- ГЛОБАЛНИ ДАННИ ---
@st.cache_data(ttl=600)
def get_companies():
    try:
        res = supabase.table("companies").select("id, code").execute()
        return {row['code'].upper(): row['id'] for row in res.data}
    except Exception:
        return {}

COMPANY_MAP = get_companies()
COMPANY_LIST = list(COMPANY_MAP.keys()) if COMPANY_MAP else ["Няма заредени фирми"]

# Бизнес роли за процесите
ROLES_LIST = ["Служител", "Пряк ръководител", "Отговорник качество", "Управител", "Контролинг", "RXG-адм", "CEO", "Друг"]

# Системни роли за достъп (Новата структура)
SYSTEM_ROLES = ["Супер-админ", "Администратор", "Power user", "Супер-четец", "Четец", "AI-User"]

CONCLUSIONS = ["Техническа грешка", "Липса на знания/умения", "Нарушение", "Не сме сигурни", "Липса на ресурс", "Дезорганизация", "Идея за подобрение"]
RECOMMENDATIONS = ["Техническа корекция", "Обучение", "Наказание", "Проверка (поле)", "Планиране на ресурс", "Реорганизация", "Обсъждане с колега"]
TERMINAL_STATUSES = ["Приключено", "Сгрешен/Анулиран"]

# --- МАТРИЦА НА ПРАВАТА (PERMISSIONS) ---
AVAILABLE_PERMISSIONS = {
    "mp_dashboard": {
        "name": "Модул: Пропуснати ползи",
        "actions": {
            "read": "Визуализация на таблото (Четене)",
            "export": "Експорт на данни (Excel)",
            "upload_data": "Зареждане на нови данни (Внос)"
        }
    },
    "ro_registry": {
        "name": "Модул: Регистър Оплаквания",
        "actions": {
            "read": "Визуализация на регистъра (Четене)",
            "create_ticket": "Въвеждане на нов сигнал",
            "edit_kanban": "Редакция на сигнали (работа по канбан)",
            "cancel_ticket": "Анулиране на сигнал (Сгрешен запис)",
            "export": "Експорт на данни (Excel)"
        }
    },
    "recruitment": {
        "name": "Модул: Рекрутмънт",
        "actions": {
            "read": "Визуализация на позиции (Четене)",
            "manage_positions": "Създаване и управление на позиции",
            "upload_candidates": "Зареждане на CV-та",
            "evaluate": "Оценяване и местене по Канбан",
            "schedule": "Насрочване на интервюта",
            "soft_delete": "Изтриване (Преместване в кошче)",
            "hard_delete": "Окончателно изтриване (Hard Delete)"
        }
    }
}

def check_permission(module, action):
    """
    Умна функция за проверка на правата въз основа на хибридния модел.
    """
    role = st.session_state.get('user_role', '')

    # 1. Бог режим: Супер-админ може абсолютно всичко навсякъде
    if role == "Супер-админ":
        return True

    # 2. Администратор: Може всичко, БЕЗ окончателно (хард) изтриване
    if role == "Администратор":
        if action == "hard_delete":
            return False
        return True

    # 3. Супер-четец: Вижда всичко навсякъде, но няма права за писане/екшън
    if role == "Супер-четец":
        return True if action == "read" else False

    # 4. За Power user, Четец, AI-User - проверяваме техния JSON в сесията
    perms = st.session_state.get('user_permissions', {})
    mod_perms = perms.get(module, {})
    return mod_perms.get(action, False)


# --- ГЛОБАЛНИ ФУНКЦИИ ---
def standardize_company_code(excel_name):
    name = str(excel_name).lower()
    if 'ren' in name: return 'REN'
    if 'rcd' in name or ('cim' in name and 'cmx' not in name):
        return 'CIM' if 'CIM' in COMPANY_MAP else 'RCD'
    if 'mas' in name: return 'MAS'
    if 'cmx' in name: return 'CMX'
    return str(excel_name).upper().strip()

def parse_smart_time(t_str):
    if not t_str: return None
    t_str = str(t_str).strip()
    if ':' in t_str:
        parts = t_str.split(':')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hh, mm = int(parts[0]), int(parts[1])
            if 0 <= hh <= 23 and 0 <= mm <= 59: return f"{hh:02d}:{mm:02d}:00"
        elif len(parts) == 3 and all(p.isdigit() for p in parts):
            hh, mm, ss = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59: return f"{hh:02d}:{mm:02d}:{ss:02d}"
    clean_str = re.sub(r"\D", "", t_str)
    if len(clean_str) in [3, 4]:
        clean_str = clean_str.zfill(4)
        hh, mm = int(clean_str[:2]), int(clean_str[2:])
        if 0 <= hh <= 23 and 0 <= mm <= 59: return f"{hh:02d}:{mm:02d}:00"
    elif len(clean_str) in [5, 6]:
        clean_str = clean_str.zfill(6)
        hh, mm, ss = int(clean_str[:2]), int(clean_str[2:4]), int(clean_str[4:])
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59: return f"{hh:02d}:{mm:02d}:{ss:02d}"
    return None

def get_related_signals(ticket, df_complaints):
    if df_complaints is None or df_complaints.empty:
        return pd.DataFrame()
    
    c_phone = str(ticket.get('client_phone', '')).strip()
    c_email = str(ticket.get('client_email', '')).strip()
    c_eik = str(ticket.get('client_eik', '')).strip()

    if not c_phone and not c_email and not c_eik:
        return pd.DataFrame()
    
    t_date = pd.to_datetime(ticket.get('event_datetime'), errors='coerce')
    if pd.isna(t_date): return pd.DataFrame()
    if t_date.tzinfo is not None: t_date = t_date.replace(tzinfo=None)

    mask = (df_complaints['id'] != ticket['id'])
    
    comp_dates = pd.to_datetime(df_complaints['event_datetime'], errors='coerce')
    if comp_dates.dt.tz is not None: comp_dates = comp_dates.dt.tz_localize(None)

    date_diff = (comp_dates - t_date).abs()
    mask &= (date_diff.dt.days <= 30)

    match_cond = pd.Series(False, index=df_complaints.index)
    if c_phone: match_cond |= (df_complaints['client_phone'].astype(str).str.strip() == c_phone)
    if c_email: match_cond |= (df_complaints['client_email'].astype(str).str.strip() == c_email)
    if c_eik: match_cond |= (df_complaints['client_eik'].astype(str).str.strip() == c_eik)

    return df_complaints[mask & match_cond]
