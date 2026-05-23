import streamlit as st
import pandas as pd
from utils import supabase, SYSTEM_ROLES

def render_admin_panel():
    st.title("⚙️ Управление на потребители и права (RBAC)")
    
    # Желязна защита: Само Супер-админ може да вижда този екран
    if st.session_state.get('user_role') != "Супер-админ":
        st.error("Нямате права за достъп до този модул.")
        st.stop()

    tab_view, tab_add, tab_docs = st.tabs([
        "👥 Списък потребители", 
        "➕ Добави нов потребител",
        "切割 📄 Документация на правата"
    ])

    with tab_view:
        st.subheader("Активни акаунти в холдинга")
        try:
            res = supabase.table("users").select("id, username, role, created_at").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d.%m.%Y %H:%M')
                df = df.rename(columns={
                    "username": "Потребител", 
                    "role": "Системна Роля", 
                    "created_at": "Създаден на", 
                    "id": "Системен ID"
                })
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Няма намерени потребители.")
        except Exception as e:
            st.error(f"Грешка при зареждане на потребители: {e}")

    with tab_add:
        st.subheader("Създаване на нов фирмен профил")
        with st.form("add_user_form_v3"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Потребителско име *").strip()
                # Използваме директно подредените роли от новия utils.py
                new_role = st.selectbox("Избор на твърда йерархична роля *", SYSTEM_ROLES, index=0)
            with col2:
                new_password = st.text_input("Парола (прав текст) *", type="password").strip()
            
            st.info("💡 Забележка: Системата използва автоматично наследяване. Правата на потребителя се определят изцяло от неговата роля.")
            submitted = st.form_submit_button("💾 Запиши новия потребител", type="primary")

            if submitted:
                if not new_username or not new_password:
                    st.error("⚠️ Моля, попълнете абсолютно всички задължителни полета!")
                else:
                    try:
                        # Проверка за съществуващо име в базата
                        check = supabase.table("users").select("id").eq("username", new_username).execute()
                        if check.data:
                            st.error(f"⚠️ Потребител с име '{new_username}' вече съществува в базата данни!")
                        else:
                            # Записваме ролята чиста, цялата тежка логика на достъп вече е в utils.py
                            supabase.table("users").insert({
                                "username": new_username,
                                "password": new_password,
                                "role": new_role,
                                "permissions": {} # Празен обект за съвместимост със старата структура
                            }).execute()
                            st.success(f"🎉 Потребителят '{new_username}' е създаден успешно с права за ниво: {new_role}!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Възникна непредвидена грешка при запис в базата: {e}")

    with tab_docs:
        st.subheader("📋 Официална йерархична матрица на правата в SequaK")
        st.markdown("""
        За да осигурите максимална стабилност, системата използва модел на наследяване отдолу нагоре. 
        Всеки по-горен слой автоматично получава всички права на нивата под него.
        
        | Системна Роля | 📊 Модул ПП (Пропуснати ползи) | 📝 Модул Сигнали (Оплаквания) | ⚙️ Админ Панел |
        | :--- | :--- | :--- | :--- |
        | **Четец** | Преглед на таблото, филтриране по дати. | Преглед на списъка и Канбан дъската. | Пълен отказ за достъп. |
        | **Power User** | Разглежда + **Експорт на данни в Excel**. | Разглежда + **Коментари/Указания** + **Назначаване на стъпки**. | Пълен отказ за достъп. |
        | **Администратор** | Наследява + **Внос на данни от външен .xlsx**. | Наследява + **Въвеждане на нови** + **Анулиране на сгрешени**. | Пълен отказ за достъп. |
        | **Супер-админ** | Пълен неограничен контрол. | Наследява + **Трайно изтриване (Hard Delete)**. | **Пълен достъп и управление**. |
        """)
