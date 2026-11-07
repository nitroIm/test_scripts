import os
from datetime import timedelta
from tinkoff.invest import Client, CandleInterval, OrderDirection, OrderType
from tinkoff.invest.utils import now

TOKEN = os.environ.get("T_INVEST_TOKEN")

def main():
    if not TOKEN:
        print("!!! Ошибка: переменная T_INVEST_TOKEN не задана.")
        return

    with Client(TOKEN) as client:
        try:
            # 1. Счета
            accounts = client.users.get_accounts()
            print(f"✅ Счета получены: {len(accounts.accounts)}")
            if not accounts.accounts:
                print("Нет счетов для тестирования.")
                return
            account_id = accounts.accounts[0].id

            # 2. Портфель
            portfolio = client.operations.get_portfolio(account_id=account_id)
            print(f"✅ Портфель получен: {len(portfolio.positions)} позиций")

            # 3. Позиции
            positions = client.operations.get_positions(account_id=account_id)
            print(f"✅ Позиции получены: {len(positions.securities)} бумаг")

            # 4. Доступный остаток для вывода
            limits = client.operations.get_withdraw_limits(account_id=account_id)
            print(f"✅ Лимиты на вывод получены.")

            # 5. История свечей
            candles = client.get_all_candles(
                figi="BBG004730N88",
                from_=now() - timedelta(days=30),
                interval=CandleInterval.CANDLE_INTERVAL_HOUR,
            )
            print(f"✅ Свечи получены: {len(candles)} штук.")

            # 6. Информация об инструментах
            instruments = client.instruments.shares()
            print(f"✅ Список акций получен: {len(instruments.instruments)} шт.")

            print("\n--- ВСЕ ОСНОВНЫЕ ЗАПРОСЫ УСПЕШНО ВЫПОЛНЕНЫ ---")

        except Exception as e:
            print(f"❌ Произошла ошибка: {e}")

if __name__ == "__main__":
    main()