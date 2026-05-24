import streamlit as st
import pandas as pd
from utils import (supabase, COMPANY_MAP, ROLES_LIST, CONCLUSIONS, 
                   RECOMMENDATIONS, TERMINAL_STATUSES, get_related_signals, 
                   check_permission)
from signal_email import render_email_tab

@st.cache_data(ttl=300)
def get_company_rules():
    """Кеширано извличане на правилниците за бързо зареждане на менютата."""
    try:
        res = supabase.table("company_rules").select("id, rulebook_name, rule_text").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["id", "rulebook_name", "rule_text"])
    except Exception:
        return pd.DataFrame(columns=["id", "rulebook_name", "rule_text"])

@st.dialog("Картон на сигнала", width="large")
def show_ticket_details(ticket, df_complaints_param):
    tab_main, tab_email = st.tabs(["📑 Данни и Действия", "📧 Композиране на мейл"])
    
    # Зареждане на данни
    history_res = supabase.table("complaint_history").select("*").eq("complaint_id", ticket['id']).order("created_at", desc=False).execute()
    history_data = history_res.data
    current_status = ticket.get('current_status', 'Чака заключение и препоръка')
    
    has_edit = check_permission("ro_registry", "edit_kanban")
    has_cancel = check_permission("ro_registry", "cancel_ticket")
    
    company_name = ticket.get('Фирма')
    if not company_name or company_name == '-':
        c_id = ticket.get('company_id')
        company_name = next((code for code, i in COMPANY_MAP.items() if i == c_id), '-')
    
    df_rules = get_company_rules()
    rulebooks = df_rules['rulebook_name'].unique().tolist() if not df_rules.empty else []

    with tab_main:
        related_df = get_related_signals(ticket, df_complaints_param)
        if not related_df.empty:
            st.error(f"⚠️ **ВНИМАНИЕ: Открити са {len(related_df)} свързани сигнала за този клиент през последните 30 дни!**")
            for _, dup_row in related_df.iterrows():
                dup_date = pd.to_datetime(dup_row.get('event_datetime')).strftime('%d.%m.%Y')
                dup_comp = dup_row.get('Фирма', '-')
                with st.expander(f"Свързан сигнал от {dup_date} ({dup_comp}) - Статус: {dup_row.get('current_status', 'Неопределен')}"):
                    st.markdown(f"**Описание:** {dup_row.get('description', '-')}")
            st.markdown("---")

        client_name_safe = str(ticket.get('client_name', 'Неизвестен')).strip()
        st.markdown(f"<h3 style='color: #FFD700; margin-bottom: 0px;'>Сигнал от: {client_name_safe}</h3>", unsafe_allow_html=True)
        st.caption(f"Дата: {ticket.get('event_datetime', '')} | Канал: {ticket.get('channel', '')} | Касае: {ticket.get('case_type', '')}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Телефон:** {ticket.get('client_phone', '-')}")
            st.write(f"**Имейл:** {ticket.get('client_email', '-')}")
            st.write(f"**ЕИК:** {ticket.get('client_eik', '-')}")
        with col2:
            st.markdown(f"**Фирма:** {company_name} &nbsp;&nbsp;|&nbsp;&nbsp; **Консултант:** {ticket.get('consultant', '-')}")
            st.write(f"**Договор №:** {ticket.get('contract_number', '-')}")
            st.write(f"**Машина/и:** {ticket.get('machines', '-')}")
            st.write(f"**Аудио запис (номер):** {ticket.get('call_number', '-')}")
        
        st.info(f"**Описание:** {ticket.get('description', '')}")
        st.markdown("---")

        # АКТИВНИ ЗАДАЧИ
        try:
            tasks_res = supabase.table("ticket_tasks").select("*").eq("complaint_id", ticket['id']).eq("status", "Отворена").execute()
            active_tasks = tasks_res.data
        except: active_tasks = []

        if active_tasks:
            st.markdown("#### 🔄 Отворени паралелни задачи")
            for t in active_tasks:
                as_text = f"{t.get('assigned_to_1', '')}"
                if t.get('assigned_to_2'): as_text += f", {t.get('assigned_to_2')}"
                
                # КОРЕКЦИЯ 1: Добавяме task_description (заключение + детайли) към жълтата кутия
                desc = t.get('task_description', '')
                st.warning(f"🔹 **{t['recommendation_type']}** | {desc} | Изпълнители: **{as_text}** | Срок: **{t.get('deadline_date', '-')}**")
            st.markdown("---")

        st.subheader("📋 Хронология на действията")
        if not history_data: st.write("Все още няма предприети действия.")
        else:
            for record in history_data:
                created_at_fmt = pd.to_datetime(record['created_at']).strftime('%d.%m.%Y %H:%M')
                author = record.get('created_by') or 'Системата'
                raw_details = str(record.get('action_details') or "")
                details_formatted = raw_details.replace(' | ', '<br>🔹 ')
                st.markdown(f"""
                <div class="history-card">
                    <strong>{created_at_fmt} - {record['action_type']}</strong> <span style="color: #00aaff; font-size: 0.9em;">(от: {author})</span>
                    <div style="margin-top: 8px; color: #eeeeee; padding-left: 5px;">{details_formatted}</div>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("---")
        
        if current_status == "Сгрешен/Анулиран":
            st.error("🚫 Този сигнал е маркиран като СГРЕШЕН / АНУЛИРАН и е заключен за редакция.")
        elif current_status == "Приключено":
            st.success("✅ Този сигнал е ПРИКЛЮЧЕН.")
        else:
            st.subheader("🤝 Комуникация с клиент (Външен процес)")
            if has_edit:
                current_client_action = ticket.get('client_action_needed', False)
                new_client_action = st.toggle("Извънреден диспут: Очаква се действие с клиента", value=current_client_action, key=f"tgl_{ticket['id']}")
                if new_client_action != current_client_action:
                    supabase.table("complaints").update({"client_action_needed": new_client_action}).eq("id", ticket['id']).execute()
                    st.session_state.auto_open_ticket_id = ticket['id']
                    st.rerun()

                if new_client_action:
                    st.markdown('<div class="client-stream"><h4>Въвеждане на комуникация</h4>', unsafe_allow_html=True)
                    client_step = st.selectbox("Изберете етап", ["1. Изпратен мейл до О.К.", "2. Предложение към клиент (от О.К.)", "3. Удовлетвореност (Финал)"], key=f"cs_{ticket['id']}")
                    c_details = ""
                    c_deadline = None
                    if client_step == "1. Изпратен мейл до О.К.":
                        c_details = f"Изпратен имейл на: {st.date_input('Дата', key=f'md_{ticket['id']}').strftime('%d.%m.%Y')}"
                    elif client_step == "2. Предложение към клиент (от О.К.)":
                        c_details = st.text_area("Направено предложение", key=f"pt_{ticket['id']}")
                        c_deadline = st.date_input("Срок", key=f"pd_{ticket['id']}")
                    elif client_step == "3. Удовлетвореност (Финал)":
                        is_sat = st.radio("Удовлетворен ли е?", ["Да", "Не"], horizontal=True, key=f"sat_{ticket['id']}")
                        c_details = f"Удовлетворен: {is_sat}. Детайли: {st.text_input('Детайли', key=f'fc_{ticket['id']}')}"

                    client_comment = st.text_area("Коментар", max_chars=500, key=f"cc_{ticket['id']}")
                    if st.button("💾 Запиши действие с клиент", key=f"btn_c_{ticket['id']}"):
                        final_c_details = f"{c_details} | Коментар: {client_comment}" if client_comment else c_details
                        supabase.table("complaint_history").insert({
                            "complaint_id": ticket['id'], "action_type": f"Клиент: {client_step.split('. ')[1]}",
                            "action_details": final_c_details, "deadline_date": str(c_deadline) if c_deadline else None,
                            "created_by": st.session_state.username
                        }).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")

            # ВЪТРЕШЕН ПРОЦЕС - ТАСКОВЕ И ПРИКЛЮЧВАНЕ
            st.subheader("⚙️ Продължаване на процеса (Вътрешен)")
            if has_edit:
                try:
                    sys_users = sorted([u['username'] for u in supabase.table("users").select("username").execute().data])
                except: sys_users = []

                mode = st.radio("Изберете режим на работа:", ["📝 Възлагане на паралелни задачи", "🏁 Окончателно приключване на сигнала"], horizontal=True)

                if mode == "📝 Възлагане на паралелни задачи":
                    task_key = f"t_cnt_{ticket['id']}"
                    if task_key not in st.session_state: st.session_state[task_key] = 1

                    def add_task_field():
                        if st.session_state[task_key] < 10: st.session_state[task_key] += 1

                    st.info("Можете да добавите до 10 паралелни задачи.")
                    
                    for i in range(st.session_state[task_key]):
                        st.markdown(f"**Задача {i+1}**")
                        col1, col2 = st.columns(2)
                        conc = col1.selectbox("Заключение", ["Избери..."] + CONCLUSIONS, key=f"tc_{ticket['id']}_{i}")
                        rec = col2.selectbox("Препоръка", ["Избери..."] + RECOMMENDATIONS, key=f"tr_{ticket['id']}_{i}")
                        details = st.text_input("Детайли / Коментар (до 500 симв.)", key=f"td_{ticket['id']}_{i}")
                        
                        if conc == "Нарушение":
                            st.markdown("<div style='background-color:#4a1e1e; padding:10px; border-radius:5px;'>", unsafe_allow_html=True)
                            st.write("⚖️ **Дисциплинарно производство**")
                            crb = st.selectbox("Правилник", ["Избери..."] + rulebooks, key=f"trb_{ticket['id']}_{i}")
                            rule_opts = ["Избери..."]
                            if crb != "Избери...":
                                rule_opts += df_rules[df_rules['rulebook_name'] == crb]['rule_text'].tolist()
                            rule_opts.append("Друго (Свободен текст)")
                            r_sel = st.selectbox("Правило", rule_opts, key=f"trs_{ticket['id']}_{i}")
                            r_cust = st.text_input("Опишете правилото", key=f"trc_{ticket['id']}_{i}") if r_sel == "Друго (Свободен текст)" else ""
                            p_name = st.text_input("Име на наказания", key=f"tpn_{ticket['id']}_{i}")
                            p_val = st.text_input("Размер на наказанието", key=f"tpv_{ticket['id']}_{i}")
                            st.markdown("</div>", unsafe_allow_html=True)

                        col3, col4, col5 = st.columns(3)
                        a1 = col3.selectbox("Изпълнител 1", ["Избери..."] + sys_users + ROLES_LIST, key=f"ta1_{ticket['id']}_{i}")
                        a2 = col4.selectbox("Изпълнител 2 (Опц.)", ["-"] + sys_users + ROLES_LIST, key=f"ta2_{ticket['id']}_{i}")
                        dl = col5.date_input("Срок", key=f"tdl_{ticket['id']}_{i}")
                        st.markdown("---")

                    col_btn1, col_btn2 = st.columns([1, 2])
                    with col_btn1:
                        st.button("➕ Добави още една задача", key=f"btn_add_t_{ticket['id']}", on_click=add_task_field)
                    with col_btn2:
                        submit_tasks = st.button("💾 ЗАПАЗИ ЗАДАЧИТЕ В БАЗАТА", type="primary", key=f"btn_save_t_{ticket['id']}")

                    if submit_tasks:
                        logs = []
                        has_field_check = False
                        for i in range(st.session_state[task_key]):
                            conc = st.session_state.get(f"tc_{ticket['id']}_{i}")
                            rec = st.session_state.get(f"tr_{ticket['id']}_{i}")
                            if conc in ["Избери...", None] or rec in ["Избери...", None]: continue
                            
                            det = st.session_state.get(f"td_{ticket['id']}_{i}", "")
                            a1 = st.session_state.get(f"ta1_{ticket['id']}_{i}")
                            a2 = st.session_state.get(f"ta2_{ticket['id']}_{i}")
                            dl = st.session_state.get(f"tdl_{ticket['id']}_{i}")
                            
                            if rec == "Проверка (поле)": has_field_check = True

                            # Запис на задачата (тук данните са си били пълни и преди)
                            supabase.table("ticket_tasks").insert({
                                "complaint_id": ticket['id'], "recommendation_type": rec,
                                "task_description": f"Заключение: {conc} | Детайли: {det}",
                                "assigned_to_1": a1 if a1 != "Избери..." else None,
                                "assigned_to_2": a2 if a2 != "-" else None,
                                "deadline_date": str(dl), "created_by": st.session_state.username
                            }).execute()

                            # Запис на наказание и генериране на лог
                            if conc == "Нарушение":
                                rb = st.session_state.get(f"trb_{ticket['id']}_{i}")
                                rsel = st.session_state.get(f"trs_{ticket['id']}_{i}")
                                rcust = st.session_state.get(f"trc_{ticket['id']}_{i}", "")
                                p_name = st.session_state.get(f"tpn_{ticket['id']}_{i}", "")
                                p_val = st.session_state.get(f"tpv_{ticket['id']}_{i}", "")
                                
                                rule_id = None
                                applied_rule_text = rsel
                                if rsel not in ["Избери...", "Друго (Свободен текст)", None]:
                                    rule_match = df_rules[(df_rules['rulebook_name'] == rb) & (df_rules['rule_text'] == rsel)]
                                    if not rule_match.empty:
                                        rule_id = int(rule_match.iloc[0]['id'])
                                elif rsel == "Друго (Свободен текст)":
                                    applied_rule_text = f"Друго: {rcust}"
                                
                                supabase.table("penalties").insert({
                                    "complaint_id": ticket['id'], "employee_name": p_name, "rule_id": rule_id,
                                    "custom_rule_text": rcust, "penalty_description": p_val, "created_by": st.session_state.username
                                }).execute()
                                
                                logs.append(f"Назначена задача: {rec} (Нарушено правило: {applied_rule_text} | Наказан: {p_name} - {p_val})")
                            else:
                                # КОРЕКЦИЯ 2: Обогатен запис за стандартните задачи
                                assignees_str = a1 if a1 != "Избери..." else "Неизвестен"
                                if a2 and a2 != "-": assignees_str += f", {a2}"
                                
                                logs.append(f"Назначена задача: {rec} (Заключение: {conc} | Детайли: {det} | Изпълнители: {assignees_str})")

                        if logs:
                            supabase.table("complaint_history").insert({
                                "complaint_id": ticket['id'], "action_type": "Възложени паралелни задачи",
                                "action_details": " | ".join(logs), "created_by": st.session_state.username
                            }).execute()
                            next_stat = "Чака проверка" if has_field_check else "Чака приключване"
                            supabase.table("complaints").update({"current_status": next_stat}).eq("id", ticket['id']).execute()
                            st.session_state.auto_open_ticket_id = ticket['id']
                            st.success("Успешно записани!")
                            st.rerun()

                # РЕЖИМ ПРИКЛЮЧВАНЕ
                elif mode == "🏁 Окончателно приключване на сигнала":
                    res_key = f"r_cnt_{ticket['id']}"
                    if res_key not in st.session_state: st.session_state[res_key] = 1

                    def add_result_field():
                        if st.session_state[res_key] < 10: st.session_state[res_key] += 1

                    st.warning("Въвеждате окончателните резултати. Сигналът ще бъде затворен.")
                    for i in range(st.session_state[res_key]):
                        st.markdown(f"**Резултат {i+1}**")
                        col1, col2 = st.columns(2)
                        conc = col1.selectbox("Заключение", ["Избери..."] + CONCLUSIONS, key=f"rc_{ticket['id']}_{i}")
                        rec = col2.selectbox("Препоръка / Изход", ["Избери..."] + RECOMMENDATIONS, key=f"rr_{ticket['id']}_{i}")
                        details = st.text_input("Детайли / Коментар (до 500 симв.)", key=f"rd_{ticket['id']}_{i}")
                        
                        if conc == "Нарушение":
                            st.markdown("<div style='background-color:#4a1e1e; padding:10px; border-radius:5px;'>", unsafe_allow_html=True)
                            crb = st.selectbox("Правилник", ["Избери..."] + rulebooks, key=f"rrb_{ticket['id']}_{i}")
                            rule_opts = ["Избери..."]
                            if crb != "Избери...": rule_opts += df_rules[df_rules['rulebook_name'] == crb]['rule_text'].tolist()
                            rule_opts.append("Друго (Свободен текст)")
                            r_sel = st.selectbox("Правило", rule_opts, key=f"rrs_{ticket['id']}_{i}")
                            r_cust = st.text_input("Опишете правилото", key=f"rrc_{ticket['id']}_{i}") if r_sel == "Друго (Свободен текст)" else ""
                            p_name = st.text_input("Име на наказания", key=f"rpn_{ticket['id']}_{i}")
                            p_val = st.text_input("Размер на наказанието", key=f"rpv_{ticket['id']}_{i}")
                            st.markdown("</div>", unsafe_allow_html=True)
                        st.markdown("---")
                    
                    col_btn3, col_btn4 = st.columns([1, 2])
                    with col_btn3:
                        st.button("➕ Добави още един резултат", key=f"btn_add_r_{ticket['id']}", on_click=add_result_field)
                    with col_btn4:
                        submit_close = st.button("✅ ПРИКЛЮЧИ СИГНАЛА ОКОНЧАТЕЛНО", type="primary", key=f"btn_close_{ticket['id']}")

                    if submit_close:
                        logs = []
                        for i in range(st.session_state[res_key]):
                            conc = st.session_state.get(f"rc_{ticket['id']}_{i}")
                            rec = st.session_state.get(f"rr_{ticket['id']}_{i}")
                            if conc in ["Избери...", None] or rec in ["Избери...", None]: continue
                            
                            det = st.session_state.get(f"rd_{ticket['id']}_{i}", "")
                            log_text = f"[{conc}] {rec} -> {det}"

                            if conc == "Нарушение":
                                rb = st.session_state.get(f"rrb_{ticket['id']}_{i}")
                                rsel = st.session_state.get(f"rrs_{ticket['id']}_{i}")
                                rcust = st.session_state.get(f"rrc_{ticket['id']}_{i}", "")
                                p_name = st.session_state.get(f"rpn_{ticket['id']}_{i}", "")
                                p_val = st.session_state.get(f"rpv_{ticket['id']}_{i}", "")
                                
                                rule_id = None
                                applied_rule_text = rsel
                                if rsel not in ["Избери...", "Друго (Свободен текст)", None]:
                                    rule_match = df_rules[(df_rules['rulebook_name'] == rb) & (df_rules['rule_text'] == rsel)]
                                    if not rule_match.empty:
                                        rule_id = int(rule_match.iloc[0]['id'])
                                elif rsel == "Друго (Свободен текст)":
                                    applied_rule_text = f"Друго: {rcust}"
                                
                                supabase.table("penalties").insert({
                                    "complaint_id": ticket['id'], "employee_name": p_name, "rule_id": rule_id,
                                    "custom_rule_text": rcust, "penalty_description": p_val, "created_by": st.session_state.username
                                }).execute()
                                
                                log_text += f" (Нарушено правило: {applied_rule_text} | Наказан: {p_name} - {p_val})"
                            logs.append(log_text)

                        final_log = " | ".join(logs) if logs else "Сигналът е приключен без детайлни резултати."
                        supabase.table("complaints").update({"current_status": "Приключено", "current_deadline": None}).eq("id", ticket['id']).execute()
                        supabase.table("complaint_history").insert({
                            "complaint_id": ticket['id'], "action_type": "Сигналът е приключен (Финални резултати)",
                            "action_details": final_log, "created_by": st.session_state.username
                        }).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.success("Сигналът е приключен!")
                        st.rerun()

        st.markdown("---")
        if has_cancel:
            with st.expander("🚫 Опции за анулиране (Сгрешен запис)"):
                cancel_reason = st.text_area("Причина за анулиране:", max_chars=500, key=f"cancel_reason_{ticket['id']}")
                if st.button("ПОТВЪРДИ АНУЛИРАНЕТО", type="secondary", key=f"btn_cancel_{ticket['id']}"):
                    if not cancel_reason.strip(): st.error("Моля, въведете причина.")
                    else:
                        supabase.table("complaint_history").insert({
                            "complaint_id": ticket['id'], "action_type": "Сигналът е АНУЛИРАН", 
                            "action_details": f"Причина: {cancel_reason}", "created_by": st.session_state.username
                        }).execute()
                        supabase.table("complaints").update({"current_status": "Сгрешен/Анулиран", "current_deadline": None}).eq("id", ticket['id']).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.rerun()

    with tab_email:
        render_email_tab(ticket, history_data, company_name, client_name_safe, current_status)

    if st.session_state.user_role == "Супер-админ":
        st.markdown("---")
        with st.expander("☢️ Опасна зона: Hard Delete на Сигнала"):
            st.error("Внимание! Това действие е необратимо.")
            if st.button("❌ ИЗТРИЙ ТОЗИ СИГНАЛ НАПЪЛНО", key=f"hard_del_{ticket['id']}", type="primary"):
                try:
                    supabase.table("complaints").delete().eq("id", ticket['id']).execute()
                    st.success("✅ Сигналът беше изтрит успешно!")
                    st.rerun()
                except Exception as e: st.error(f"Грешка: {e}")
