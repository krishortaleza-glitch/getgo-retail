import io
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="GetGo – Retail",
    layout="wide",
)

st.title("GetGo – Retail")

def read_uploaded_file(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    """Read CSV or Excel uploads into a DataFrame."""
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        return pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)

    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, dtype=str).fillna("")

    raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def get_column_by_position(df: pd.DataFrame, position: int, label: str) -> pd.Series:
    """Return a column using a zero-based positional index."""
    if position >= len(df.columns):
        raise ValueError(
            f"{label} does not contain the required column at position {position + 1}."
        )
    return df.iloc[:, position].astype(str)


def normalize_key_part(series: pd.Series) -> pd.Series:
    """Normalize key parts without changing their actual output columns."""
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def build_direct_key(first: pd.Series, second: pd.Series) -> pd.Series:
    """Concatenate key components directly, with no separator."""
    return normalize_key_part(first) + normalize_key_part(second)


def parse_numeric(series: pd.Series) -> pd.Series:
    """Convert a string series to numeric values where possible."""
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(",", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


st.subheader("Upload files")

retail_upload = st.file_uploader(
    "1. Retail File",
    type=["csv", "xlsx", "xls"],
    key="retail_file",
)

raw_cost_upload = st.file_uploader(
    "2. Raw Vendor Store Cost",
    type=["csv", "xlsx", "xls"],
    key="raw_cost_file",
)

if retail_upload and raw_cost_upload:
    try:
        retail_df = read_uploaded_file(retail_upload)
        raw_df = read_uploaded_file(raw_cost_upload)

        st.write("### File preview")
        preview_col1, preview_col2 = st.columns(2)

        with preview_col1:
            st.write("**Retail File**")
            st.dataframe(retail_df.head(5), use_container_width=True)

        with preview_col2:
            st.write("**Raw Vendor Store Cost**")
            st.dataframe(raw_df.head(5), use_container_width=True)

        if st.button("Process Retail File", type="primary"):
            try:
                # Retail lookup key: Column C + Column E
                retail_key = build_direct_key(
                    get_column_by_position(retail_df, 2, "Retail File"),
                    get_column_by_position(retail_df, 4, "Retail File"),
                )

                # Raw lookup key: Column A + Column C
                raw_key = build_direct_key(
                    get_column_by_position(raw_df, 0, "Raw Vendor Store Cost"),
                    get_column_by_position(raw_df, 2, "Raw Vendor Store Cost"),
                )

                # Raw condition: Column L >= 1
                raw_condition = parse_numeric(
                    get_column_by_position(raw_df, 11, "Raw Vendor Store Cost")
                ).ge(1)

                # Raw value to populate Retail Column Q: Column N
                raw_end_date = get_column_by_position(
                    raw_df, 13, "Raw Vendor Store Cost"
                )

                raw_lookup = pd.DataFrame(
                    {
                        "_lookup_key": raw_key,
                        "_eligible": raw_condition,
                        "_value": raw_end_date,
                    }
                )

                # Keep the first occurrence for duplicate raw lookup keys.
                raw_lookup = raw_lookup.drop_duplicates(
                    subset="_lookup_key",
                    keep="first",
                ).set_index("_lookup_key")

                output_df = retail_df.copy()

                # Retail Column Q is position 17 (zero-based index 16).
                if len(output_df.columns) <= 16:
                    raise ValueError(
                        "Retail File does not contain Column Q, so the output cannot be created."
                    )

                q_column_name = output_df.columns[16]

                matched = retail_key.map(raw_lookup["_eligible"])
                matched_value = retail_key.map(raw_lookup["_value"])

                # Populate Q only when Raw Column L >= 1.
                output_df.iloc[:, 16] = matched_value.where(matched.eq(True), "")

                # Ensure unmatched keys and ineligible rows are blank.
                output_df.iloc[:, 16] = output_df.iloc[:, 16].fillna("").astype(str)

                matched_count = int(matched.notna().sum())
                populated_count = int((output_df.iloc[:, 16] != "").sum())

                st.success("Retail File processed successfully.")

                metric1, metric2, metric3 = st.columns(3)
                metric1.metric("Retail rows", len(output_df))
                metric2.metric("Matched lookup keys", matched_count)
                metric3.metric("Column Q populated", populated_count)

                st.write(f"**Updated output column:** {q_column_name} (Column Q)")
                st.dataframe(output_df.head(20), use_container_width=True)

                csv_bytes = output_df.to_csv(index=False).encode("utf-8-sig")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                st.download_button(
                    label="Download Retail File",
                    data=csv_bytes,
                    file_name=f"GetGo_Retail_Output_{timestamp}.csv",
                    mime="text/csv",
                )

            except Exception as process_error:
                st.error(f"Processing error: {process_error}")

    except Exception as read_error:
        st.error(f"File reading error: {read_error}")
else:
    st.info("Upload both files to begin.")
