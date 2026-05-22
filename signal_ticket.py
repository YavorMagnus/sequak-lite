import streamlit as st
import pandas as pd
import re
import urllib.parse
from utils import (supabase, COMPANY_MAP, ROLES_LIST, CONCLUSIONS, 
                   RECOMMENDATIONS, TERMINAL_STATUSES, get_related_signals, 
                   check_permission)

@st.dialog("Картон на сигнала", width="large")
def show_ticket_details(ticket, df_complaints_param):
    tab_main, tab_email = st.tabs(["📑 Данни и Действия", "📧 Композиране на мейл - шарено"])
    
    history_res = supabase.table("complaint_history").select("*").eq("complaint_id", ticket['id']).order("created_at", desc=False).execute()
    history_data = history_res.data
    current_status = ticket.get('current_status', 'Чака заключение и препоръка')
    
    # Проверка на правата на текущия потребител
    has_edit = check_permission("ro_registry", "edit_kanban")
    has_cancel = check_permission("ro_registry", "cancel_ticket")
    
    company_name = ticket.get('Фирма')
    if not company_name or company_name == '-':
        c_id = ticket.get('company_id')
        company_name = next((code for code, i in COMPANY_MAP.items() if i == c_id), '-')
    
    with tab_main:
        related_df = get_related_signals(ticket, df_complaints_param)
        
        if not related_df.empty:
            st.error(f"⚠️ **ВНИМАНИЕ: Открити са {len(related_df)} свързани сигнала за този клиент през последните 30 дни!**")
            for _, dup_row in related_df.iterrows():
                dup_date = pd.to_datetime(dup_row.get('event_datetime')).strftime('%d.%m.%Y')
                dup_status = dup_row.get('current_status', 'Неопределен')
                dup_comp = dup_row.get('Фирма')
                if not dup_comp or dup_comp == '-':
                    dup_c_id = dup_row.get('company_id')
                    dup_comp = next((code for code, i in COMPANY_MAP.items() if i == dup_c_id), '-')
                
                with st.expander(f"Свързан сигнал от {dup_date} ({dup_comp}) - Статус: {dup_status}"):
                    st.markdown(f"**Канал:** {dup_row.get('channel', '-')} | **Касае:** {dup_row.get('case_type', '-')}")
                    st.markdown(f"**Описание:** {dup_row.get('description', '-')}")
                    st.info("💡 *Бележка: За да редактирате този свързан сигнал, използвайте Търсачката.*")
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

        st.subheader("📋 Хронология на действията")
        if not history_data:
            st.write("Все още няма предприети действия.")
        else:
            for record in history_data:
                created_at_fmt = pd.to_datetime(record['created_at']).strftime('%d.%m.%Y %H:%M')
                deadline_str = f" | Срок: <span style='color:#ff4b4b;'>{record['deadline_date']}</span>" if record.get('deadline_date') else ""
                assigned_str = f" | Към: {record['assigned_to']}" if record.get('assigned_to') else ""
                author = record.get('created_by') or 'Системата'
                raw_details = str(record.get('action_details') or "")
                details_formatted = raw_details.replace(' | ', '<br>🔹 ')
                
                st.markdown(f"""
                <div class="history-card">
                    <strong>{created_at_fmt} - {record['action_type']}</strong> <span style="color: #00aaff; font-size: 0.9em;">(от: {author})</span> {assigned_str} {deadline_str}
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
                    action_text = "Активиран" if new_client_action else "Дезактивиран"
                    supabase.table("complaint_history").insert({
                        "complaint_id": ticket['id'], "action_type": f"Диспут с клиент: {action_text}", "created_by": st.session_state.username
                    }).execute()
                    st.session_state.auto_open_ticket_id = ticket['id']
                    st.rerun()

                if new_client_action:
                    st.markdown('<div class="client-stream"><h4>Въвеждане на комуникация</h4>', unsafe_allow_html=True)
                    client_step = st.selectbox("Изберете етап", ["1. Изпратен мейл до О.К.", "2. Предложение към клиент (от О.К.)", "3. Удовлетвореност (Финал)"], key=f"cs_{ticket['id']}")
                    c_details = ""
                    c_deadline = None
                    
                    if client_step == "1. Изпратен мейл до О.К.":
                        mail_date = st.date_input("Дата на мейла", key=f"md_{ticket['id']}")
                        c_details = f"Изпратен имейл на: {mail_date.strftime('%d.%m.%Y')}"
                    elif client_step == "2. Предложение към клиент (от О.К.)":
                        c_details = st.text_area("Въведете направеното предложение", key=f"pt_{ticket['id']}")
                        c_deadline = st.date_input("Очакван отговор до (Срок)", key=f"pd_{ticket['id']}")
                    elif client_step == "3. Удовлетвореност (Финал)":
                        is_satisfied = st.radio("Удовлетворен ли е клиентът?", ["Да", "Не"], horizontal=True, key=f"sat_{ticket['id']}")
                        follow_up = st.text_input("Детайли към удовлетвореността", key=f"fc_{ticket['id']}")
                        c_details = f"Клиентът е удовлетворен: {is_satisfied}. Детайли: {follow_up}"

                    client_comment = st.text_area("Допълнителен коментар (незадължително)", max_chars=500, key=f"cc_{ticket['id']}")

                    if st.button("💾 Запиши действие с клиент", key=f"btn_c_{ticket['id']}"):
                        final_c_details = c_details
                        if client_comment: final_c_details += f" | Коментар: {client_comment}"
                        history_payload = {
                            "complaint_id": ticket['id'], "action_type": f"Клиент: {client_step.split('. ')[1]}",
                            "action_details": final_c_details, "deadline_date": str(c_deadline) if c_deadline else None,
                            "created_by": st.session_state.username
                        }
                        supabase.table("complaint_history").insert(history_payload).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.write(f"Очаква се действие с клиента: **{'Да' if ticket.get('client_action_needed') else 'Не'}**")
                st.info("⚠️ Нямате права за въвеждане на действия с клиента.")

            st.markdown("---")

            st.subheader("⚙️ Продължаване на процеса (Вътрешен)")
            st.write(f"Текущ мастър статус: **{current_status}**")
            
            if has_edit:
                if current_status == "Чака проверка":
                    st.warning("В момента се изисква проверка според последната стъпка.")
                    check_result = st.text_area("До какво доведе проверката? (до 500 символа)", max_chars=500, key=f"cr_{ticket['id']}")
                    if st.button("Приключи проверката", type="primary", key=f"btn_chk_{ticket['id']}"):
                        if not check_result: st.error("Моля, въведете резултат от проверката.")
                        else:
                            supabase.table("complaint_history").insert({
                                "complaint_id": ticket['id'], "action_type": "Резултат от проверка", 
                                "action_details": check_result, "created_by": st.session_state.username
                            }).execute()
                            supabase.table("complaints").update({"current_status": "Чака заключение и препоръка", "current_deadline": None}).eq("id", ticket['id']).execute()
                            st.session_state.auto_open_ticket_id = ticket['id']
                            st.rerun()
                else:
                    new_conc = st.selectbox("Заключение контролинг", ["Избери..."] + CONCLUSIONS, key=f"nc_{ticket['id']}")
                    conc_comment = st.text_input("Обосновка / Коментар към заключението (незадължително)", max_chars=500, key=f"cc_conc_{ticket['id']}")
                    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                    
                    new_rec = st.selectbox("Препоръка контролинг", ["Избери..."] + RECOMMENDATIONS, key=f"nr_{ticket['id']}")
                    field_details = ""
                    rec_comment = ""
                    if new_rec == "Проверка (поле)": field_details = st.text_input("Какво точно ще се проверява?", max_chars=100, key=f"fd_{ticket['id']}")
                    else: rec_comment = st.text_input("Коментар към препоръката (незадължително)", max_chars=500, key=f"ic_{ticket['id']}")
                    st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                    
                    # ИЗВЛИЧАНЕ НА РЕАЛНИТЕ ПОТРЕБИТЕЛИ ЗА УМНО ВЪЗЛАГАНЕ
                    try:
                        sys_users_res = supabase.table("users").select("username").execute()
                        sys_users = sorted([u['username'] for u in sys_users_res.data])
                    except:
                        sys_users = []
                    
                    assignee_options = ["Избери..."] + sys_users + ["--- Бизнес Роли ---"] + ROLES_LIST
                    
                    col_as1, col_as2 = st.columns(2)
                    with col_as1: 
                        assignee = st.selectbox("Възложено на (Потребител или Роля)", assignee_options, key=f"as_{ticket['id']}")
                    with col_as2: 
                        deadline = st.date_input("Ръчен срок (Край до)", value=None, key=f"dl_{ticket['id']}")
                    assignee_comment = st.text_input("Указания / Коментар към изпълнителя (незадължително)", max_chars=500, key=f"ac_ass_{ticket['id']}")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1: save_step = st.button("💾 Запази следваща стъпка", type="primary", key=f"btn_s_{ticket['id']}")
                    with col_btn2: close_ticket = st.button("✅ ПРИКЛЮЧИ СИГНАЛА", key=f"btn_x_{ticket['id']}")

                    if save_step:
                        if new_conc == "Избери..." or new_rec == "Избери...": st.error("Моля, изберете Заключение и Препоръка!")
                        elif new_rec == "Проверка (поле)" and not field_details: st.error("Моля, опишете какво ще се проверява.")
                        elif new_rec != "Проверка (поле)" and (assignee == "Избери..." or assignee == "--- Бизнес Роли ---"): st.error("Моля, изберете на кого възлагате изпълнението!")
                        else:
                            next_status = "Чака проверка" if new_rec == "Проверка (поле)" else "Чака приключване"
                            conc_text = f"Заключение: {new_conc}"
                            if conc_comment: conc_text += f" [{conc_comment}]"
                            rec_text = f"Препоръка: {new_rec}"
                            if new_rec == "Проверка (поле)" and field_details: rec_text += f" [Обект: {field_details}]"
                            elif rec_comment: rec_text += f" [{rec_comment}]"
                            full_details = f"{conc_text} | {rec_text}"
                            if assignee_comment: full_details += f" | Указания към изпълнител: {assignee_comment}"
                                
                            supabase.table("complaint_history").insert({
                                "complaint_id": ticket['id'], "action_type": "Назначена стъпка", "action_details": full_details,
                                "assigned_to": assignee if assignee not in ["Избери...", "--- Бизнес Роли ---"] else None, 
                                "deadline_date": str(deadline) if deadline else None,
                                "created_by": st.session_state.username
                            }).execute()
                            supabase.table("complaints").update({"current_status": next_status, "current_deadline": str(deadline) if deadline else None}).eq("id", ticket['id']).execute()
                            st.session_state.auto_open_ticket_id = ticket['id']
                            st.rerun()
                            
                    if close_ticket:
                        close_details = "Сигналът е приключен."
                        supabase.table("complaints").update({"current_status": "Приключено", "current_deadline": None}).eq("id", ticket['id']).execute()
                        supabase.table("complaint_history").insert({"complaint_id": ticket['id'], "action_type": "Сигналът е приключен", "action_details": close_details, "created_by": st.session_state.username}).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.rerun()
            else:
                st.info("⚠️ Нямате права за промяна на вътрешния процес.")

        st.markdown("---")
        
        if has_cancel:
            with st.expander("🚫 Опции за анулиране (Сгрешен запис)"):
                st.warning("Внимание: Анулирането ще преустанови следенето на този сигнал.")
                cancel_reason = st.text_area("Причина за анулиране (задължително):", max_chars=500, key=f"cancel_reason_{ticket['id']}")
                if st.button("ПОТВЪРДИ АНУЛИРАНЕТО", type="secondary", key=f"btn_cancel_{ticket['id']}"):
                    if not cancel_reason.strip(): st.error("Моля, въведете причина за анулирането.")
                    else:
                        supabase.table("complaint_history").insert({
                            "complaint_id": ticket['id'], "action_type": "Сигналът е АНУЛИРАН", 
                            "action_details": f"Причина: {cancel_reason}", "created_by": st.session_state.username
                        }).execute()
                        supabase.table("complaints").update({"current_status": "Сгрешен/Анулиран", "current_deadline": None}).eq("id", ticket['id']).execute()
                        st.session_state.auto_open_ticket_id = ticket['id']
                        st.rerun()

    with tab_email:
        st.markdown("Изберете кои елементи да присъстват в мейла чрез чекбоксовете вдясно. Всичко се обновява на живо.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_data_1, col_chk_1 = st.columns([11, 1])
        with col_data_1:
            st.markdown(f"<strong style='font-size:1.1em;'>Сигнал от: {client_name_safe}</strong>", unsafe_allow_html=True)
            st.caption(f"Дата: {ticket.get('event_datetime', '')} | Канал: {ticket.get('channel', '')} | Касае: {ticket.get('case_type', '')}")
            sc1, sc2 = st.columns(2)
            sc1.write(f"Телефон: {ticket.get('client_phone', '-')}")
            sc1.write(f"Имейл: {ticket.get('client_email', '-')}")
            sc1.write(f"ЕИК: {ticket.get('client_eik', '-')}")
            sc2.write(f"Фирма: {company_name}")
            sc2.write(f"Консултант: {ticket.get('consultant', '-')}")
            sc2.write(f"Договор №: {ticket.get('contract_number', '-')}")
            sc2.write(f"Машина/и: {ticket.get('machines', '-')}")
            sc2.write(f"Аудио запис: {ticket.get('call_number', '-')}")
        with col_chk_1:
            st.markdown("<br><br>", unsafe_allow_html=True)
            inc_main_info = st.checkbox("", value=True, key=f"chk_main_{ticket['id']}")
            
        st.markdown("---")

        col_data_2, col_chk_2 = st.columns([11, 1])
        with col_data_2: st.info(f"**Описание:** {ticket.get('description', '')}")
        with col_chk_2:
            st.markdown("<br>", unsafe_allow_html=True)
            inc_description = st.checkbox("", value=True, key=f"chk_desc_{ticket['id']}")
            
        st.markdown("---")

        st.markdown("📝 **Хронология на действията**")
        selected_history = []
        if history_data:
            for idx, rec in enumerate(history_data):
                dt_fmt = pd.to_datetime(rec['created_at']).strftime('%d.%m.%Y %H:%M')
                author = rec.get('created_by') or 'Системата'
                raw_details = str(rec.get('action_details') or "")
                details_formatted = raw_details.replace(' | ', '<br>🔹 ')
                
                col_data_h, col_chk_h = st.columns([11, 1])
                with col_data_h:
                    st.markdown(f"""
                    <div style="background-color: #2a2a2a; padding: 10px; border-left: 3px solid #FFD700; margin-bottom: 5px; border-radius: 4px;">
                        <strong>{dt_fmt} - {rec['action_type']}</strong> <span style="color: #00aaff; font-size: 0.9em;">(от: {author})</span><br>
                        <span style="color: #cccccc;">{details_formatted}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with col_chk_h:
                    st.markdown("<br>", unsafe_allow_html=True)
                    is_checked = st.checkbox("", value=True, key=f"chk_hist_{ticket['id']}_{idx}")
                    if is_checked: selected_history.append(rec)
        else: st.write("Няма действия в хронологията.")
            
        st.markdown("### 👁️ Предварителен преглед на мейла")
        st.caption("👇 **МАРКИРАЙ С МИШКАТА рамката по-долу, натисни Ctrl+C и пейстни (Ctrl+V) директно в Outlook.**")
        
        html_content = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #333333; max-width: 800px; background-color: #ffffff; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <p style="font-size: 14px;">Здравейте,<br><br>Изпращам информация относно регистриран сигнал в системата SequaK:</p>
        """
        if inc_main_info:
            html_content += f"""
            <h4 style="color: #111111; border-bottom: 2px solid #FFD700; padding-bottom: 5px; margin-top: 20px;">Сигнал от: {client_name_safe}</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px;">
            <tr style="background-color: #f9f9f9;">
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Дата:</b> {ticket.get('event_datetime', '')}</td>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Фирма:</b> {company_name} <br> <span style="color:#666;">(Консултант: {ticket.get('consultant', '-')})</span></td>
            </tr>
            <tr>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Канал:</b> {ticket.get('channel', '')}</td>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Договор №:</b> {ticket.get('contract_number', '-')}</td>
            </tr>
            <tr style="background-color: #f9f9f9;">
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Телефон:</b> {ticket.get('client_phone', '-')}</td>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Машина/и:</b> {ticket.get('machines', '-')}</td>
            </tr>
            <tr>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Имейл:</b> {ticket.get('client_email', '-')}</td>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Аудио запис:</b> {ticket.get('call_number', '-')}</td>
            </tr>
            <tr style="background-color: #f9f9f9;">
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>ЕИК:</b> {ticket.get('client_eik', '-')}</td>
            <td style="padding: 8px; border: 1px solid #eeeeee;"><b>Касае:</b> {ticket.get('case_type', '-')}</td>
            </tr>
            </table>
            """
        if inc_description:
            html_content += f"""
            <div style="background-color: #eef7ff; border-left: 4px solid #00aaff; padding: 12px; margin-bottom: 20px; font-size: 13px;">
            <strong style="color: #005580;">Описание на проблема:</strong><br>{ticket.get('description', '')}</div>
            """
        if selected_history:
            html_content += """<h4 style="color: #111111; border-bottom: 2px solid #cccccc; padding-bottom: 5px; margin-top: 20px;">Хронология на действията</h4>"""
            for rec in selected_history:
                dt_fmt = pd.to_datetime(rec['created_at']).strftime('%d.%m.%Y %H:%M')
                author = rec.get('created_by') or 'Системата'
                raw_details_email = str(rec.get('action_details') or "")
                details_html_email = raw_details_email.replace(' | ', '<br>🔹 ')
                html_content += f"""
                <div style="margin-bottom: 10px; padding-left: 10px; border-left: 3px solid #FFD700; font-size: 13px;">
                <span style="color: #777777; font-size: 11px;">{dt_fmt} (от: <b>{author}</b>)</span><br>
                <strong>{rec['action_type']}</strong><br><span style="color: #444444;">{details_html_email}</span></div>
                """
        html_content += f"""
        <br><p style="font-size: 13px; border-top: 1px dashed #cccccc; padding-top: 10px;">
        <b>Текущ статус на сигнала:</b> <span style="color: #d35400;">{current_status}</span></p>
        <p style="font-size: 13px; color: #555555;">Поздрави,<br><b>{st.session_state.username}</b></p></div>
        """
        clean_html = re.sub(r'\n\s+', ' ', html_content)
        st.markdown(f'<div class="email-preview-box">{clean_html}</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.expander("🔗 Резервен вариант (Ако искате мейл само с прост текст)"):
            plain_text = f"Здравейте,\n\nСигнал от: {client_name_safe}\nФирма: {company_name}\nКонсултант: {ticket.get('consultant', '-')}\nТекущ статус: {current_status}\n\n"
            if inc_description: plain_text += f"Описание:\n{ticket.get('description', '')}\n\n"
            plain_text += f"Поздрави,\n{st.session_state.username}"
            subject_encoded = urllib.parse.quote(f"Информация за сигнал от клиент: {client_name_safe}")
            body_encoded = urllib.parse.quote(plain_text)
            mailto_link = f"mailto:?subject={subject_encoded}&body={body_encoded}"
            st.markdown(f"""
            <a href="{mailto_link}" target="_blank">
                <button style="background-color: #333333; color: white; border: 1px solid #555; padding: 5px 15px; border-radius: 4px; cursor: pointer;">✉️ Отвори в Outlook (Само текст)</button>
            </a>
            """, unsafe_allow_html=True)

    # HARD DELETE ЗОНА (САМО ЗА СУПЕР-АДМИН)
    if st.session_state.user_role == "Супер-админ":
        st.markdown("---")
        with st.expander("☢️ Опасна зона: Hard Delete на Сигнала"):
            st.error("Внимание! Това действие е необратимо. Сигналът и цялата му хронология ще бъдат изтрити от базата данни завинаги.")
            if st.button("❌ ИЗТРИЙ ТОЗИ СИГНАЛ НАПЪЛНО", key=f"hard_del_{ticket['id']}", type="primary"):
                try:
                    # Изтриваме първо хронологията (ако няма CASCADE)
                    supabase.table("complaint_history").delete().eq("complaint_id", ticket['id']).execute()
                    supabase.table("complaints").delete().eq("id", ticket['id']).execute()
                    
                    st.success("✅ Сигналът беше изтрит успешно!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Възникна грешка при изтриването: {e}")
