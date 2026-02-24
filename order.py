import streamlit as st
import pandas as pd
import openpyxl  # Explicitly included

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="OFT AI Backlog Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CUSTOM STYLING
st.markdown(
    """
<style>
.main { background-color: #f5f7fb; }
.block-container {
    padding-top: 2rem;
    max-width: 1000px;
    margin: auto;
}
.header-box {
    background: #228B22;
    padding: 30px;
    border-radius: 15px;
    text-align: center;
    color: white;
    font-size: 22px;
    font-weight: bold;
    margin-bottom: 25px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="header-box">OFT Backlog & Dispatch Assistant</div>',
    unsafe_allow_html=True,
)

# -------------------------------------------------
# SESSION STATE
# -------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None

# -------------------------------------------------
# RESET CHAT BUTTON
# -------------------------------------------------
col1, col2 = st.columns([8, 1])
with col2:
    if st.button("Reset Chat"):
        st.session_state.messages = []
        st.rerun()

# -------------------------------------------------
# FILE UPLOAD
# -------------------------------------------------
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file is None:
    st.info("Upload Excel file to start chatting.")
    st.stop()


# -------------------------------------------------
# DATA LOADING
# -------------------------------------------------
@st.cache_data(show_spinner=True)
def load_data(file):

    df_raw = pd.read_excel(
        file,
        engine="openpyxl",
        dtype={
            "SOLDTO": "string",
            "Type": "string",
            "Incoterm": "string",
            "Status Summary": "string",
            "City": "string",  # ADDED
        },
    )

    df_raw.columns = df_raw.columns.str.strip()

    required_cols = [
        "SOLDTO",
        "Type",
        "Incoterm",
        "Status Summary",
        "ORDERED_QUANTITY",
        "City",  # ADDED
    ]

    missing = [c for c in required_cols if c not in df_raw.columns]

    if missing:
        return None, missing

    df_raw["SOLDTO"] = df_raw["SOLDTO"].str.strip()
    df_raw["Type"] = df_raw["Type"].str.strip()
    df_raw["Incoterm"] = df_raw["Incoterm"].str.strip()
    df_raw["City"] = df_raw["City"].str.strip()  # ADDED
    df_raw["Status Summary"] = df_raw["Status Summary"].str.strip().str.lower()

    df_raw["ORDERED_QUANTITY"] = pd.to_numeric(
        df_raw["ORDERED_QUANTITY"], errors="coerce"
    ).fillna(0)

    # ADDED City to grouping
    group_cols = ["SOLDTO", "City", "Type", "Incoterm"]

    backlog = (
        df_raw[df_raw["Status Summary"] == "backlog"]
        .groupby(group_cols)["ORDERED_QUANTITY"]
        .sum()
        .reset_index()
        .rename(columns={"ORDERED_QUANTITY": "Backlog"})
    )

    mtd = (
        df_raw[df_raw["Status Summary"] == "dispatched"]
        .groupby(group_cols)["ORDERED_QUANTITY"]
        .sum()
        .reset_index()
        .rename(columns={"ORDERED_QUANTITY": "MTD"})
    )

    df = pd.merge(backlog, mtd, on=group_cols, how="outer").fillna(0)

    customers = sorted(df["SOLDTO"].unique())

    return df, customers


df, customers_list = load_data(uploaded_file)

if df is None:
    st.error(f"Missing required columns: {customers_list}")
    st.stop()

# -------------------------------------------------
# CUSTOMER SEARCH + CLEAR BUTTON
# -------------------------------------------------
col_search, col_clear = st.columns([4, 1])

with col_search:
    st.session_state.selected_customer = st.selectbox(
        "Search & Select Customer",
        customers_list,
        index=None,
        placeholder="Search customer...",
    )

with col_clear:
    if st.button("Clear Search"):
        st.session_state.selected_customer = None
        st.session_state.messages = []
        st.rerun()

question_type = st.selectbox(
    "What do you want to know?", ["Backlog", "MTD", "Backlog & MTD"]
)

# -------------------------------------------------
# DISPLAY CHAT HISTORY
# -------------------------------------------------
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# -------------------------------------------------
# ASK BUTTON
# -------------------------------------------------
if st.button("Ask"):

    if not st.session_state.selected_customer:
        st.warning("Please select a customer.")
        st.stop()

    selected_customer = st.session_state.selected_customer

    prompt = f"{question_type} for {selected_customer}"
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    customer_df = df[df["SOLDTO"].str.lower() == selected_customer.lower()]

    if customer_df.empty:
        response = "❌ ERROR: Customer not present in dataset."
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)
        st.stop()

    # ADDED City into breakdown
    breakdown = customer_df.groupby(["City", "Type", "Incoterm"], as_index=False).agg(
        {"Backlog": "sum", "MTD": "sum"}
    )

    total_backlog = breakdown["Backlog"].sum()
    total_mtd = breakdown["MTD"].sum()

    parts = []

    if question_type in ["Backlog", "Backlog & MTD"]:
        backlog_text = f"## {selected_customer} - Backlog Summary\n"
        backlog_text += f"**Total Backlog:** {total_backlog:,.2f}\n\n"
        backlog_text += "### Backlog by City, Type and Incoterm\n"

        for _, row in breakdown.iterrows():
            backlog_text += f"- {row['City']} | {row['Type']} | {row['Incoterm']} → {row['Backlog']:,.2f}\n"

        parts.append(backlog_text)

    if question_type in ["MTD", "Backlog & MTD"]:
        mtd_text = f"## {selected_customer} - MTD Summary\n"
        mtd_text += f"**Total MTD:** {total_mtd:,.2f}\n\n"
        mtd_text += "### MTD by City, Type and Incoterm\n"

        for _, row in breakdown.iterrows():
            mtd_text += f"- {row['City']} | {row['Type']} | {row['Incoterm']} → {row['MTD']:,.2f}\n"

        parts.append(mtd_text)

    response = "\n\n".join(parts)

    st.session_state.messages.append({"role": "assistant", "content": response})

    with st.chat_message("assistant"):
        st.markdown(response)
