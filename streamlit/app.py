import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------
# 1. Cấu hình Trang Web
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dashboard Bán Hàng E-Commerce",
    page_icon="📊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. Tạo kết nối CSDL & Caching dữ liệu
# ---------------------------------------------------------
@st.cache_resource
def init_connection():
    return mysql.connector.connect(
        host=st.secrets["mysql"]["host"],
        port=st.secrets["mysql"]["port"],
        database=st.secrets["mysql"]["database"],
        user=st.secrets["mysql"]["username"],
        password=st.secrets["mysql"]["password"]
    )

conn = init_connection()

@st.cache_data(ttl=600)
def run_query(query, params=None):
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute(query, params or ())
        result = cursor.fetchall()
    return pd.DataFrame(result)

# ---------------------------------------------------------
# 3. Giao diện Sidebar - Các Bộ Lọc (Filters)
# ---------------------------------------------------------
st.sidebar.header("🔍 Bộ Lọc Dữ Liệu")

try:
    categories_df = run_query("SELECT DISTINCT category_name FROM Categories")
    category_list = ["Tất cả"] + categories_df['category_name'].tolist()
except Exception as e:
    st.sidebar.error(f"Lỗi tải danh mục: {e}")
    category_list = ["Tất cả"]

try:
    cities_df = run_query("SELECT DISTINCT city FROM Customers WHERE city IS NOT NULL")
    city_list = ["Tất cả"] + cities_df['city'].tolist()
except Exception as e:
    city_list = ["Tất cả"]

selected_category = st.sidebar.selectbox("Chọn Danh mục Sản phẩm:", category_list)
selected_city = st.sidebar.selectbox("Chọn Thành phố:", city_list)

status_list = ["Tất cả", "Completed", "Pending", "Cancelled"]
selected_status = st.sidebar.selectbox("Trạng thái Đơn hàng:", status_list)

try:
    date_df = run_query("SELECT MIN(order_date) as min_date, MAX(order_date) as max_date FROM Orders")
    min_d = date_df['min_date'].iloc[0]
    max_d = date_df['max_date'].iloc[0]
    if pd.isna(min_d) or pd.isna(max_d):
        min_d, max_d = pd.to_datetime("2023-01-01").date(), pd.to_datetime("2026-12-31").date()
    else:
        min_d = pd.to_datetime(min_d).date()
        max_d = pd.to_datetime(max_d).date()
except:
    min_d, max_d = pd.to_datetime("2023-01-01").date(), pd.to_datetime("2026-12-31").date()

date_range = st.sidebar.date_input("Khoảng thời gian đặt hàng:", [min_d, max_d])

# ---------------------------------------------------------
# 4. Truy vấn Dữ liệu theo Bộ Lọc & Xử lý
# ---------------------------------------------------------
st.title("📊 Báo Cáo Doanh Thu & Hành Vi Mua Hàng E-Commerce")

base_sql = """
    SELECT 
        o.order_id,
        o.order_date,
        o.status,
        cu.city,
        c.category_name,
        p.product_name,
        od.quantity,
        (od.quantity * od.unit_price) AS total_price
    FROM Orders o
    JOIN OrderDetails od ON o.order_id = od.order_id
    JOIN Products p ON od.product_id = p.product_id
    JOIN Categories c ON p.category_id = c.category_id
    JOIN Customers cu ON o.customer_id = cu.customer_id
    WHERE 1=1
"""

query_params = []

if selected_status != "Tất cả":
    base_sql += " AND o.status = %s"
    query_params.append(selected_status)

if selected_category != "Tất cả":
    base_sql += " AND c.category_name = %s"
    query_params.append(selected_category)

if selected_city != "Tất cả":
    base_sql += " AND cu.city = %s"
    query_params.append(selected_city)

if len(date_range) == 2:
    base_sql += " AND o.order_date BETWEEN %s AND %s"
    query_params.append(date_range[0])
    query_params.append(date_range[1])

df = run_query(base_sql, tuple(query_params) if query_params else None)

if not df.empty and 'order_date' in df.columns:
    df['order_date'] = pd.to_datetime(df['order_date']).dt.date

# ---------------------------------------------------------
# 5. Hiển thị Các Chỉ Số Quan Trọng (KPI Metrics)
# ---------------------------------------------------------
if not df.empty:
    col1, col2, col3, col4 = st.columns(4)
    
    total_revenue = df['total_price'].sum()
    total_orders = df['order_id'].nunique()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    total_products = df['quantity'].sum()

    col1.metric("Tổng Doanh Thu", f"{total_revenue:,.0f} USD")
    col2.metric("Tổng Số Đơn Hàng", f"{total_orders:,} đơn")
    col3.metric("Giá Trị TB/Đơn (AOV)", f"{avg_order_value:,.2f} USD")
    col4.metric("Tổng Sản Phẩm Bán", f"{total_products:,} sản phẩm")

    st.markdown("---")

    # ---------------------------------------------------------
    # 6. Biểu đồ Trực quan hóa (Plotly Chart)
    # ---------------------------------------------------------
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("📈 Doanh Thu Theo Ngày")
        df_daily = df.groupby('order_date')['total_price'].sum().reset_index()
        fig_line = px.line(
            df_daily, x='order_date', y='total_price', markers=True,
            labels={'order_date': 'Ngày', 'total_price': 'Doanh Thu ($)'}
        )
        st.plotly_chart(fig_line, use_container_width=True)

    with col_chart2:
        st.subheader("🔥 Top 5 Sản Phẩm Bán Chạy")
        df_product = df.groupby('product_name')['quantity'].sum().reset_index()
        df_top5 = df_product.nlargest(5, 'quantity').sort_values('quantity', ascending=True)
        fig_bar = px.bar(
            df_top5, x='quantity', y='product_name', orientation='h',
            labels={'quantity': 'Số Lượng Bán', 'product_name': 'Sản Phẩm'}
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ---------------------------------------------------------
    # 7. Bảng Dữ liệu Chi tiết & Tải xuống CSV
    # ---------------------------------------------------------
    st.markdown("---")
    with st.expander("📄 Xem Bảng Dữ Liệu Chi Tiết & Tải Xuống"):
        st.dataframe(df, use_container_width=True)
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Tải xuống dữ liệu (CSV)",
            data=csv_data,
            file_name="ecommerce_sales_data.csv",
            mime="text/csv"
        )
else:
    st.warning("⚠️ Không tìm thấy dữ liệu phù hợp với bộ lọc hiện tại!")