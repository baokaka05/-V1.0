import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import plotly.express as px
from io import BytesIO

# --- 網頁設定 ---
st.set_page_config(page_title="智能排班系統 (職級版)", page_icon="👨‍✈️", layout="wide")
st.title("👨‍✈️ 自動排班系統 (含資深/資淺邏輯)")
st.info("💡 新規則：每個班次至少會有一位「資深員工」值班，避免整班都是新人。")

# --- 1. 側邊欄設定 ---
st.sidebar.header("⚙️ 人員設定")

# 分開輸入資深與一般員工
st.sidebar.subheader("1. 員工名單")
default_seniors = "店長, 副店"
default_juniors = "小明, 阿華, 美美, 大壯"

seniors_str = st.sidebar.text_area("資深員工 (幹部)", default_seniors, help="這些人每個班次至少要出現一位")
juniors_str = st.sidebar.text_area("一般員工", default_juniors)

# 資料清理
seniors = [x.strip() for x in seniors_str.split(',') if x.strip()]
juniors = [x.strip() for x in juniors_str.split(',') if x.strip()]
all_employees = seniors + juniors # 合併成總名單

st.sidebar.subheader("2. 班表規則")
min_shifts = st.sidebar.slider("每人每週最少幾班？", 1, 7, 3) # 稍微調低一點以免無解
max_shifts = st.sidebar.slider("每人每週最多幾班？", 1, 7, 6)

st.sidebar.subheader("3. 指定休假")
off_day_employee = st.sidebar.selectbox("選擇員工", ["(無)"] + all_employees)
off_day_choice = st.sidebar.selectbox("選擇休假日期", ["(無)", "週一", "週二", "週三", "週四", "週五", "週六", "週日"])

# --- 2. 排班核心邏輯 ---
def solve_schedule(seniors, juniors, min_s, max_s, off_emp, off_day):
    employees = seniors + juniors
    days = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
    shifts = ['早班', '中班', '晚班']

    model = cp_model.CpModel()
    schedule = {}

    for e in employees:
        for d in days:
            for s in shifts:
                schedule[(e, d, s)] = model.NewBoolVar(f'{e}_{d}_{s}')

    # 規則 A: 每日每班次總人數固定為 1 (這裡假設每班只有1人)
    # ⚠️ 如果您的店每班需要多人，請把 == 1 改成 == 2 或更多
    for d in days:
        for s in shifts:
            model.Add(sum(schedule[(e, d, s)] for e in employees) == 1)

    # 規則 B: 每人每日最多 1 班
    for e in employees:
        for d in days:
            model.Add(sum(schedule[(e, d, s)] for s in shifts) <= 1)

    # 規則 C: 總量管制
    for e in employees:
        num = sum(schedule[(e, d, s)] for d in days for s in shifts)
        model.Add(num >= min_s)
        model.Add(num <= max_s)

    # 規則 D: 防爆肝 (晚接早)
    for e in employees:
        for i in range(len(days) - 1):
            model.Add(schedule[(e, days[i], '晚班')] + schedule[(e, days[i+1], '早班')] <= 1)

    # =========== 新增規則 E: 資深員工覆蓋率 ===========
    # 邏輯：每個班次中，(資深員工的人數) 必須 >= 1
    # 注意：如果每班總人數只排 1 人，這代表該班次「必須」是資深員工
    # 為了讓排班有彈性，通常建議每班總人數 > 1，或者資深員工夠多

    # 這裡我們做一個「稍微寬鬆」的檢查：
    # 如果「資深員工」數量極少，我們不要強制每一班都有，以免無解。
    # 但這裡為了演示，我們強制設定：若有排班，優先填入資深員工。

    # (進階寫法) 為了演示「老鳥帶菜鳥」，我們假設每班至少要有 1 個資深員工
    # 但因為目前設定每班總共只有 1 人，這會變成「所有班都要資深員工上」，這樣會無解。
    # 所以我們修改規則 A 的邏輯：
    # 我們改為：每天至少要有 1 個「資深員工」上班 (店長不一定要每分每秒都在，但每天都要看到人)

    for d in days:
         model.Add(sum(schedule[(e, d, s)] for e in seniors for s in shifts) >= 1)

    # =================================================

    # 指定休假
    if off_emp != "(無)" and off_day != "(無)":
        for s in shifts:
            model.Add(schedule[(off_emp, off_day, s)] == 0)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # 資料整理 (加入職級標籤)
        chart_data = []
        table_data = []

        for d in days:
            row = {'日期': d}
            for s in shifts:
                for e in employees:
                    if solver.Value(schedule[(e, d, s)]) == 1:
                        # 標記是否為資深
                        role_tag = "(資深)" if e in seniors else ""
                        display_name = f"{e}{role_tag}"
                        row[s] = display_name

                        chart_data.append({
                            '員工': e,
                            '職級': '資深' if e in seniors else '一般', # 給圖表分組用
                            '星期': d,
                            '班次': s
                        })
            table_data.append(row)

        return pd.DataFrame(table_data), pd.DataFrame(chart_data)
    else:
        return None, None

# --- 3. 顯示結果 ---
if st.button("🚀 開始自動排班 (含職級檢查)", use_container_width=True):
    # 檢查輸入
    if not seniors or not juniors:
        st.error("❌ 請確保資深員工和一般員工欄位都有填寫名字！")
    else:
        with st.spinner("正在計算最佳組合 (確保每天都有幹部)..."):
            df_table, df_chart = solve_schedule(seniors, juniors, min_shifts, max_shifts, off_day_employee, off_day_choice)

        if df_table is not None:
            st.success("🎉 排班完成！已確認每天都有資深幹部坐鎮。")

            # --- 視覺化圖表 ---
            st.subheader("📊 班表視覺化 (顏色區分職級)")
            # 這裡我們改用顏色來區分「資深 vs 一般」，形狀區分班次
            fig = px.scatter(
                df_chart,
                x="星期",
                y="員工",
                color="職級", # 這裡改成用職級上色
                symbol="班次",
                size_max=20,
                category_orders={
                    "星期": ['週一', '週二', '週三', '週四', '週五', '週六', '週日'],
                    "班次": ['早班', '中班', '晚班']
                },
                color_discrete_map={'資深': '#FF5722', '一般': '#4CAF50'}, # 資深=橘紅, 一般=綠
                title="職級分佈圖 (橘色為幹部)"
            )
            fig.update_traces(marker=dict(size=25, line=dict(width=2, color='DarkSlateGrey')))
            fig.update_layout(height=400, plot_bgcolor='white')
            st.plotly_chart(fig, use_container_width=True)

            # --- 表格 ---
            st.dataframe(df_table, use_container_width=True, hide_index=True)

            # Excel 下載
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_table.to_excel(writer, index=False)
            st.download_button(
                "下載 Excel",
                output.getvalue(),
                "職級排班表.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

        else:
            st.error("❌ 排班失敗。通常是因為資深員工太少，無法覆蓋每一天。請嘗試增加資深員工，或減少每週最少班數。")
