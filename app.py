import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- КОНФИГУРАЦИЯ СТРАНИЦЫ ---
st.set_page_config(page_title="OSETROFF | Analytics", layout="wide", page_icon="🦈")

st.title("🦈 OSETROFF: Корпоративный Дашборд")
st.markdown("---")

# --- БЛОК ЗАГРУЗКИ ДАННЫХ ---
# Мы делаем так, чтобы файл можно было просто перетащить в браузер
uploaded_file = st.sidebar.file_uploader("📂 Загрузите Excel/CSV отчет", type=['xlsx', 'csv'])

# Функция загрузки
@st.cache_data
def load_data(file):
    data = {'expenses': pd.DataFrame(), 'calls': pd.DataFrame()}
    
    # Если файла нет, возвращаем пустоту
    if file is None:
        return data

    dfs_expenses = []
    sheet_keywords = {
        'promo': ['промо', 'promo', 'маркетинг'],
        'cost': ['себестоим', 'cost', 'затраты'],
        'calls': ['звонки', 'calls', 'продажи'],
    }

    try:
        # Если Excel
        if file.name.endswith('.xlsx'):
            xls = pd.ExcelFile(file)
            for sheet in xls.sheet_names:
                sheet_lower = sheet.lower()
                
                # 1. РАСХОДЫ
                if any(k in sheet_lower for k in sheet_keywords['promo'] + sheet_keywords['cost']):
                    try:
                        df = pd.read_excel(xls, sheet_name=sheet, header=1)
                        if len(df.columns) < 2: df = pd.read_excel(xls, sheet_name=sheet, header=0)
                        
                        df.columns = [str(c).lower() for c in df.columns]
                        rename_map = {c: 'date' for c in df.columns if 'дата' in c or 'date' in c}
                        rename_map.update({c: 'manager' for c in df.columns if 'кто' in c or 'manager' in c})
                        rename_map.update({c: 'amount' for c in df.columns if 'сумма' in c or 'amount' in c})
                        rename_map.update({c: 'qty' for c in df.columns if 'кол-во' in c})
                        rename_map.update({c: 'weight_g' for c in df.columns if 'грам' in c})
                        
                        df = df.rename(columns=rename_map)
                        df['category'] = sheet
                        
                        needed = ['date', 'manager', 'amount', 'qty', 'weight_g', 'category']
                        # Оставляем только существующие колонки
                        valid_cols = [c for c in needed if c in df.columns]
                        df = df[valid_cols]
                        
                        dfs_expenses.append(df)
                    except: pass
                
                # 2. ЗВОНКИ
                if any(k in sheet_lower for k in sheet_keywords['calls']):
                    try:
                        df_c = pd.read_excel(xls, sheet_name=sheet)
                        # Жесткая логика для звонков (обычно колонка 0 - дата, 1 - входящие, 2 - заказы, 4 - кг)
                        # Пробуем найти по именам или индексам
                        df_c = df_c.iloc[:, [0, 1, 2, 4]]
                        df_c.columns = ['date', 'incoming', 'orders', 'sales_kg']
                        data['calls'] = df_c
                    except: pass

        # Сборка расходов
        if dfs_expenses:
            full_exp = pd.concat(dfs_expenses, ignore_index=True)
            if 'date' in full_exp.columns:
                full_exp['date'] = pd.to_datetime(full_exp['date'], errors='coerce')
                full_exp = full_exp.dropna(subset=['date'])
            for col in ['amount', 'qty', 'weight_g']:
                if col in full_exp.columns:
                    full_exp[col] = pd.to_numeric(full_exp[col], errors='coerce').fillna(0)
            data['expenses'] = full_exp

        # Чистка звонков
        if not data['calls'].empty:
            df_c = data['calls']
            df_c['date'] = pd.to_datetime(df_c['date'], errors='coerce')
            df_c = df_c.dropna(subset=['date'])
            for col in ['incoming', 'orders', 'sales_kg']:
                df_c[col] = pd.to_numeric(df_c[col], errors='coerce').fillna(0)
            data['calls'] = df_c
            
    except Exception as e:
        st.error(f"Ошибка обработки файла: {e}")

    return data

# Загружаем данные
db = load_data(uploaded_file)

# --- ЕСЛИ ДАННЫХ НЕТ ---
if uploaded_file is None:
    st.info("👆 Пожалуйста, загрузите файл отчета в меню слева, чтобы начать работу.")
    st.stop()

