import streamlit as st
import pandas as pd
import numpy as np
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import re
import plotly.express as px
import io
import urllib.parse
from utils import (supabase, COMPANY_MAP, COMPANY_LIST, parse_smart_time,
                   ROLES_LIST, CONCLUSIONS, RECOMMENDATIONS, TERMINAL_STATUSES,
                   get_related_signals, check_permission)

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

def show_company_tickets(company_code, df_complaints):
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
        status = row.get('current_status', 'Неопределен')
        client = row.get('client_name', 'Неизвестен')
        has_client_action = row.get('client_action_needed', False)
        
        is_overdue = False
        deadline_val = row.get('current_deadline')
        if pd.notna(deadline_val) and status not in TERMINAL_STATUSES:
            dt_obj = pd.to_datetime(deadline_val, errors='coerce')
            if pd.notna(dt_obj) and dt_obj.date() < datetime.date.today(): is_overdue = True
                
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
            if is_overdue: st.markdown("<span style='color:red; font-size:0.8em;'>⚠️ Просрочен!</span>", unsafe_allow_html=True)
        with colC:
            if st.button("Отвори", key=f"btn_open_{row['id']}"): show_ticket_details(row.to_dict(), df_complaints)
        st.divider()

def check_and_show_alerts():
    # Само ако има права за редакция вижда алармите
    if check_permission("ro_registry", "edit_kanban") and not st.session_state.alerts_dismissed:
        try:
            res_active = supabase.table("complaints").select("*, companies(code)").not_.in_("current_status", TERMINAL_STATUSES).execute()
            df_active_alerts = pd.DataFrame(res_active.data)
            
            overdue_tickets = []
            if not df_active_alerts.empty:
                df_active_alerts['Фирма'] = df_active_alerts['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
                for _, row in df_active_alerts.iterrows():
                    dl_val = row.get('current_deadline')
                    if pd.notna(dl_val):
                        dt_obj = pd.to_datetime(dl_val, errors='coerce')
                        if pd.notna(dt_obj) and dt_obj.date() < datetime.date.today():
                            overdue_tickets.append(row)
            
            if len(overdue_tickets) > 0:
                st.markdown("<h1 style='color: #ff4b4b; text-align: center;'>🚨 ВНИМАНИЕ: ПРОСРОЧЕНИ СИГНАЛИ! 🚨</h1>", unsafe_allow_html=True)
                st.markdown(f"<h4 style='text-align: center;'>Имате <b>{len(overdue_tickets)}</b> активни сигнала с изтекъл срок, които изискват вашето внимание.</h4>", unsafe_allow_html=True)
                st.markdown("---")
                
                for tkt in overdue_tickets:
                    col1, col2, col3 = st.columns([4, 2, 1])
                    dt_str = pd.to_datetime(tkt['event_datetime']).strftime('%d.%m.%Y')
                    col1.markdown(f"**Клиент:** {tkt['client_name']} | **Фирма:** {tkt['Фирма']}")
                    col2.markdown(f"<span style='color: #ff4b4b;'>Срок: {tkt['current_deadline']}</span> | Статус: {tkt['current_status']}", unsafe_allow_html=True)
                    with col3:
                        if st.button("Отвори Картона", key=f"alert_btn_{tkt['id']}", use_container_width=True):
                            st.session_state.auto_open_ticket_id = tkt['id']
                            st.session_state.alerts_dismissed = True
                            st.rerun()
                    st.divider()
                    
                st.markdown("<br><br>", unsafe_allow_html=True)
                if st.button("✅ РАЗБРАХ, ПРОДЪЛЖИ КЪМ РАБОТНОТО ПРОСТРАНСТВО", type="primary", use_container_width=True):
                    st.session_state.alerts_dismissed = True
                    st.rerun()
                st.stop()
            else:
                st.session_state.alerts_dismissed = True
        except Exception:
            st.session_state.alerts_dismissed = True

def render_ro_registry():
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
        res = supabase.table("complaints").select("*, companies(code)").limit(100000).execute()
        df_complaints = pd.DataFrame(res.data)
        if not df_complaints.empty:
            df_complaints['Фирма'] = df_complaints['companies'].apply(lambda x: x.get('code', '') if isinstance(x, dict) else '')
            
        hist_res = supabase.table("complaint_history").select("complaint_id, assigned_to, deadline_date, action_details, action_type").order("created_at", desc=True).limit(100000).execute()
        df_hist_full = pd.DataFrame(hist_res.data)
        
        latest_hist_dict = {}
        if not df_hist_full.empty and not df_complaints.empty:
            for cid in df_complaints['id'].unique():
                comp_hist = df_hist_full[df_hist_full['complaint_id'] == cid]
                if not comp_hist.empty:
                    action_steps = comp_hist[comp_hist['action_type'] == 'Назначена стъпка']
                    if not action_steps.empty:
                        last_action = action_steps.iloc[0]
                        action_str = str(last_action.get('action_details', ''))
                        rec_match = re.search(r"Препоръка:\s*(.*?)(?:\s*\||$)", action_str)
                        rec_text = rec_match.group(1).strip() if rec_match else "Няма инфо"
                        latest_hist_dict[cid] = {'assignee': last_action.get('assigned_to') or "Не е посочен", 'recommendation': rec_text}
                    else: latest_hist_dict[cid] = {'assignee': "Не е посочен", 'recommendation': "Няма назначена стъпка"}
                else: latest_hist_dict[cid] = {'assignee': "Не е посочен", 'recommendation': "Няма история"}
    except Exception as e:
        st.error(f"Грешка при връзка с DB: {e}")
        df_complaints = pd.DataFrame()
        df_hist_full = pd.DataFrame()
        latest_hist_dict = {}

    # =========================================================
    # 🔔 ЦЕНТЪР ЗА ИЗВЕСТИЯ (МОИТЕ ЗАДАЧИ)
    # =========================================================
    if not df_complaints.empty and check_permission("ro_registry", "edit_kanban"):
        my_active_tasks = []
        for _, row in df_complaints.iterrows():
            cid = row['id']
            status = row.get('current_status', '')
            if status not in TERMINAL_STATUSES:
                assignee = latest_hist_dict.get(cid, {}).get('assignee', '')
                if assignee == st.session_state.username:
                    my_active_tasks.append(row)

        if my_active_tasks:
            st.markdown(f"""
            <div style="background-color: #0d2136; border-left: 5px solid #00aaff; padding: 15px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0, 170, 255, 0.1);">
                <h3 style="color: #00aaff; margin-top: 0; margin-bottom: 5px;">🔔 Имате {len(my_active_tasks)} задачи, възложени лично на Вас!</h3>
                <p style="color: #ccc; font-size: 0.9em; margin-bottom: 15px;">Следните активни сигнали очакват Вашето действие:</p>
            </div>
            """, unsafe_allow_html=True)

            for task in my_active_tasks:
                col_t1, col_t2, col_t3 = st.columns([4, 2, 1])
                dt_str = pd.to_datetime(task.get('event_datetime')).strftime('%d.%m.%Y') if pd.notna(task.get('event_datetime')) else ""
                col_t1.markdown(f"👤 **{task.get('client_name')}** | 🏢 {task.get('Фирма')} | 📅 {dt_str}")
                col_t2.markdown(f"<span style='color: #FFD700;'>{task.get('current_status')}</span>", unsafe_allow_html=True)
                with col_t3:
                    if st.button("Отвори", key=f"my_task_btn_{task['id']}", use_container_width=True):
                        st.session_state.auto_open_ticket_id = task['id']
                        st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

    tab_list, tab_kanban, tab_new = st.tabs(["👁️ Птичи поглед (Дашборд)", "📋 Канбан дъска", "➕ Въвеждане на нов сигнал"])
    
    with tab_list:
        st.markdown("### 🔍 Търсачка и Списък")
        search_query = st.text_input("Търсене по: Име, Телефон, ЕИК, Имейл, Договор, Машина, Аудио запис или Консултант", placeholder="Въведете текст и натиснете Enter...", key="global_search").strip()
        
        if not df_complaints.empty:
            df_to_display = df_complaints.copy()
            df_to_display['assignee'] = df_to_display['id'].map(lambda x: latest_hist_dict.get(x, {}).get('assignee', 'Не е посочен'))
            
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
                    st.button(f"Отговорник{arrow}", key="btn_sort_assignee", on_click=handle_sort, args=('assignee',), use_container_width=True)
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
                        overdue = sum(1 for _, row in comp_data.iterrows() if row.get('current_status') not in TERMINAL_STATUSES and pd.notna(row.get('current_deadline')) and pd.to_datetime(row.get('current_deadline'), errors='coerce').date() < datetime.date.today())
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
            show_company_tickets(st.session_state.active_company, df_complaints)

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
                is_overdue = pd.notna(tkt.get('current_deadline')) and pd.to_datetime(tkt.get('current_deadline'), errors='coerce').date() < datetime.date.today()
                in_dispute = tkt.get('client_action_needed', False)
                
                meta_info = latest_hist_dict.get(cid, {'assignee': 'Не е посочен', 'recommendation': 'Няма'})
                dl_display = tkt.get('current_deadline') if pd.notna(tkt.get('current_deadline')) else "Няма"
                
                card_class = "kanban-card overdue" if is_overdue else "kanban-card dispute" if in_dispute else "kanban-card"
                badge_dispute = " 🔵 [Диспут]" if in_dispute else ""
                badge_overdue = " 🔴 [Просрочен]" if is_overdue else ""
                
                html_card = f"""
                <div class="{card_class}">
                    <div class="kanban-title">{client}{badge_dispute}{badge_overdue}</div>
                    <div class="kanban-meta">{comp_name} | Дата: {dt_str}</div>
                    <div class="kanban-detail"><strong>Отговорник:</strong> {meta_info['assignee']}</div>
                    <div class="kanban-detail"><strong>Срок до:</strong> {dl_display}</div>
                    <div class="kanban-detail"><strong>Действие:</strong> {meta_info['recommendation']}</div>
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
                with col1: channel = st.selectbox("Канал на постъпване *", ["Телефон", "Email", "Чат", "Друго"])
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
        except Exception: pass

def render_ro_analytics():
    st.title("📈 Анализи и Справки (РО)")
    st.markdown("---")
    
    try:
        res_comp = supabase.table("complaints").select("*, companies(code)").limit(100000).execute()
        df_comp = pd.DataFrame(res_comp.data)
        res_hist = supabase.table("complaint_history").select("*").limit(100000).execute()
        df_hist = pd.DataFrame(res_hist.data)
        
        if not df_comp.empty:
            df_comp['Фирма'] = df_comp['companies'].apply(lambda x: x.get('code', 'UNKNOWN') if isinstance(x, dict) else 'UNKNOWN')
            df_comp['event_datetime'] = pd.to_datetime(df_comp['event_datetime'], errors='coerce')
            if df_comp['event_datetime'].dt.tz is not None: df_comp['event_datetime'] = df_comp['event_datetime'].dt.tz_localize(None)
            
        if not df_hist.empty:
            df_hist['created_at'] = pd.to_datetime(df_hist['created_at'], errors='coerce')
            if df_hist['created_at'].dt.tz is not None: df_hist['created_at'] = df_hist['created_at'].dt.tz_localize(None)
        else: df_hist = pd.DataFrame(columns=['id', 'complaint_id', 'action_type', 'action_details', 'assigned_to', 'deadline_date', 'created_by', 'created_at'])
    except Exception as e:
        st.error(f"Грешка при зареждане: {e}")
        df_comp = pd.DataFrame()
        df_hist = pd.DataFrame()

    if df_comp.empty: st.info("⚠️ Няма достатъчно данни.")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            company_options = ["Всички фирми (Холдинг)"] + sorted([c for c in df_comp['Фирма'].unique() if c])
            selected_company = st.selectbox("Избор на обхват:", company_options)
        with col_f2: period_option = st.radio("Избор на период за анализ:", ["Текущ месец", "Текущо тримесечие", "Текущо полугодие", "Текуща година"], horizontal=True)

        st.markdown("---")
        today = pd.to_datetime(datetime.date.today())
        
        if period_option == "Текущ месец":
            start_current = today.replace(day=1)
            end_current = (start_current + relativedelta(months=1)) - timedelta(days=1)
            start_prev = start_current - relativedelta(months=1)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходния месец"
        elif period_option == "Текущо тримесечие":
            current_quarter = (today.month - 1) // 3 + 1
            start_current = datetime.datetime(today.year, 3 * current_quarter - 2, 1)
            end_current = (start_current + relativedelta(months=3)) - timedelta(days=1)
            start_prev = start_current - relativedelta(months=3)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходното тримесечие"
        elif period_option == "Текущо полугодие":
            current_half = 1 if today.month <= 6 else 2
            start_current = datetime.datetime(today.year, 1 if current_half == 1 else 7, 1)
            end_current = datetime.datetime(today.year, 6, 30) if current_half == 1 else datetime.datetime(today.year, 12, 31)
            start_prev = start_current - relativedelta(months=6)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходното полугодие"
        else:
            start_current = today.replace(month=1, day=1)
            end_current = today.replace(month=12, day=31)
            start_prev = start_current - relativedelta(years=1)
            end_prev = start_current - timedelta(days=1)
            period_label = "предходната година"

        st.write(f"📅 **Анализиран период:** {start_current.strftime('%d.%m.%Y')} - {end_current.strftime('%d.%m.%Y')} (Спрямо: {period_label})")

        if selected_company != "Всички фирми (Холдинг)": df_filtered = df_comp[df_comp['Фирма'] == selected_company].copy()
        else: df_filtered = df_comp.copy()
            
        if df_filtered.empty: st.warning(f"Няма регистрирани сигнали за {selected_company}.")
        else:
            df_active = df_filtered[df_filtered['current_status'] != 'Сгрешен/Анулиран'].copy()
            mask_current_in = (df_active['event_datetime'] >= start_current) & (df_active['event_datetime'] <= end_current)
            mask_prev_in = (df_active['event_datetime'] >= start_prev) & (df_active['event_datetime'] <= end_prev)
            
            count_in_current = len(df_active[mask_current_in])
            count_in_prev = len(df_active[mask_prev_in])
            delta_in = count_in_current - count_in_prev

            closed_history = df_hist[df_hist['action_type'] == "Сигналът е приключен"].copy()
            closed_merged = pd.merge(df_active[['id', 'current_status']], closed_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
            
            count_closed_current = len(closed_merged[(closed_merged['created_at'] >= start_current) & (closed_merged['created_at'] <= end_current)])
            count_closed_prev = len(closed_merged[(closed_merged['created_at'] >= start_prev) & (closed_merged['created_at'] <= end_prev)])
            delta_closed = count_closed_current - count_closed_prev
            
            pct_holding_str = ""
            if selected_company != "Всички фирми (Холдинг)":
                holding_active = df_comp[df_comp['current_status'] != 'Сгрешен/Анулиран']
                holding_closed_merged = pd.merge(holding_active[['id']], closed_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
                total_holding_closed = len(holding_closed_merged[(holding_closed_merged['created_at'] >= start_current) & (holding_closed_merged['created_at'] <= end_current)])
                if total_holding_closed > 0: pct_holding_str = f"({(count_closed_current / total_holding_closed) * 100:.1f}% от холдинга)"

            dispute_history = df_hist[df_hist['action_type'] == "Диспут с клиент: Активиран"].copy()
            dispute_merged = pd.merge(df_active[['id']], dispute_history[['complaint_id', 'created_at']], left_on='id', right_on='complaint_id', how='inner')
            
            count_disputes_current = len(dispute_merged[(dispute_merged['created_at'] >= start_current) & (dispute_merged['created_at'] <= end_current)]['complaint_id'].unique())
            prev_disputes_ids = dispute_merged[(dispute_merged['created_at'] >= start_prev) & (dispute_merged['created_at'] <= end_prev)]['complaint_id'].unique()
            delta_disputes = count_disputes_current - len(prev_disputes_ids)
            pct_disputes = (count_disputes_current / count_in_current * 100) if count_in_current > 0 else 0

            overdue_signals_count = sum(1 for _, row in df_active.iterrows() if pd.notna(row.get('current_deadline')) and row.get('current_status') not in TERMINAL_STATUSES and pd.to_datetime(row.get('current_deadline'), errors='coerce').date() < today.date())
            pct_overdue = (overdue_signals_count / count_in_current * 100) if count_in_current > 0 else 0

            st.markdown('<div class="analytic-card">', unsafe_allow_html=True)
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Постъпили", count_in_current, delta=delta_in)
            m_col2.metric("Приключени", f"{count_closed_current} {pct_holding_str}", delta=delta_closed)
            m_col3.metric("Влезли в диспут", f"{count_disputes_current} ({pct_disputes:.1f}%)", delta=delta_disputes)
            m_col4.metric("С просрочия", f"{overdue_signals_count} ({pct_overdue:.1f}%)")
            st.markdown('</div>', unsafe_allow_html=True)

            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.subheader("Постъпили по Канал")
                if count_in_current > 0:
                    channel_counts = df_active[mask_current_in]['channel'].value_counts().reset_index()
                    channel_counts.columns = ['Канал', 'Брой']
                    fig_channels = px.pie(channel_counts, values='Брой', names='Канал', hole=0.4, color_discrete_sequence=px.colors.sequential.Plasma)
                    fig_channels.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white')
                    st.plotly_chart(fig_channels, use_container_width=True)
                else: st.info("Няма постъпили сигнали за този период.")

            with g_col2:
                st.subheader("Първо Заключение (Приключени)")
                if count_closed_current > 0:
                    closed_ids = closed_merged[(closed_merged['created_at'] >= start_current) & (closed_merged['created_at'] <= end_current)]['id'].tolist()
                    first_conclusions = []
                    for cid in closed_ids:
                        steps = df_hist[(df_hist['complaint_id'] == cid) & (df_hist['action_type'] == 'Назначена стъпка')].sort_values(by='created_at')
                        if not steps.empty:
                            match = re.search(r"Заключение:\s*(.*?)\s*\|", steps.iloc[0]['action_details'])
                            first_conclusions.append(match.group(1).strip() if match else "Неизвестно")
                        else: first_conclusions.append("Без заключение")
                    if first_conclusions:
                        conc_df = pd.DataFrame(first_conclusions, columns=['Заключение']).value_counts().reset_index()
                        conc_df.columns = ['Заключение', 'Брой']
                        fig_conc = px.bar(conc_df, x='Заключение', y='Брой', color='Заключение', color_discrete_sequence=px.colors.qualitative.Set3)
                        fig_conc.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white', showlegend=False)
                        st.plotly_chart(fig_conc, use_container_width=True)
                    else: st.info("Не са намерени заключения.")
                else: st.info("Няма приключени сигнали за този период.")

        st.markdown("---")
        # Експорт - ЗАЩИТЕН
        if check_permission("ro_registry", "export"):
            with st.expander("📥 Експорт на данните (Excel)"):
                if not df_comp.empty:
                    min_date = df_comp['event_datetime'].min().date() if pd.notna(df_comp['event_datetime'].min()) else today.date()
                    max_date = df_comp['event_datetime'].max().date() if pd.notna(df_comp['event_datetime'].max()) else today.date()
                    col_ex1, col_ex2 = st.columns([1, 2])
                    with col_ex1: export_dates = st.date_input("Период за експорт (Начало - Край):", value=(min_date, max_date), min_value=min_date, max_value=max_date)
                    if len(export_dates) == 2:
                        start_export, end_export = export_dates
                        export_df = df_comp[(df_comp['event_datetime'].dt.date >= start_export) & (df_comp['event_datetime'].dt.date <= end_export)].copy()
                        if 'companies' in export_df.columns: export_df = export_df.drop(columns=['companies'])
                        for col in export_df.select_dtypes(include=['datetimetz']).columns: export_df[col] = export_df[col].dt.tz_localize(None)
                        with col_ex2:
                            st.write(f"Готови за експорт: **{len(export_df)} записа**")
                            buffer = io.BytesIO()
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer: export_df.to_excel(writer, index=False, sheet_name='РО_Експорт')
                            st.download_button(label="💾 Изтегли като .xlsx", data=buffer.getvalue(), file_name=f"SequaK_RO_{start_export}_to_{end_export}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                    else:
                        with col_ex2: st.info("Моля, изберете начална и крайна дата в календара.")
                else: st.info("Няма данни за експорт.")
