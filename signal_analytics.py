import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import re
import plotly.express as px
import io
from utils import supabase, check_permission, TERMINAL_STATUSES

def get_dominant_resolution(action_details_str):
    """
    Priority Waterfall (Йерархичен приоритет) за финалните резултати.
    Търси най-тежката мярка в текста и класифицира сигнала по нея.
    """
    if not action_details_str:
        return "Друго / Без приоритет"
        
    priorities = [
        "Реорганизация",
        "Наказание",
        "Обучение",
        "Планиране на ресурс",
        "Техническа корекция",
        "Обсъждане с колега"
    ]
    
    for p in priorities:
        if p in action_details_str:
            return p
            
    return "Друго / Без приоритет"

def render_signal_analytics():
    st.title("📈 Анализи и Справки (Сигнали)")
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

            closed_history = df_hist[df_hist['action_type'].fillna('').str.contains("Сигналът е приключен")].copy()
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
                st.subheader("Водещ резултат (Приключени сигнали)")
                if count_closed_current > 0:
                    closed_ids = closed_merged[(closed_merged['created_at'] >= start_current) & (closed_merged['created_at'] <= end_current)]['id'].tolist()
                    final_resolutions = []
                    
                    for cid in closed_ids:
                        # Търсим финалното действие
                        steps = df_hist[(df_hist['complaint_id'] == cid) & (df_hist['action_type'].fillna('').str.contains('Сигналът е приключен'))].sort_values(by='created_at', ascending=False)
                        
                        if not steps.empty:
                            action_details = str(steps.iloc[0]['action_details'])
                            dom_res = get_dominant_resolution(action_details)
                            
                            # Fallback за стари картони: ако финалното приключване няма детайли, гледаме последната стъпка
                            if dom_res == "Друго / Без приоритет":
                                last_steps = df_hist[(df_hist['complaint_id'] == cid) & (df_hist['action_type'] == 'Назначена стъпка')].sort_values(by='created_at', ascending=False)
                                if not last_steps.empty:
                                    dom_res = get_dominant_resolution(str(last_steps.iloc[0]['action_details']))
                                    
                            final_resolutions.append(dom_res)
                        else: 
                            final_resolutions.append("Без данни")
                            
                    if final_resolutions:
                        conc_df = pd.DataFrame(final_resolutions, columns=['Решение']).value_counts().reset_index()
                        conc_df.columns = ['Водещо Решение', 'Брой']
                        fig_conc = px.bar(conc_df, x='Водещо Решение', y='Брой', color='Водещо Решение', color_discrete_sequence=px.colors.qualitative.Set3)
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
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer: export_df.to_excel(writer, index=False, sheet_name='Сигнали_Експорт')
                            st.download_button(label="💾 Изтегли като .xlsx", data=buffer.getvalue(), file_name=f"SequaK_Signals_{start_export}_to_{end_export}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                    else:
                        with col_ex2: st.info("Моля, изберете начална и крайна дата в календара.")
                else: st.info("Няма данни за експорт.")