if db['expenses'].empty and db['calls'].empty:
    st.warning("Файл загружен, но данные не распознаны. Проверьте названия листов (Промо, Звонки, Себестоимость).")
    st.stop()

# --- САЙДБАР (НАСТРОЙКИ) ---
st.sidebar.header("⚙️ Моделирование")
avg_price = st.sidebar.slider("💰 Средняя цена (руб/кг)", 20000, 60000, 35000, 1000)
traffic_mult = st.sidebar.slider("📈 Рост трафика (x)", 0.5, 3.0, 1.0, 0.1)
conv_boost = st.sidebar.slider("🎯 Рост конверсии (%)", -5.0, 10.0, 0.0, 0.5)

# Фильтр менеджеров
managers_list = ['Все']
if not db['expenses'].empty and 'manager' in db['expenses'].columns:
    unique = sorted([str(x) for x in db['expenses']['manager'].unique() if str(x) != 'nan'])
    managers_list += unique

selected_managers = st.sidebar.multiselect("👤 Менеджеры", managers_list, default=['Все'])

# --- РАСЧЕТНАЯ ЧАСТЬ ---
df_exp = db['expenses'].copy()
df_call = db['calls'].copy()

# Фильтрация
if 'Все' not in selected_managers and not df_exp.empty:
    df_exp = df_exp[df_exp['manager'].astype(str).isin(selected_managers)]

# KPI
total_exp = df_exp['amount'].sum() if not df_exp.empty else 0
actual_calls = df_call['incoming'].sum() if not df_call.empty else 0
actual_orders = df_call['orders'].sum() if not df_call.empty else 0
actual_kg = df_call['sales_kg'].sum() if not df_call.empty else 0

# Сценарии
model_calls = actual_calls * traffic_mult
base_conv = (actual_orders / actual_calls * 100) if actual_calls > 0 else 0
model_conv = max(0, base_conv + conv_boost)
model_orders = model_calls * (model_conv / 100)
kg_per_order = (actual_kg / actual_orders) if actual_orders > 0 else 0
model_kg = model_orders * kg_per_order
model_revenue = model_kg * avg_price
model_profit = model_revenue - total_exp

# --- ВИЗУАЛИЗАЦИЯ (KPI) ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Выручка (Model)", f"{model_revenue:,.0f} ₽", delta="Прогноз")
c2.metric("Расходы (Fact)", f"{total_exp:,.0f} ₽", delta_color="inverse")
c3.metric("Прибыль (Est.)", f"{model_profit:,.0f} ₽", delta_color="normal")
c4.metric("Объем продаж", f"{model_kg:.1f} кг")

# --- ГРАФИКИ ---
tab1, tab2, tab3 = st.tabs(["📈 Динамика", "📦 Продукт", "👥 Команда"])

with tab1:
    fig_trend = go.Figure()
    if not df_call.empty:
        df_call['m'] = df_call['date'].dt.to_period('M').astype(str)
        trend = df_call.groupby('m')['sales_kg'].sum().reset_index()
        trend['rev'] = trend['sales_kg'] * avg_price
        fig_trend.add_trace(go.Bar(x=trend['m'], y=trend['rev'], name='Выручка (Модель)', marker_color='#2ecc71'))
    
    if not df_exp.empty:
        df_exp['m'] = df_exp['date'].dt.to_period('M').astype(str)
        ex = df_exp.groupby('m')['amount'].sum().reset_index()
        fig_trend.add_trace(go.Scatter(x=ex['m'], y=ex['amount'], name='Расходы (Факт)', line=dict(color='#e74c3c', width=3)))
        
    st.plotly_chart(fig_trend, use_container_width=True)

with tab2:
    if not df_exp.empty and 'weight_g' in df_exp.columns:
        w_agg = df_exp.groupby('weight_g')['qty'].sum().reset_index()
        w_agg['label'] = w_agg['weight_g'].astype(str) + " г"
        fig_pie = px.pie(w_agg, values='qty', names='label', title='Списания/Промо по весу (шт)', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Нет данных по весу продукта")

with tab3:
    if not df_exp.empty:
        m_agg = df_exp.groupby(['manager', 'category'])['amount'].sum().reset_index().sort_values('amount', ascending=False)
        fig_bar = px.bar(m_agg, x='manager', y='amount', color='category', title='Топ расходов по менеджерам')

        st.plotly_chart(fig_bar, use_container_width=True)
