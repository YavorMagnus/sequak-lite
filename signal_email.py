import streamlit as st
import pandas as pd
import re
import urllib.parse

def render_email_tab(ticket, history_data, company_name, client_name_safe, current_status):
    """
    Изолиран модул за рендиране на таба за имейл комуникация.
    """
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
