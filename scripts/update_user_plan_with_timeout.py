import os
import signal
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import threading

# Настройки подключения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://transkribator:transkribator@localhost:5432/transkribator")
USERNAME = "Like_a_duck"
TIMEOUT = 10  # секунд

# Функция для выполнения запроса с таймаутом
class TimeoutException(Exception):
    pass

def handler(signum, frame):
    raise TimeoutException()

def update_user_plan():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE users SET current_plan = 'unlimited', plan_expires_at = NULL WHERE username = :username
            """),
            {"username": USERNAME}
        )
        print(f"User {USERNAME} updated to unlimited.")

def main():
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(TIMEOUT)
    try:
        update_user_plan()
        signal.alarm(0)
    except TimeoutException:
        print(f"Timeout: Query took longer than {TIMEOUT} seconds.")
        sys.exit(1)
    except SQLAlchemyError as e:
        print(f"SQLAlchemy error: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"Other error: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()
