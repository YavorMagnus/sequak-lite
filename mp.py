import streamlit as st
import pandas as pd
import numpy as np
import datetime
import io
import time
import plotly.express as px
from utils import supabase, COMPANY_MAP, standardize_company_code, check_permission

def render_mp_dashboard():
    try:
        response_pp = supabase.table("missed_profits").select("*, companies(code)").limit(100000).execute()
        df_pp = pd.DataFrame(response_pp.data)
        
        if not df_pp.empty:
            df_pp['company_code'] = df_pp['companies'].apply(lambda x: x.get('code', 'UNKNOWN').upper() if isinstance(x, dict) else 'UNKNOWN')
            df_pp['clean_machine'] = df_pp['item_tag'].apply(lambda x: str(x).split('|')[-1].strip() if '|' in str(x) else str(x))
            df_pp['event_date'] = pd.to_datetime(df_pp['event_date'], errors='coerce')
            if df_pp['event_date'].dt.tz is not None:
                df_pp['event_date'] = df_pp['event_date'].dt.tz_localize(None)
        else:
            df_pp['company_code'] = 'UNKNOWN'
            df_pp['clean_machine'] = 'UNKNOWN'
            df_pp['event_date'] = pd.to_datetime(datetime.date.today())

        st.title("📊 ПП (Пропуснати ползи) - Дашборд")
        
        if df_pp.empty:
            st.info("В момента няма заредени данни за пропуснати ползи.")
        else:
            min_date = df_pp['event_date'].min().date() if pd.notna(df_pp['event_date'].min()) else datetime.date.today()
            max_date = df_pp['event_date'].max().date() if pd.notna(df_pp['event_date'].max()) else datetime.date.today()
            
            st.markdown("### 🔍 Избор на период")
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                date_range = st.date_input("Покажи данни за времето от-до:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_filtered = df_pp[(df_pp['event_date'].dt.date >= start_date) & (df_pp['event_date'].dt.date <= end_date)].copy()
            else:
                df_filtered = df_pp.copy()

            st.markdown("---")
            
            if 'resolution_status' in df_filtered.columns:
                df_filtered['safe_status_kpi'] = df_filtered['resolution_status'].astype(str).str.lower().str.strip()
                valid_statuses = ['отказва се', 'нямаме наличност']
                df_kpi = df_filtered[df_filtered['safe_status_kpi'].isin(valid_statuses)]
                
                total_eur = df_kpi['total_value_eur'].sum() if not df_kpi.empty else 0
                total_count = len(df_kpi)
                avg_eur = total_eur / total_count if total_count > 0 else 0
                all_searches_count = len(df_filtered)
            else:
                total_eur, total_count, avg_eur, all_searches_count = 0, 0, 0, 0

            st.markdown('<div class="analytic-card">', unsafe_allow_html=True)
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Анализирани разговори (бр.)", f"{all_searches_count} бр.")
            kpi2.metric("Пропуснати ползи (отказва се/няма наличност)", f"€ {total_eur:,.2f}")
            kpi3.metric("Обаждания с пропусната полза", f"{total_count} бр.")
            kpi4.metric("Средна пропусната полза", f"€ {avg_eur:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)

            col_ch1, col_ch2 = st.columns([1.5, 1])
            
            with col_ch1:
                st.subheader("📑 Анализ по Статус / Фирми")
                tab_table, tab_chart = st.tabs(["📊 Детайли по Статус", "📈 Обща Графика"])
                
                with tab_table:
                    if not df_filtered.empty and 'resolution_status' in df_filtered.columns:
                        df_status = df_filtered.copy()
                        df_status['safe_status'] = df_status['resolution_status'].astype(str).str.lower().str.strip()
                        df_status['refused_count'] = df_status['safe_status'].str.contains('отказва се', na=False).astype(int)
                        df_status['refused_sum'] = np.where(df_status['safe_status'].str.contains('отказва се', na=False), df_status['total_value_eur'], 0)
                        df_status['no_stock_count'] = df_status['safe_status'].str.contains('нямаме наличност', na=False).astype(int)
                        df_status['no_stock_sum'] = np.where(df_status['safe_status'].str.contains('нямаме наличност', na=False), df_status['total_value_eur'], 0)
                        df_status['not_offered_count'] = df_status['safe_status'].str.contains('не предлагаме', na=False).astype(int)

                        status_summary = df_status.groupby('company_code')[
                            ['refused_count', 'refused_sum', 'no_stock_count', 'no_stock_sum', 'not_offered_count']
                        ].sum().reset_index()
                        
                        status_summary.columns = [
                            'Фирма', 'Отказва се (Бр.)', 'Отказва се (€)', 
                            'Няма наличност (Бр.)', 'Няма наличност (€)', 'Не предлагаме (Бр.)'
                        ]
                        status_summary = status_summary.sort_values(by='Няма наличност (€)', ascending=False)
                        status_summary['Общо (Бр.)'] = status_summary['Отказва се (Бр.)'] + status_summary['Няма наличност (Бр.)'] + status_summary['Не предлагаме (Бр.)']
                        status_summary['Общо (€)'] = status_summary['Отказва се (€)'] + status_summary['Няма наличност (€)']
                        
                        total_row = pd.DataFrame({
                            'Фирма': ['ОБЩО'],
                            'Отказва се (Бр.)': [status_summary['Отказва се (Бр.)'].sum()],
                            'Отказва се (€)': [status_summary['Отказва се (€)'].sum()],
                            'Няма наличност (Бр.)': [status_summary['Няма наличност (Бр.)'].sum()],
                            'Няма наличност (€)': [status_summary['Няма наличност (€)'].sum()],
                            'Не предлагаме (Бр.)': [status_summary['Не предлагаме (Бр.)'].sum()],
                            'Общо (Бр.)': [status_summary['Общо (Бр.)'].sum()],
                            'Общо (€)': [status_summary['Общо (€)'].sum()]
                        })
                        
                        status_summary = pd.concat([total_row, status_summary], ignore_index=True)

                        styled_status = status_summary.style.format({
                            'Отказва се (€)': '€ {:,.2f}', 'Няма наличност (€)': '€ {:,.2f}', 'Общо (€)': '€ {:,.2f}'
                        }).set_properties(**{'color': '#FFFFFF'}).set_table_styles([{'selector': 'th', 'props': [('color', 'white !important')]}])
                        
                        st.dataframe(styled_status, use_container_width=True, hide_index=True)
                    else:
                        st.write("Няма данни за статуси в избрания период.")
                
                with tab_chart:
                    if not df_filtered.empty:
                        company_group = df_filtered.groupby('company_code')['total_value_eur'].sum().reset_index()
                        company_group = company_group.sort_values('total_value_eur', ascending=False)
                        fig = px.bar(company_group, x='company_code', y='total_value_eur', 
                                     labels={'company_code': 'Фирма', 'total_value_eur': 'Стойност (€)'},
                                     color='company_code', color_discrete_sequence=px.colors.sequential.Plasma)
                        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='white', showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.write("Няма данни за избрания период.")

            with col_ch2:
                st.subheader("🏆 Топ 15 Машини")
                
                status_filter = st.radio(
                    "Срез по статус на обаждането:",
                    ["Всички", "Информира се", "Отказва се", "Нямаме наличност", "Не предлагаме"],
                    horizontal=True, index=3
                )

                if status_filter != "Всички":
                    df_top15_base = df_filtered[df_filtered['resolution_status'].astype(str).str.strip().str.lower() == status_filter.lower()]
                else:
                    df_top15_base = df_filtered.copy()

                tab_all, tab_ren, tab_cim, tab_mas, tab_cmx = st.tabs(["Всички", "REN", "CIM", "MAS", "CMX"])
                
                def show_top_15(df_to_show, current_status):
                    if df_to_show.empty or 'clean_machine' not in df_to_show.columns:
                        st.write("Няма данни за този срез.")
                        return

                    if current_status in ["Не предлагаме", "Информира се", "Всички"]:
                        top_15 = df_to_show.groupby('clean_machine').size().reset_index(name='Брой')
                        top_15 = top_15.nlargest(15, 'Брой')
                        top_15.columns = ['Машина', 'Търсения (бр.)']
                        styled_df = top_15.style.format({'Търсения (бр.)': '{} бр.'}).set_properties(**{'color': '#FFFFFF'}).set_table_styles([{'selector': 'th', 'props': [('color', 'white !important')]}])
                    else:
                        top_15 = df_to_show.groupby('clean_machine')['total_value_eur'].sum().nlargest(15).reset_index()
                        top_15.columns = ['Машина', 'Изпусната сума (€)']
                        styled_df = top_15.style.format({'Изпусната сума (€)': '€ {:,.2f}'}).set_properties(**{'color': '#FFFFFF'}).set_table_styles([{'selector': 'th', 'props': [('color', 'white !important')]}])

                    st.dataframe(styled_df, use_container_width=True, hide_index=True)

                with tab_all: show_top_15(df_top15_base, status_filter)
                with tab_ren: show_top_15(df_top15_base[df_top15_base['company_code'] == 'REN'], status_filter)
                with tab_cim: show_top_15(df_top15_base[df_top15_base['company_code'].isin(['CIM', 'RCD'])], status_filter)
                with tab_mas: show_top_15(df_top15_base[df_top15_base['company_code'] == 'MAS'], status_filter)
                with tab_cmx: show_top_15(df_top15_base[df_top15_base['company_code'] == 'CMX'], status_filter)
            
            st.markdown("---")
            st.subheader("👨‍💼 Анализ на отказите по консултанти")
            cons_comp_filter = st.radio("Избор на фирма (за анализ на консултанти):", ["Всички", "REN", "CIM", "MAS", "CMX"], horizontal=True, key="cons_comp_filter")
            
            if cons_comp_filter != "Всички":
                if cons_comp_filter == "CIM": df_cons_base = df_filtered[df_filtered['company_code'].isin(['CIM', 'RCD'])].copy()
                else: df_cons_base = df_filtered[df_filtered['company_code'] == cons_comp_filter].copy()
            else:
                df_cons_base = df_filtered.copy()
            
            if 'consultant' in df_cons_base.columns and not df_cons_base.empty:
                cons_total = df_cons_base.groupby('consultant').size().reset_index(name='Общо анализирани')
                
                df_refused = df_cons_base[df_cons_base['safe_status_kpi'].str.contains('отказва се', na=False)]
                cons_refused = df_refused.groupby('consultant').agg(Отказва_се=('total_value_eur', 'count'), EUR_откази=('total_value_eur', 'sum')).reset_index()
                
                df_problem = df_cons_base[df_cons_base['safe_status_kpi'].str.contains('проблем', na=False)]
                cons_problem = df_problem.groupby('consultant').size().reset_index(name='Проблемни')
                
                cons_stats = pd.merge(cons_total, cons_refused, on='consultant', how='left')
                cons_stats = pd.merge(cons_stats, cons_problem, on='consultant', how='left').fillna(0)
                
                cons_stats = cons_stats.rename(columns={'consultant': 'Име на консултант', 'Отказва_се': 'Отказва се', 'EUR_откази': 'EUR откази'})
                cons_stats['% откази'] = np.where(cons_stats['Общо анализирани'] > 0, (cons_stats['Отказва се'] / cons_stats['Общо анализирани']) * 100, 0)
                cons_stats['% проблемни'] = np.where(cons_stats['Общо анализирани'] > 0, (cons_stats['Проблемни'] / cons_stats['Общо анализирани']) * 100, 0)
                
                cols_order = ['Име на консултант', 'Общо анализирани', 'Отказва се', '% откази', 'EUR откази', 'Проблемни', '% проблемни']
                cons_stats = cons_stats[cols_order]
                cons_stats = cons_stats.sort_values(by=['EUR откази'], ascending=[False])
                
                hide_date = datetime.date(2026, 6, 1)
                is_reader = st.session_state.user_role not in ["Администратор", "Супер-админ"]
                if is_reader and datetime.date.today() < hide_date:
                    cons_stats = cons_stats.drop(columns=['Проблемни', '% проблемни'])

                format_dict = {
                    'Общо анализирани': '{:,.0f}', 'Отказва се': '{:,.0f}', '% откази': '{:.1f} %', 'EUR откази': '€ {:,.2f}'
                }
                if 'Проблемни' in cons_stats.columns:
                    format_dict['Проблемни'] = '{:,.0f}'
                    format_dict['% проблемни'] = '{:.1f} %'

                styled_cons = cons_stats.style.format(format_dict).set_properties(**{'color': '#FFFFFF'}).set_table_styles([{'selector': 'th', 'props': [('color', 'white !important')]}])
                st.dataframe(styled_cons, use_container_width=True, hide_index=True)
            else:
                st.info("В базата няма информация за Консултанти ('КА') за избрания срез.")

            # Експорт - ЗАЩИТЕН
            if check_permission("mp_dashboard", "export"):
                st.markdown("---")
                with st.expander("📥 Изтегляне на филтрираните данни (Excel)"):
                    st.write(f"Готови за изтегляне: **{len(df_filtered)}** записа (отговарящи на избрания по-горе период).")
                    buffer_pp = io.BytesIO()
                    export_df_pp = df_filtered.copy()
                    if 'companies' in export_df_pp.columns: export_df_pp = export_df_pp.drop(columns=['companies'])
                    with pd.ExcelWriter(buffer_pp, engine='openpyxl') as writer:
                        export_df_pp.to_excel(writer, index=False, sheet_name='Пропуснати_Ползи')
                    st.download_button(label="💾 Изтегли като .xlsx", data=buffer_pp.getvalue(), file_name=f"SequaK_PP_{start_date}_to_{end_date}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    except Exception as e:
        st.error(f"Възникна грешка при зареждане на таблото: {e}")

    # Внос - ЗАЩИТЕН
    if check_permission("mp_dashboard", "upload_data"):
        st.markdown("---")
        st.header("📥 Внос на данни (Пропуснати ползи)")
        uploaded_file = st.file_uploader("Изберете Excel файл (.xlsx)", type=["xlsx", "xls"])
        if uploaded_file is not None:
            try:
                xls_file = pd.ExcelFile(uploaded_file)
                selected_sheet = st.selectbox("Изберете страница:", xls_file.sheet_names)
                df_uploaded = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                st.success(f"✅ Заредена страница '{selected_sheet}'.")
                
                if st.button("🚀 ИЗПРАТИ ДАННИТЕ КЪМ БАЗАТА", type="primary"):
                    required_cols = ['Дата', 'Тагове', 'Обща стойност', 'Резултат', 'Фирма']
                    if all(col in df_uploaded.columns for col in required_cols):
                        cols_to_extract = required_cols.copy()
                        if 'КА' in df_uploaded.columns: cols_to_extract.append('КА')
                        df_to_insert = df_uploaded[cols_to_extract].copy()
                        
                        rename_dict = {'Дата': 'event_date', 'Тагове': 'item_tag', 'Обща стойност': 'total_value_eur', 'Резултат': 'resolution_status'}
                        if 'КА' in df_to_insert.columns: rename_dict['КА'] = 'consultant'
                        df_to_insert = df_to_insert.rename(columns=rename_dict)
                        
                        if 'consultant' in df_to_insert.columns: df_to_insert['consultant'] = df_to_insert['consultant'].fillna('Неизвестен').astype(str)
                        else: df_to_insert['consultant'] = 'Неизвестен'

                        def get_smart_transaction_type(tag):
                            tag_str = str(tag)
                            if 'Наем' in tag_str: return 'Наем'
                            elif 'Поръчка' in tag_str or 'Продажба' in tag_str: return 'Продажба'
                            return 'Неопределен'
                            
                        df_to_insert['transaction_type'] = df_to_insert['item_tag'].apply(get_smart_transaction_type)
                        df_to_insert['event_date'] = pd.to_datetime(df_to_insert['event_date'], dayfirst=True).dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        if df_to_insert['total_value_eur'].dtype == object:
                            df_to_insert['total_value_eur'] = df_to_insert['total_value_eur'].astype(str).str.replace(r'\s+', '', regex=True).str.replace(',', '.')
                        df_to_insert['total_value_eur'] = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0)
                        
                        df_to_insert['resolution_status'] = df_to_insert['resolution_status'].fillna('Неопределен')
                        df_to_insert['mapped_code'] = df_to_insert['Фирма'].apply(standardize_company_code)
                        df_to_insert['company_id'] = df_to_insert['mapped_code'].map(COMPANY_MAP)
                        df_to_insert = df_to_insert.dropna(subset=['item_tag', 'event_date', 'company_id'])
                        df_to_insert = df_to_insert.replace({float('nan'): None, np.nan: None})
                        df_to_insert = df_to_insert.drop_duplicates(subset=['event_date', 'item_tag', 'total_value_eur', 'company_id'])

                        existing_fingerprints = set()
                        if not df_pp.empty and 'event_date' in df_pp.columns:
                            db_cmp = df_pp['company_code'].astype(str).str.strip().str.upper()
                            db_tag = df_pp['item_tag'].astype(str).str.strip().str.lower()
                            db_date = pd.to_datetime(df_pp['event_date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                            db_val = pd.to_numeric(df_pp['total_value_eur'], errors='coerce').fillna(0).round(2).apply(lambda x: f"{x:.2f}")
                            existing_sigs = db_cmp + "|" + db_tag + "|" + db_date + "|" + db_val
                            existing_fingerprints = set(existing_sigs)

                        new_cmp = df_to_insert['mapped_code'].astype(str).str.strip().str.upper()
                        new_tag = df_to_insert['item_tag'].astype(str).str.strip().str.lower()
                        new_date = pd.to_datetime(df_to_insert['event_date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
                        new_val = pd.to_numeric(df_to_insert['total_value_eur'], errors='coerce').fillna(0).round(2).apply(lambda x: f"{x:.2f}")

                        df_to_insert['fingerprint'] = new_cmp + "|" + new_tag + "|" + new_date + "|" + new_val
                        
                        df_final = df_to_insert[~df_to_insert['fingerprint'].isin(existing_fingerprints)].copy()
                        df_final = df_final.drop(columns=['Фирма', 'mapped_code', 'fingerprint'])
                        
                        if df_final.empty:
                            st.info("⚠️ Според бързия филтър всички тези данни вече са качени в базата! Няма нови записи.")
                        else:
                            records = df_final.to_dict(orient='records')
                            total_records = len(records)
                            success_count = 0
                            
                            progress_bar = st.progress(0, text="Инициализация на записите...")
                            status_text = st.empty()
                            
                            for i, record in enumerate(records):
                                try:
                                    supabase.table("missed_profits").insert(record).execute()
                                    success_count += 1
                                except Exception:
                                    pass
                                
                                progress_pct = (i + 1) / total_records
                                progress_bar.progress(progress_pct, text=f"Проверка и запис: {i + 1} от {total_records}...")
                            
                            if success_count > 0:
                                status_text.success(f"🎉 Готово! Бяха добавени {success_count} НОВИ уникални записа (от {total_records} обработени). Презареждам...")
                            else:
                                status_text.warning(f"⚠️ Базата данни отхвърли всички {total_records} записа като дубликати.")
                            
                            time.sleep(3)
                            st.rerun() 
                    else:
                        st.warning("⚠️ Липсват нужни колони (Уверете се, че има 'Дата', 'Тагове', 'Обща стойност', 'Резултат', 'Фирма').")
            except Exception as e:
                st.error(f"Възникна грешка при четене на файла: {e}")
