import streamlit as st
import bcrypt
from utils import supabase
from ro import render_ro_registry, render_ro_analytics, check_and_show_alerts
from mp import render_mp_dashboard

# --- КОНФИГУРАЦИЯ НА СТРАНИЦАТА ---
st.set_page_config(
    page_title="SequaK Lite",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ИНИЦИАЛИЗАЦИЯ НА СЕСИЯТА ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ''
if 'user_role' not in st.session_state:
    st.session_state.user_role = ''
if 'user_permissions' not in st.session_state:
    st.session_state.user_permissions = {}
if 'alerts_dismissed' not in st.session_state:
    st.session_state.alerts_dismissed = False

# --- ФУНКЦИЯ ЗА ЛОГИН ---
def verify_login(username, password):
    try:
        response = supabase.table("users").select("*").eq("username", username).execute()
        if response.data:
            user_data = response.data[0]
            stored_hash = user_data.get('password_hash')
            if stored_hash:
                if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
                    st.session_state.logged_in = True
                    st.session_state.username = user_data['username']
                    st.session_state.user_role = user_data.get('role', 'Четец')
                    st.session_state.user_permissions = user_data.get('permissions', {})
                    return True
        return False
    except Exception as e:
        st.error(f"Грешка при връзка с базата данни: {e}")
        return False

# --- ЕКРАН ЗА ЛОГИН ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #FFD700;'>SequaK Lite</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Вход в системата</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username_input = st.text_input("Потребителско име")
            password_input = st.text_input("Парола", type="password")
            submit_login = st.form_submit_button("Вход", type="primary", use_container_width=True)
            
            if submit_login:
                if verify_login(username_input, password_input):
                    st.success("Успешен вход! Презареждане...")
                    st.rerun()
                else:
                    st.error("Грешно потребителско име или парола!")
    st.stop()

# --- ПРОВЕРКА ЗА ПРОСРОЧЕНИ СИГНАЛИ (АЛАРМИ) ---
# Това ще се покаже веднага след логин, ако има просрочени задачи (идва от ro.py)
if not st.session_state.alerts_dismissed:
    check_and_show_alerts()

# --- ОСНОВНА НАВИГАЦИЯ (СЛЕД УСПЕШЕН ЛОГИН) ---
st.sidebar.markdown(f"👤 **Вписан като:** {st.session_state.username}")
st.sidebar.markdown(f"🛡️ **Роля:** {st.session_state.user_role}")

if st.sidebar.button("Изход", type="secondary", use_container_width=True):
    st.session_state.logged_in = False
    st.session_state.username = ''
    st.session_state.user_role = ''
    st.session_state.user_permissions = {}
    st.session_state.alerts_dismissed = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("📌 Навигация")

page = st.sidebar.radio(
    "Изберете модул:",
    ["Регистър Оплаквания (РО)", "Анализи (РО)", "Пропуснати ползи (ПП)"]
)

# Зареждане на съответния модул
if page == "Регистър Оплаквания (РО)":
    render_ro_registry()
elif page == "Анализи (РО)":
    render_ro_analytics()
elif page == "Пропуснати ползи (ПП)":
    render_mp_dashboard()
