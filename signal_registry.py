import streamlit as st
import pandas as pd
import datetime
import re
import urllib.parse
from utils import (supabase, COMPANY_MAP, COMPANY_LIST, parse_smart_time,
                   ROLES_LIST, TERMINAL_STATUSES, get_related_signals, check_permission)
from signal_ticket import show_ticket_details

def show_company_tickets(company_code, df_complaints, active_tasks_dict):
    col_title, col_btn = st.columns([4, 1])
    with col_title: st.subheader(f"📋 Всички сигнали за {company_code}")
    with col_btn:
        if st.button("✖ Затвори списъка", use_container_width=True):
            st.session_state.active_company = None
            st.rerun()
            
    if df_complaints.empty:
        st.write("Няма данни.")
        return
        
    comp_df = df_complaints[df_complaints['Фирма'] == company_code].sort_values(by="event_datetime", ascending=False)
    if comp_df.empty:
        st.info("Няма регистрирани сигнали за тази фирма.")
        return

    for _, row in comp_df.iterrows():
        cid = row['id']
        status = row.get('current_status', 'Неопределен')
        client = row.get('client_name', 'Неизвестен')
        has_client_action = row.get('client_action_needed', False)
        
        task_info = active_tasks_dict.get(cid, {})
        is_overdue = task_info.get('is_overdue', False)
                
        has_dup = not get_related_signals(row, df_complaints).empty
        dup_badge = " <span style='color:#ff4b4b;' title='Има свързани сигнали (30 дни)'>🚨</span>" if has_dup else ""
            
        colA, colB, colC = st.columns([3, 2, 1])
        with colA:
            strike = "s" if status == "Сгрешен/Анулиран" else "strong"
            client_display = f"👤 <{strike}>{client}</{strike}>{dup_badge}" + (" <span style='color:#00aaff;'>🔵 [В диспут]</span>" if has_client_action and status not in TERMINAL_STATUSES else "")
            st.markdown(client_display, unsafe_allow_html=True)
            dt_str = pd.to_datetime(row.get('event_datetime')).strftime('%d.%m.%Y %H:%M') if pd.notna(row.get('event_datetime')) else ""
            st.caption(f"Дата: {dt_str}")
        with colB:
            color = "gray" if status == "Сгрешен/Анулиран" else "red" if is_overdue else "green" if status == "Приключено" else "orange"
            st.markdown(f"Статус: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            if is_overdue: st.markdown("<span style='color:red; font-size:0.8em;'>⚠️ Просрочена задача!</span>", unsafe_allow_html=True)
        with colC:
            if st.button("Отвори", key=f"btn_open_{cid}"): show_ticket_details(row.to_dict(), df_complaints)
        st.divider()

def check_and_show_alerts():
    """Новият интелигентен Welcome Дашборд за задачи"""
    if not check_permission("ro_registry", "edit_kanban") or st.session_state.get('alerts_dismissed', False):
        return
        
    try:
        # Изтегляме всички отворени задачи и ги свързваме с картоните
        res_tasks = supabase.table("ticket_tasks").select("*, complaints(client_name, current_status, company_id)").eq("status", "Отворена").execute()
        if not res_tasks.data:
            st.session_state.alerts_dismissed = True
            return
            
        today = datetime.date.today()
        my_user = st.session_state.username
        is_admin = st.session_state.user_role in ["Администратор", "Супер-админ"]
        
        my_overdue = []
        my_upcoming = []
        other_overdue = []
        
        # Сортиране на задачите
        for t in res_tasks.data:
            comp = t.get('complaints')
            if not comp or comp.get('current_status') in TERMINAL_STATUSES: continue
            
            c_id = comp.get('company_id')
            t['Фирма'] = next((code for code, i in COMPANY_MAP.items() if i == c_id), '-')
            t['client_name'] = comp.get('client_name', 'Неизвестен')
            
            dl_obj = pd.to_datetime(t.get('deadline_date'), errors='coerce')
            is_ovd = pd.notna(dl_obj) and dl_obj.date() < today
            
            is_mine = (t.get('assigned_to_1') == my_user) or (t.get('assigned_to_2') == my_user)
            
            if is_mine:
                if is_ovd: my_overdue.append(t)
                else: my_upcoming.append(t)
            elif is_ovd and is_admin:
                other_overdue.append(t)

        if not my_overdue and not my_upcoming and not other_overdue:
            st.session_state.alerts_dismissed = True
            return

        # ВИЗУАЛИЗАЦИЯ НА WELCOME ЕКРАНА
        st.markdown("<h2 style='text-align: center; color: #00aaff;'>👋 Добре дошли в работното си пространство!</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #ccc;'>Преглед на активните паралелни задачи преди да влезете в регистъра.</p>", unsafe_allow_html=True)
        st.markdown("---")

        def render_task_list(tasks, title, color, icon):
            if not tasks: return
            st.markdown(f"<h4 style='color: {color};'>{icon} {title} ({len(tasks)})</h4>", unsafe_allow_html=True)
            for t in tasks:
                col1, col2, col3 = st.columns([4, 2, 1])
                col1.markdown(f"**Клиент:** {t['client_name']} | **Фирма:** {t['Фирма']}")
                col1.caption(f"Задача: {t['recommendation_type']}")
                col2.markdown(f"<span style='color: {color};'>Срок: {t.get('deadline_date', 'Няма')}</span>", unsafe_allow_html=True)
                with col3:
                    if st.button("Отвори Картона", key=f"alert_btn_{t['id']}", use_container_width=True):
                        st.session_state.auto_open_ticket_id = t['complaint_id']
                        st.session_state.alerts_dismissed = True
                        st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

        render_task_list(my_overdue, "МОИ ПРОСРОЧЕНИ ЗАДАЧИ", "#ff4b4b", "🚨")
        render_task_list(my_upcoming, "МОИ АКТИВНИ ЗАДАЧИ (В СРОК)", "#FFD700", "📌")
        if is_admin:
            render_task_list(other_overdue, "ПРОСРОЧЕНИ ЗАДАЧИ НА ДРУГИ СЛУЖИТЕЛИ (АДМИН ИЗГЛЕД)", "#ff9900", "👁️")
            
        st.markdown("---")
        if st.button("✅ РАЗБРАХ, ПРОДЪЛЖИ КЪМ РЕГИСТЪРА", type="primary", use_container_width=True):
            st.session_state.alerts_dismissed = True
            st.rerun()
        st.stop()
        
    except Exception as e:
        st.error(f"Грешка при зареждане на задачите: {e}")
        st.session_state.alerts_dismissed = True

def render_signal_registry():
    st.title("📝 Сигнали и оплаквания")
    if 'active_company' not in st.session_state: st.session_state.active_company = None
    if 'ro_sort_col' not in st.session_state:
        st.session_state.ro_sort_col = 'event_datetime'
        st.session_state.ro_sort_asc = False

    def handle_sort(column_name):
        if st.session_state.ro_sort_col == column_name: st.session_state.ro_sort_asc = not st.session_state.ro_sort_asc
        else:
            st.session_state.ro_sort_col = column_name
            st.session_state.ro_sort_asc = True
        
    try:
        # 1. Изтегляме всички картони
        res = supabase.table("complaints").select("*, companies(code)").limit(100000).execute()
        df_complaints = pd.DataFrame(res.data)
        if not df_complaints.empty:
            df_complaints['Фирма'] = df_complaints['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
            
        # 2. Изтегляме активните паралелни задачи за мапинг
        tasks_res = supabase.table("ticket_tasks").select("*").eq("status", "Отворена").execute()
        df_tasks = pd.DataFrame(tasks_res.data) if tasks_res.data else pd.DataFrame()
        
        active_tasks_dict = {}
        if not df_tasks.empty and not df_complaints.empty:
            for cid, group in df_tasks.groupby('complaint_id'):
                a1 = group['assigned_to_1'].dropna().tolist()
                a2 = group['assigned_to_2'].dropna().tolist()
                all_a = list(set(a1 + a2))
                all_a = [a for a in all_a if a.strip()]
                
                acts = group['recommendation_type'].dropna().unique().tolist()
                dls = pd.to_datetime(group['deadline_date'], errors='coerce').dropna()
                
                active_tasks_dict[cid] = {
                    'assignees': ", ".join(all_a) if all_a else "Не е посочен",
                    'recommendations': " + ".join(acts) if acts else "Няма активни",
                    'earliest_deadline': dls.min().strftime('%Y-%m-%d') if not dls.empty else None,
                    'is_overdue': (dls.dt.date < datetime.date.today()).any() if not dls.empty else False
                }

    except Exception as e:
        st.error(f"Грешка при връзка с DB: {e}")
        df_complaints = pd.DataFrame()
        active_tasks_dict = {}

    tab_list, tab_kanban, tab_new = st.tabs(["👁️ Птичи поглед (Дашборд)", "📋 - Канбан дъска", "➕ Въвеждане на нов сигнал"])
    
    with tab_list:
        st.markdown("### 🔍 Търсачка и Списък")
        search_query = st.text_input("Търсене по: Име, Телефон, ЕИК, Имейл, Договор, Машина, Аудио запис или Консултант", placeholder="Въведете текст и натиснете Enter...", key="global_search").strip()
        
        if not df_complaints.empty:
            df_to_display = df_complaints.copy()
            df_to_display['assignee'] = df_to_display['id'].map(lambda x: active_tasks_dict.get(x, {}).get('assignees', 'Не е посочен'))
            
            if search_query:
                q = search_query.lower()
                search_cols = ['client_name', 'client_phone', 'client_email', 'client_eik', 'contract_number', 'machines', 'call_number', 'consultant']
                mask = False
                for col in search_cols:
                    if col in df_to_display.columns: mask = mask | df_to_display[col].fillna('').astype(str).str.lower().str.contains(q)
                display_df = df_to_display[mask]
                st.markdown(f"**Намерени резултати:** {len(display_df)}")
            else:
                st.markdown("#### 🕒 Последни 50 въведени сигнала")
                display_df = df_to_display.sort_values(by="id", ascending=False).head(50)
            
            if st.session_state.ro_sort_col in display_df.columns:
                display_df = display_df.sort_values(by=st.session_state.ro_sort_col, ascending=st.session_state.ro_sort_asc)

            with st.container(height=500, border=True):
                h_col1, h_col2, h_col3, h_col4, h_col5, h_col6 = st.columns([1.5, 2, 1, 1.5, 1.5, 1])
                
                with h_col1:
                    arrow = " ↑" if st.session_state.ro_sort_col == 'event_datetime' and st.session_state.ro_sort_asc else " ↓" if st.session_state.ro_sort_col == 'event_datetime' else ""
                    st.markdown(f'<div class="sort-btn-container">', unsafe_allow_html=True)
                    st.button(f"Дата и Час{arrow}", key="btn_sort_date", on_click=handle_sort, args=('event_datetime',), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with h_col2:
                    arrow = " ↑" if st.session_state.ro_sort_col == 'client_name' and st.session_state.ro_sort_asc else " ↓" if st.session_state.ro_sort_col == 'client_name' else ""
                    st.markdown(f'<div class="sort-btn-container">', unsafe_allow_html=True)
                    st.button(f"Клиент{arrow}", key="btn_sort_client", on_click=handle_sort, args=('client_name',), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with h_col3:
                    arrow = " ↑" if st.session_state.ro_sort_col == 'Фирма' and st.session_state.ro_sort_asc else " ↓" if st.session_state.ro_sort_col == 'Фирма' else ""
                    st.markdown(f'<div class="sort-btn-container">', unsafe_allow_html=True)
                    st.button(f"Фирма{arrow}", key="btn_sort_comp", on_click=handle_sort, args=('Фирма',), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with h_col4:
                    arrow = " ↑" if st.session_state.ro_sort_col == 'current_status' and st.session_state.ro_sort_asc else " ↓" if st.session_state.ro_sort_col == 'current_status' else ""
                    st.markdown(f'<div class="sort-btn-container">', unsafe_allow_html=True)
                    st.button(f"Статус{arrow}", key="btn_sort_status", on_click=handle_sort, args=('current_status',), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with h_col5:
                    arrow = " ↑" if st.session_state.ro_sort_col == 'assignee' and st.session_state.ro_sort_asc else " ↓" if st.session_state.ro_sort_col == 'assignee' else ""
                    st.markdown(f'<div class="sort-btn-container">', unsafe_allow_html=True)
                    st.button(f"Отговорници{arrow}", key="btn_sort_assignee", on_click=handle_sort, args=('assignee',), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                with h_col6: st.markdown("**Действие**")
                st.divider()
                
                if display_df.empty: st.write("Няма намерени записи.")
                else:
                    for _, row in display_df.iterrows():
                        r_col1, r_col2, r_col3, r_col4, r_col5, r_col6 = st.columns([1.5, 2, 1, 1.5, 1.5, 1])
                        status = row.get('current_status', 'Неопределен')
                        dt_str = pd.to_datetime(row.get('event_datetime')).strftime('%d.%m.%Y %H:%M') if pd.notna(row.get('event_datetime')) else ""
                        r_col1.write(dt_str)
                        has_dup = not get_related_signals(row, df_complaints).empty
                        dup_badge = " <span style='color:#ff4b4b;' title='Има свързани сигнали (30 дни)'>🚨</span>" if has_dup else ""
                        client = row.get('client_name', 'Неизвестен')
                        strike = "s" if status == "Сгрешен/Анулиран" else "span"
                        
                        r_col2.markdown(f"<{strike}>{client}</{strike}>{dup_badge}", unsafe_allow_html=True)
                        r_col3.write(row.get('Фирма', ''))
                        color = "gray" if status == "Сгрешен/Анулиран" else "green" if status == "Приключено" else "orange"
                        r_col4.markdown(f"<span style='color:{color}'><{strike}>{status}</{strike}></span>", unsafe_allow_html=True)
                        assignee_val = row.get('assignee', 'Не е посочен')
                        r_col5.markdown(f"<{strike}>{assignee_val}</{strike}>", unsafe_allow_html=True)
                        with r_col6:
                            if st.button("Отвори", key=f"btn_rec_{row['id']}"): show_ticket_details(row.to_dict(), df_complaints)
                        st.markdown("<hr style='margin: 0.2em 0; opacity: 0.2'>", unsafe_allow_html=True)
        else: st.info("Все още няма регистрирани сигнали в базата данни.")

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### Птичи поглед по фирми")
        st.caption("Кликнете върху бутона под дадена фирма, за да видите детайли и просрочия.")

        NUM_COLS_PER_ROW = 4
        cols = st.columns(NUM_COLS_PER_ROW)
        
        for i, comp in enumerate(COMPANY_LIST):
            with cols[i % NUM_COLS_PER_ROW]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: #FFD700; margin-top: 0;'>{comp}</h3>", unsafe_allow_html=True)
                    if not df_complaints.empty and 'Фирма' in df_complaints.columns:
                        comp_data = df_complaints[df_complaints['Фирма'] == comp]
                        unresolved = len(comp_data[~comp_data['current_status'].isin(TERMINAL_STATUSES)])
                        in_dispute = len(comp_data[(~comp_data['current_status'].isin(TERMINAL_STATUSES)) & (comp_data['client_action_needed'] == True)])
                        
                        # Преброяваме просрочените на база на паралелните задачи
                        overdue = 0
                        for _, r in comp_data.iterrows():
                            if r.get('current_status') not in TERMINAL_STATUSES and active_tasks_dict.get(r['id'], {}).get('is_overdue'):
                                overdue += 1
                    else: unresolved, overdue, in_dispute = 0, 0, 0
                    
                    st.write(f"**Неприключени:** {unresolved} бр.")
                    st.write(f"**Просрочени:** {'🔴 ' + str(overdue) if overdue > 0 else '0'} бр.")
                    st.write(f"**В диспут:** {'🔵 ' + str(in_dispute) if in_dispute > 0 else '0'} бр.")
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(f"🔍 Отвори списък", key=f"open_dash_{comp}", use_container_width=True):
                        st.session_state.active_company = comp
                        st.rerun()

        if st.session_state.active_company:
            st.markdown("---")
            show_company_tickets(st.session_state.active_company, df_complaints, active_tasks_dict)

    with tab_kanban:
        st.markdown("### Оперативно управление на сигналите")
        
        desired_order = ['REN', 'MAS', 'CIM', 'CMX', 'AST', 'BAU', 'RSX']
        ordered_companies = [c for c in desired_order if c in COMPANY_LIST]
        ordered_companies += [c for c in COMPANY_LIST if c not in desired_order]

        kb_comp_filter = st.radio("Покажи сигнали за фирма:", ["Всички"] + ordered_companies, horizontal=True, key="kb_filter")
        
        if not df_complaints.empty:
            df_kb_all = df_complaints[~df_complaints['current_status'].isin(TERMINAL_STATUSES)].copy()
            total_active = len(df_kb_all)
            comp_counts = df_kb_all['Фирма'].value_counts().to_dict()
            
            badges_html = f"<div style='display: flex; flex-wrap: wrap; gap: 10px; margin-top: -5px; margin-bottom: 20px;'><div style='background-color: #2a2a2a; border-left: 3px solid #FFD700; padding: 5px 12px; border-radius: 4px; font-size: 0.9em; color: #eee;'><strong>Всички:</strong> <span style='color: #FFD700; font-weight: bold;'>{total_active}</span></div>"
            for c in ordered_companies:
                cnt = comp_counts.get(c, 0)
                color = "#00aaff" if cnt > 0 else "#666666"
                badges_html += f"<div style='background-color: #1e1e1e; border: 1px solid #444; padding: 5px 10px; border-radius: 4px; font-size: 0.85em; color: #ccc;'>{c}: <span style='color: {color}; font-weight: bold;'>{cnt}</span></div>"
            badges_html += "</div>"
            
            st.markdown(badges_html, unsafe_allow_html=True)
            st.markdown("---")
            
            df_kb = df_kb_all.copy()
            if kb_comp_filter != "Всички": 
                df_kb = df_kb[df_kb['Фирма'] == kb_comp_filter]

            k_col1, k_col2, k_col3 = st.columns(3)
            
            def render_kanban_card(tkt, column_obj):
                cid = tkt['id']
                client = tkt.get('client_name', 'Неизвестен')
                comp_name = tkt.get('Фирма', '')
                dt_str = pd.to_datetime(tkt.get('event_datetime')).strftime('%d.%m.%Y')
                in_dispute = tkt.get('client_action_needed', False)
                
                meta_info = active_tasks_dict.get(cid, {'assignees': 'Не е посочен', 'recommendations': 'Няма задачи', 'earliest_deadline': 'Няма', 'is_overdue': False})
                is_overdue = meta_info['is_overdue']
                
                card_class = "kanban-card overdue" if is_overdue else "kanban-card dispute" if in_dispute else "kanban-card"
                badge_dispute = " 🔵 [Диспут]" if in_dispute else ""
                badge_overdue = " 🔴 [Просрочена задача]" if is_overdue else ""
                
                html_card = f"""
                <div class="{card_class}">
                    <div class="kanban-title">{client}{badge_dispute}{badge_overdue}</div>
                    <div class="kanban-meta">{comp_name} | Дата: {dt_str}</div>
                    <div class="kanban-detail"><strong>Отговорници:</strong> {meta_info['assignees']}</div>
                    <div class="kanban-detail"><strong>Задачи:</strong> {meta_info['recommendations']}</div>
                    <div class="kanban-detail"><strong>Най-ранен срок:</strong> {meta_info['earliest_deadline'] or 'Няма'}</div>
                </div>
                """
                with column_obj:
                    st.markdown(html_card, unsafe_allow_html=True)
                    if st.button("Отвори", key=f"kb_btn_{cid}", use_container_width=True): show_ticket_details(tkt, df_complaints)

            df_col1 = df_kb[df_kb['current_status'] == "Чака заключение и препоръка"]
            df_col2 = df_kb[df_kb['current_status'] == "Чака проверка"]
            df_col3 = df_kb[df_kb['current_status'] == "Чака приключване"]

            with k_col1:
                st.markdown(f"<h4 style='text-align: center; color: #aaaaaa;'>Чака заключ. / препоръка ({len(df_col1)})</h4>", unsafe_allow_html=True)
                for _, r in df_col1.iterrows(): render_kanban_card(r.to_dict(), k_col1)
            with k_col2:
                st.markdown(f"<h4 style='text-align: center; color: #ff9900;'>Чака проверка ({len(df_col2)})</h4>", unsafe_allow_html=True)
                for _, r in df_col2.iterrows(): render_kanban_card(r.to_dict(), k_col2)
            with k_col3:
                st.markdown(f"<h4 style='text-align: center; color: #00aaff;'>Чака приключване ({len(df_col3)})</h4>", unsafe_allow_html=True)
                for _, r in df_col3.iterrows(): render_kanban_card(r.to_dict(), k_col3)
        else: 
            st.markdown("---")
            st.info("Няма данни за визуализация на Канбан дъската.")

    with tab_new:
        if check_permission("ro_registry", "create_ticket"):
            st.write("Форма за въвеждане на първичен картон от служител/кол център.")
            st.markdown("---")
            if "form_key" not in st.session_state: st.session_state.form_key = 0
            with st.form(f"new_complaint_form_{st.session_state.form_key}"):
                st.subheader("Основни данни")
                col1, col2, col3, col4 = st.columns(4)
                with col1: channel = st.selectbox("Канал на постъпване *", ["Телефон", "Email", "Чат", "Контролинг - камери", "Контролинг - присъствено", "Друго"])
                with col2: company_selected = st.selectbox("Фирма *", COMPANY_LIST)
                with col3: event_date = st.date_input("Дата на сигнала *")
                with col4: event_time_str = st.text_input("Час (напр. 1430) *", placeholder="Въведете цифри...")

                st.subheader("Данни за клиента")
                col5, col6, col7, col8 = st.columns([2, 1, 1, 1])
                with col5:
                    client_name = st.text_input("Име/Наименование *")
                    client_type = st.selectbox("Вид клиент", ["Юридическо лице", "Физическо лице", "Неизвестно"])
                with col6:
                    client_phone = st.text_input("Телефон")
                    client_eik = st.text_input("ЕИК (за ЮЛ)")
                with col7:
                    client_email = st.text_input("Email")
                    contract_number = st.text_input("Договор/Поръчка №", max_chars=20)
                with col8: client_action_needed = st.checkbox("Очаква ли се действие с клиента?", value=False)
                    
                st.subheader("Същност на проблема")
                col9, col10 = st.columns(2)
                with col9:
                    case_type = st.selectbox("Касае *", ["Наем", "Продажба", "Ремонт", "Друго"])
                    call_number = st.text_input("Номер на разговора (аудио запис)")
                with col10: 
                    machines = st.text_input("Машина/и", max_chars=100)
                    consultant_name = st.text_input("Консултант (Имена)", max_chars=100)
                    
                description = st.text_area("Изложение на проблема *", height=120)
                st.write("*Полетата със звезда са задължителни.*")
                submit_button = st.form_submit_button("Запиши първичен картон", type="primary")

                if submit_button:
                    formatted_time = parse_smart_time(event_time_str)
                    if not company_selected or not client_name or not description or not event_time_str: st.error("⚠️ Моля, попълнете задължителните полета!")
                    elif not formatted_time: st.error("⚠️ Невалиден час!")
                    else:
                        try:
                            company_id = COMPANY_MAP.get(company_selected)
                            datetime_str = f"{event_date.strftime('%Y-%m-%d')} {formatted_time}"
                            new_record = {
                                "channel": channel, "event_datetime": datetime_str, "company_id": company_id,
                                "client_name": client_name, "client_phone": client_phone, "client_email": client_email,
                                "client_type": client_type, "client_eik": client_eik, "contract_number": contract_number,
                                "case_type": case_type, "call_number": call_number, "machines": machines, "consultant": consultant_name,
                                "client_action_needed": client_action_needed, "description": description,
                                "current_status": "Чака заключение и препоръка"
                            }
                            inserted = supabase.table("complaints").insert(new_record).execute()
                            st.session_state.form_key += 1
                            if inserted.data: st.session_state.auto_open_ticket_id = inserted.data[0]['id']
                            st.rerun()
                        except Exception as e: st.error(f"Грешка при запис: {e}")
        else:
            st.warning("⚠️ Нямате права за създаване на нови сигнали.")

    if 'auto_open_ticket_id' in st.session_state:
        t_id = st.session_state['auto_open_ticket_id']
        del st.session_state['auto_open_ticket_id']
        try:
            t_res = supabase.table("complaints").select("*").eq("id", t_id).execute()
            if t_res.data: show_ticket_details(t_res.data[0], df_complaints)
        except Exception as e:
            st.error(f"Системна грешка при отваряне на картона: {e}")
