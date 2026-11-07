import os
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API, INVEST_GRPC_API_SANDBOX

TOKEN_PROD = os.environ.get("T_INVEST_TOKEN")
TOKEN_SANDBOX = os.environ.get("T_SANDBOX")

def check_token(token, target, name):
    if not token:
        print(f"⚠️ Токен для {name} не найден.")
        return
    try:
        with Client(token, target=target) as client:
            accounts = client.users.get_accounts()
            print(f"✅ Токен РАБОТАЕТ в {name}! Найдено счетов: {len(accounts.accounts)}")
            for acc in accounts.accounts:
                print(f"   - ID: {acc.id}, Название: {acc.name}")
    except Exception as e:
        print(f"❌ Токен НЕ работает в {name}. Ошибка: {e}")

def main():
    print("--- ПРОВЕРКА РЕАЛЬНОГО ТОКЕНА (PROD) ---")
    check_token(TOKEN_PROD, INVEST_GRPC_API, "REAL")

    print("\n--- ПРОВЕРКА ТОКЕНА ПЕСОЧНИЦЫ (SANDBOX) ---")
    check_token(TOKEN_SANDBOX, INVEST_GRPC_API_SANDBOX, "SANDBOX")

if __name__ == "__main__":
    main()