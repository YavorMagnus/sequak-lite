import streamlit as st
from utils import supabase
# Новите "тръби" към разцепените модули
from signal_registry import render_signal_registry, check_and_show_alerts
from signal_analytics import render_signal_analytics
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

# --- ФУНКЦИЯ ЗА ЛОГИН (КОРИГИРАНА ЗА ПРАВ ТЕКСТ) ---
def verify_login(username, password):
    try:
        response = supabase.table("users").select("*").eq("username", username).execute()
        if response.data:
            user_data = response.data[0]
            # Взимаме паролата от колоната 'password' в прав текст
            stored_password = user_data.get('password') 
            if stored_password and str(stored_password).strip() == str(password).strip():
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

# Зареждане на съответния модул през новите функции
if page == "Регистър Оплаквания (РО)":
    render_signal_registry()
elif page == "Анализи (РО)":
    render_signal_analytics()
elif page == "Пропуснати ползи (ПП)":
    render_mp_dashboard()
