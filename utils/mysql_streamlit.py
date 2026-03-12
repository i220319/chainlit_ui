import streamlit as st

from mysql_client import MySQLClient


def load_databases(client: MySQLClient):
    return client.list_databases()


def load_tables(client: MySQLClient, database: str):
    return client.list_tables(database)


def load_columns(client: MySQLClient, database: str, table: str):
    cur = client.cursor()
    cur.execute(f"SHOW COLUMNS FROM `{database}`.`{table}`")
    return [row[0] for row in cur.fetchall()]


def load_rows(client: MySQLClient, database: str, table: str, limit: int, offset: int):
    cur = client.cursor()
    cur.execute(
        f"SELECT * FROM `{database}`.`{table}` LIMIT %s OFFSET %s",
        (limit, offset),
    )
    rows = cur.fetchall()
    col_names = [desc[0] for desc in cur.description] if cur.description else []
    return [dict(zip(col_names, row)) for row in rows]

def load_primary_keys(client: MySQLClient, database: str, table: str):
    cur = client.cursor()
    cur.execute(f"SHOW KEYS FROM `{database}`.`{table}` WHERE Key_name = 'PRIMARY'")
    return [row[4] for row in cur.fetchall()]

st.title("MySQL Browser")

with MySQLClient() as client:
    try:
        databases = load_databases(client)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    database = st.selectbox("Database", databases)
    if database:
        try:
            tables = load_tables(client, database)
        except Exception as exc:
            st.error(str(exc))
            st.stop()

        table = st.selectbox("Table", tables)
        if table:
            try:
                with st.expander("Delete table", expanded=False):
                    confirm_name = st.text_input("Type table name to confirm", value="")
                    confirm = st.checkbox("I understand this will delete the table")
                    if st.button("Delete table", type="primary", use_container_width=True):
                        if confirm_name == table and confirm:
                            client.execute(
                                f"DROP TABLE `{database}`.`{table}`",
                                commit=True,
                            )
                            st.success(f"Deleted table {table}")
                            st.stop()
                        else:
                            st.error("Confirmation mismatch")

                columns = load_columns(client, database, table)
                st.table([{"column": name} for name in columns])

                page_size = st.slider("Rows per page", min_value=1, max_value=500, value=50)
                page = st.number_input("Page", min_value=1, value=1, step=1)
                offset = (page - 1) * page_size
                rows = load_rows(client, database, table, page_size, offset)
                st.dataframe(rows)
                with st.expander("Delete rows", expanded=False):
                    try:
                        pk_cols = load_primary_keys(client, database, table)
                    except Exception:
                        pk_cols = []
                    confirm = st.checkbox("I understand row deletion is irreversible", key=f"confirm_row_delete_{database}_{table}")
                    for i, row in enumerate(rows):
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            st.json(row)
                        with c2:
                            if st.button("Delete", key=f"del_{database}_{table}_{offset}_{i}") and confirm:
                                if pk_cols:
                                    where_clause = " AND ".join([f"`{k}`=%s" for k in pk_cols])
                                    params = tuple(row.get(k) for k in pk_cols)
                                else:
                                    keys = list(row.keys())
                                    where_clause = " AND ".join([f"`{k}` <=> %s" for k in keys])
                                    params = tuple(row.get(k) for k in keys)
                                client.execute(
                                    f"DELETE FROM `{database}`.`{table}` WHERE {where_clause} LIMIT 1",
                                    params=params,
                                    commit=True,
                                )
                                st.success("Row deleted")
                                st.rerun()
            except Exception as exc:
                st.error(str(exc))
