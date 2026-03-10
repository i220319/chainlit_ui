import json

try:
    import pymysql
except ImportError:
    pymysql = None
try:
    from utils.config import load_config
except ImportError:
    from config import load_config

class MySQLClient:
    def __init__(
        self,
        host=None,
        port=None,
        user=None,
        password=None,
        database=None,
        table=None,
        analysis_table=None,
        access_table=None,
        charset="utf8mb4",
        autocommit=False,
    ):
        config = load_config()
        self.host = host or config.mysql_host
        self.port = int(port or config.mysql_port)
        self.user = user or config.mysql_user
        self.password = password or config.mysql_password
        self.database = database or config.mysql_database
        self.table = table or config.mysql_table
        self.analysis_table = analysis_table or config.mysql_analysis_table
        self.access_table = access_table or config.mysql_access_table
        self.charset = charset
        self.autocommit = autocommit
        self._conn = None

    def _ensure_ready(self):
        if pymysql is None:
            raise ImportError("pymysql is required. Install it with pip.")
        missing = []
        if not self.host:
            missing.append("MYSQL_HOST")
        if not self.user:
            missing.append("MYSQL_USER")
        if not self.password:
            missing.append("MYSQL_PASSWORD")
        if missing:
            raise ValueError(f"Missing config values: {', '.join(missing)}")

    def connect(self):
        self._ensure_ready()
        if self._conn and getattr(self._conn, "open", False):
            return self._conn
        kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "charset": self.charset,
            "autocommit": self.autocommit,
        }
        if self.database:
            kwargs["database"] = self.database
        self._conn = pymysql.connect(**kwargs)
        return self._conn

    def cursor(self):
        return self.connect().cursor()

    def execute(self, sql, params=None, commit=False):
        cur = self.cursor()
        cur.execute(sql, params or ())
        if commit:
            self._conn.commit()
        return cur.rowcount

    def fetchall(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params or ())
        return cur.fetchall()

    def fetchone(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params or ())
        return cur.fetchone()

    def list_tables(self, database=None):
        target_database = database or self.database
        if not target_database:
            raise ValueError("Missing config values: MYSQL_DATABASE")
        cur = self.cursor()
        cur.execute(f"SHOW TABLES FROM `{target_database}`")
        return [row[0] for row in cur.fetchall()]

    def list_databases(self):
        cur = self.cursor()
        cur.execute("SHOW DATABASES")
        return [row[0] for row in cur.fetchall()]

    def create_database(self, database):
        if not database:
            raise ValueError("Database name is required")
        cur = self.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
        self._conn.commit()

    def create_feedback_table(self, database, table):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
                feedback_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                ip VARCHAR(45),
                feedback ENUM('like','dislike') NOT NULL,
                feedback_suggestion TEXT,
                extra JSON
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        self._conn.commit()

    def create_analysis_table(self, database, table):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
                analysis_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                ip VARCHAR(45),
                input_text TEXT,
                result_body LONGTEXT,
                extra JSON
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        self._conn.commit()

    def create_access_table(self, database, table):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS `{database}`.`{table}` (
                access_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                create_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ip VARCHAR(45),
                extra JSON
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        self._conn.commit()

    def init_feedback_storage(
        self,
        database=None,
        table=None,
    ):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        target_database = database
        target_table = table
        self.create_database(target_database)
        self.create_feedback_table(target_database, target_table)
        self.database = target_database
        self.table = target_table

    def init_analysis_storage(
        self,
        database=None,
        table=None,
    ):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        target_database = database
        target_table = table
        self.create_database(target_database)
        self.create_analysis_table(target_database, target_table)
        self.database = target_database
        self.analysis_table = target_table

    def init_access_storage(
        self,
        database=None,
        table=None,
    ):
        if not database:
            raise ValueError("Database name is required")
        if not table:
            raise ValueError("Table name is required")
        target_database = database
        target_table = table
        self.create_database(target_database)
        self.create_access_table(target_database, target_table)
        self.database = target_database
        self.access_table = target_table

    def insert_feedback(
        self,
        feedback_value,
        suggestion=None,
        extra=None,
        ip=None,
        database=None,
        table=None,
    ):
        target_database = database or self.database
        target_table = table or self.table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        if feedback_value in {"up", "like"}:
            feedback = "like"
        elif feedback_value in {"down", "dislike"}:
            feedback = "dislike"
        else:
            raise ValueError("Invalid feedback value")

        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        cur = self.cursor()
        cur.execute(
            f"""
            INSERT INTO `{target_database}`.`{target_table}`
                (feedback, feedback_suggestion, extra, ip)
            VALUES (%s, %s, %s, %s)
            """,
            (feedback, suggestion, extra_json, ip),
        )
        self._conn.commit()
        self.database = target_database

    def insert_analysis_log(
        self,
        ip=None,
        input_text=None,
        result_body=None,
        extra=None,
        database=None,
        table=None,
    ):
        target_database = database or self.database
        target_table = table or self.analysis_table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        cur = self.cursor()
        cur.execute(
            f"""
            INSERT INTO `{target_database}`.`{target_table}`
                (ip, input_text, result_body, extra)
            VALUES (%s, %s, %s, %s)
            """,
            (ip, input_text, result_body, extra_json),
        )
        self._conn.commit()
        self.database = target_database

    def insert_access_log(
        self,
        ip=None,
        extra=None,
        database=None,
        table=None,
    ):
        target_database = database or self.database
        target_table = table or self.access_table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        cur = self.cursor()
        cur.execute(
            f"""
            INSERT INTO `{target_database}`.`{target_table}`
                (ip, extra)
            VALUES (%s, %s)
            """,
            (ip, extra_json),
        )
        self._conn.commit()
        self.database = target_database

    def update_analysis_log_add_comment(
        self,
        input_text,
        result_body,
        database=None,
        table=None,
    ):
        if not input_text or not result_body:
            return 0
        target_database = database or self.database
        target_table = table or self.analysis_table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            UPDATE `{target_database}`.`{target_table}`
            SET extra = JSON_SET(
                COALESCE(extra, JSON_OBJECT()),
                '$.add_comment_count',
                COALESCE(
                    CAST(JSON_UNQUOTE(JSON_EXTRACT(extra, '$.add_comment_count')) AS UNSIGNED),
                    0
                ) + 1
            )
            WHERE input_text = %s AND result_body = %s
            ORDER BY update_time DESC
            LIMIT 1
            """,
            (input_text, result_body),
        )
        self._conn.commit()
        return cur.rowcount

    def feedback_exists_by_analysis_result(
        self,
        analysis_result,
        database=None,
        table=None,
    ):
        if not analysis_result:
            return False
        target_database = database or self.database
        target_table = table or self.table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            SELECT 1 FROM `{target_database}`.`{target_table}`
            WHERE JSON_UNQUOTE(JSON_EXTRACT(extra, '$.source.analysis_result')) = %s
            LIMIT 1
            """,
            (analysis_result,),
        )
        return cur.fetchone() is not None

    def get_feedback_by_analysis_result(
        self,
        issue_key,
        analysis_result,
        database=None,
        table=None,
    ):
        if not issue_key or not analysis_result:
            return None
        target_database = database or self.database
        target_table = table or self.table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        cur = self.cursor()
        cur.execute(
            f"""
            SELECT feedback_id, feedback, feedback_suggestion, extra, ip
            FROM `{target_database}`.`{target_table}`
            WHERE JSON_UNQUOTE(JSON_EXTRACT(extra, '$.source.analysis_result')) = %s
              AND JSON_UNQUOTE(JSON_EXTRACT(extra, '$.source.issue_key')) = %s
            ORDER BY update_time DESC
            LIMIT 1
            """,
            (analysis_result, issue_key),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "feedback_id": row[0],
            "feedback": row[1],
            "feedback_suggestion": row[2],
            "extra": row[3],
            "ip": row[4],
        }

    def update_feedback(
        self,
        feedback_id,
        feedback_value,
        suggestion=None,
        extra=None,
        ip=None,
        database=None,
        table=None,
    ):
        target_database = database or self.database
        target_table = table or self.table
        if not target_database:
            raise ValueError("Database name is required")
        if not target_table:
            raise ValueError("Table name is required")
        if feedback_value in {"up", "like"}:
            feedback = "like"
        elif feedback_value in {"down", "dislike"}:
            feedback = "dislike"
        else:
            raise ValueError("Invalid feedback value")
        extra_json = json.dumps(extra or {}, ensure_ascii=False)
        cur = self.cursor()
        cur.execute(
            f"""
            UPDATE `{target_database}`.`{target_table}`
            SET feedback = %s,
                feedback_suggestion = %s,
                extra = %s,
                ip = %s
            WHERE feedback_id = %s
            """,
            (feedback, suggestion, extra_json, ip, feedback_id),
        )
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

if __name__ == "__main__":
    mysql_client = MySQLClient()
    mysql_client.init_feedback_storage("5000agent_feedback", "used_feedback")
    mysql_client.connect()
    databases = mysql_client.list_databases()
    print(f"databases: {databases}")
    tables = mysql_client.list_tables("5000agent_feedback")
    print(f"tables:{tables}")
    mysql_client.close()
