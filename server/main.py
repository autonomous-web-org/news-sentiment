import os
from flask import Flask
from flask.views import MethodView
from flask_smorest import Api, Blueprint, abort
from marshmallow import Schema, fields, ValidationError
from dotenv import load_dotenv
import pymysql

# from sshtunnel import SSHTunnelForwarder
# from contextlib import contextmanager


load_dotenv()

# SSH_HOST = "ssh.pythonanywhere.com"      # or "ssh.eu.pythonanywhere.com"
# SSH_USERNAME = os.environ.get("PA_DB_USER")
# SSH_PASSWORD = os.environ.get("PA_SSH_PASSWORD")    # PythonAnywhere SSH/password auth

DB_HOST = os.environ.get("PA_DB_HOST")
DB_USER = os.environ.get("PA_DB_USER")
DB_PASSWORD = os.environ.get("PA_DB_PASSWORD")
DB_NAME = os.environ.get("PA_DB_NAME")

app = Flask(__name__)

# Flask-SMOREST configuration
app.config["API_TITLE"] = "Sentiment API"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.2"
app.config["OPENAPI_URL_PREFIX"] = "/"
app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

api = Api(app)

# @contextmanager  # ← Add this decorator!
# def mysql_conn_over_ssh():
#     """Create MySQL connection over SSH tunnel to PythonAnywhere."""
#     with SSHTunnelForwarder(
#         (SSH_HOST, 22),
#         ssh_username=SSH_USERNAME,
#         ssh_password=SSH_PASSWORD,
#         remote_bind_address=(DB_HOST, 3306),
#         set_keepalive=10.0
#     ) as tunnel:
#         local_port = tunnel.local_bind_port
#         conn = pymysql.connect(
#             host="127.0.0.1",
#             port=local_port,
#             user=DB_USER,
#             password=DB_PASSWORD,
#             database=DB_NAME,
#             charset="utf8mb4",
#             autocommit=True,
#             cursorclass=pymysql.cursors.DictCursor,  # ← Added this for consistency
#             connect_timeout=10,
#             read_timeout=30,
#             write_timeout=30,
#         )
#         try:
#             yield conn
#         finally:
#             conn.close()

def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )

def resolve_ticker_id(conn, exchange_code: str, symbol: str):
    sql = """
      SELECT t.id
      FROM tickers t
      JOIN exchanges e ON e.id = t.exchange_id
      WHERE LOWER(e.code) = %s AND UPPER(t.symbol) = %s AND active = 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (exchange_code.lower(), symbol.upper()))
        row = cur.fetchone()
        return row["id"] if row else None
    

# Marshmallow schemas for request/response validation
class SentimentQueryArgsSchema(Schema):
    exchange = fields.Str(required=True, metadata={"description": "Exchange code (e.g., NSE, NASDAQ)"})
    ticker = fields.Str(required=True, metadata={"description": "Ticker symbol (e.g., RELIANCE, PEP)"})

# class SentimentDataSchema(Schema):
#     date = fields.Date(metadata={"description": "Date of sentiment data"})
#     sentiment = fields.Int(metadata={"description": "Sentiment score"})

# Create a blueprint
blp = Blueprint(
    "sentiment",
    __name__,
    url_prefix="/",
    description="Sentiment data operations"
)


@blp.route("/sentiment")
class SentimentResource(MethodView):
    @blp.arguments(SentimentQueryArgsSchema, location="query")
    # @blp.response(200, SentimentDataSchema(many=True))  # Use the schema here
    @blp.response(200, description="Returns sentiment data in pipe-delimited format (date|sentiment)")
    @blp.alt_response(400, description="Missing exchange or ticker parameter")
    @blp.alt_response(404, description="Ticker not found")
    def get(self, args):
        """Get sentiment data for a specific ticker
        
        Returns sentiment data in pipe-delimited format with one entry per line:
        date|sentiment
        """
        exchange = args["exchange"].strip()
        ticker = args["ticker"].strip()
        
        if not exchange or not ticker:
            abort(400, message="missing exchange or ticker")

        conn = get_conn()
        try:
            # with mysql_conn_over_ssh() as conn:
            # Ensure socket is healthy; reconnect transparently if needed
            conn.ping(reconnect=True)

            tid = resolve_ticker_id(conn, exchange, ticker)
            if not tid:
                abort(404, message="Ticker not found")

            sql = """
            SELECT date, sentiment
            FROM sentiment_daily
            WHERE ticker_id = %s
            ORDER BY date ASC
            """
            lines = []
            # results = [] # uncomment if JSON response needed
            with conn.cursor() as cur:
                cur.execute(sql, (tid,))
                for row in cur.fetchall():
                    lines.append(f"{row['date'].isoformat()}|{int(row['sentiment'])}")
                    # results.append({
                    #     "date": row['date'].isoformat(),
                    #     "sentiment": int(row['sentiment'])
                    # })
            
            # return results
            body = "\n".join(lines) + ("\n" if lines else "")
            return body, 200, {"Content-Type": "text/plain"}
        finally:
            try:
                conn.close()
            except Exception:
                pass


# Register the blueprint
api.register_blueprint(blp)



@app.get("/")
def index():
    return "hello world"


# For local testing only;expose `app` as WSGI entrypoint.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
