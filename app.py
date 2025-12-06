import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import plotly.express as px
from io import BytesIO
import calendar  # 新增：日曆模組

# --- 網頁設定 ---
st.set_page_config(page_title="智能排班系統 V2", page_icon="🗓️", layout="wide")
st.title("🗓️ 自動排班系統 V2 (指定月份 + 多人休假)")

# --- 1. 側邊欄：參數設定 ---
st.sidebar.header("1. 日期與人員")

# A. 設定年份與月份
col_y, col_m = st.sidebar.columns(2)
year = col_y.number_input("年份", 2024, 2030, 2024)
month = col_m.number_input("月份", 1, 12, 12)

# 自動計算該月有幾天
_, num_days_in_month = calendar.monthrange(year, month)
st.sidebar.success(f"📅 {year}年{month}月 共有 {num_days_in_month} 天")

# B. 員工設定
st.sidebar.subheader("員工名單")
default_seniors = "店長, 副店"
default_juniors = "小明, 阿華, 美美, 大壯"
seniors = [x.strip() for x in st.sidebar.text_area("資深幹部", default_seniors).split(',') if x.strip()]
juniors = [x.strip() for x in st.sidebar.text_area("一般員工", default_juniors).split(',') if x.strip()]

# C. 規則設定
st.sidebar.subheader("2. 排班規則")
# 自動計算建議的班數區間
total_shifts_needed = num_days_in_month * 1 # 每天1班 (假設)
total_staff = len(seniors) + len(juniors)
if total_staff > 0:
    avg_shifts = total_shifts_needed / total_staff
    st.sidebar.info(f"💡 數學提示：每人平均約需上 {avg_shifts:.1f} 班")

min_shifts = st.sidebar.number_input("每人每月最少班數", 1, 31, int(avg_shifts - 2))
max_shifts = st.sidebar.number_input("每人每月最多班數", 1, 31, int(avg_shifts + 3))

# D. 休假設定 (升級版)
st.sidebar.subheader("3. 指定休假 (多人多天)")
st.sidebar.caption("格式範例：\n小明: 5, 12, 20\n店長: 1, 2")
leave_requests_str = st.sidebar.text_area("請輸入休假需求 (一行一位)", "小明: 5, 6\n副店: 10, 20")

# --- 2. 資料處理函式 ---

def parse_leaves(leave_str):
    """解析文字框裡的休假需求"""
    leaves = {}
    if not leave_str.strip():
        return leaves
    
    lines = leave_str.split('\n')
    for line in lines:
        if ':' in line:
            name, days_str = line.split(':', 1)
            name = name.strip()
            # 處理全形逗號與空格
            days_str = days_str.replace('，', ',')
            try:
                days = [int(d.strip()) for d in days_str.split(',') if d.strip().isdigit()]
                leaves[name] = days
            except:
                pass # 格式錯誤就跳過
    return leaves

def get_day_label(y, m, d):
    """回傳格式：1 (週一)"""
    weekday_idx = calendar.weekday(y, m, d)
    weekdays_zh = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
    return f"{d}號 ({weekdays_zh[weekday_idx]})"

# --- 3. 排班核心邏輯 ---
def solve_schedule(year, month, num_days, seniors, juniors, min_s, max_s, leave_dict):
    employees = seniors + juniors
    days = list(range(1, num_days + 1)) # 產生 1 到 30/31 的數字列表
    shifts = ['早班', '中班', '晚班']
    
    model = cp_model.CpModel()
    schedule = {}

    # 建立變數
    for e in employees:
        for d in days:
            for s in shifts:
                schedule[(e, d, s)] = model.NewBoolVar(f'{e}_{d}_{s}')

    # 規則 A: 每日每班次 1 人 (若您店裡需要多人，請改這裡)
    for d in days:
        for s in shifts:
            model.Add(sum(schedule[(e, d, s)] for e in employees) == 1)

    # 規則 B: 每人每日最多 1 班
    for e in employees:
        for d in days:
            model.Add(sum(schedule[(e, d, s)] for s in shifts) <= 1)

    # 規則 C: 總量管制 (月總工時)
    for e in employees:
        num = sum(schedule[(e, d, s)] for d in days for s in shifts)
        model.Add(num >= min_s)
        model.Add(num <= max_s)

    # 規則 D: 防爆肝 (晚接早)
    for e in employees:
        for i in range(len(days) - 1):
            today = days[i]
            tomorrow = days[i+1]
            model.Add(schedule[(e, today, '晚班')] + schedule[(e, tomorrow, '早班')] <= 1)
    
    # 規則 E: 資深幹部每日至少出現一位
    for d in days:
         model.Add(sum(schedule[(e, d, s)] for e in seniors for s in shifts) >= 1)

    # 規則 F: 指定休假 (解析後的名單)
    for name, dates in leave_dict.items():
        if name in employees:
            for d in dates:
                if 1 <= d <= num_days: # 確保日期在該月範圍內
                    for s in shifts:
                        model.Add(schedule[(name, d, s)] == 0)

    # 求解
    solver = cp_model.CpSolver()
    # 設定運算時間上限 (避免算太久卡住)
    solver.parameters.max_time_in_seconds = 10
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        chart_data = []
        table_data = []
        
        for d in days:
            label = get_day_label(year, month, d)
            row = {'日期': label}
            for s in shifts:
                for e in employees:
                    if solver.Value(schedule[(e, d, s)]) == 1:
                        # 標記是否為資深
                        role_tag = "(資深)" if e in seniors else ""
                        row[s] = f"{e}{role_tag}"
                        
                        chart_data.append({
                            '員工': e,
                            '職級': '資深' if e in seniors else '一般',
                            '日期': d, # 用數字給圖表排序比較準
                            '日期標籤': label,
                            '班次': s
                        })
            table_data.append(row)
            
        return pd.DataFrame(table_data), pd.DataFrame(chart_data)
    else:
        return None, None

# --- 4. 介面互動 ---
if st.button("🚀 開始排班", use_container_width=True):
    # 解析休假輸入
    leaves = parse_leaves(leave_requests_str)
    
    with st.spinner("正在計算整月份的班表..."):
        df_table, df_chart = solve_schedule(
            year, month, num_days_in_month, 
            seniors, juniors, 
            min_shifts, max_shifts, 
            leaves
        )
        
    if df_table is not None:
        st.success("🎉 排班完成！")
        
        # 顯示休假確認 (讓使用者安心)
        if leaves:
            st.info(f"已排除以下指定休假：{leaves}")

        # 圖表
        st.subheader("📊 月份班表概覽")
        fig = px.scatter(
            df_chart, 
            x="日期", # 這裡改成 1,2,3...31
            y="員工", 
            color="職級", 
            symbol="班次", 
            hover_data=["日期標籤"],
            category_orders={"班次": ['早班', '中班', '晚班']},
            color_discrete_map={'資深': '#FF5722', '一般': '#4CAF50'},
            height=500
        )
        fig.update_traces(marker=dict(size=15))
        fig.update_layout(xaxis=dict(tickmode='linear', dtick=1)) # 強制顯示每一天的刻度
        st.plotly_chart(fig, use_container_width=True)

        # 表格
        st.subheader("📋 詳細班表")
        st.dataframe(df_table, use_container_width=True, hide_index=True)
        
        # 下載
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_table.to_excel(writer, index=False)
        st.download_button("下載 Excel", output.getvalue(), f"{year}年{month}月班表.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    else:
        st.error("❌ 排班失敗。可能原因：休假的人太多，或是每人最少班數設太高，導致無法填滿每天的班次。")
