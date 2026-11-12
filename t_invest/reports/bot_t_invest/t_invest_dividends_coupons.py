# PROD CONTOUR ONLY
# Python: 3.10

import os
import sys
import json
import logging
import io
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.utils import now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_T_INVEST_CHANNEL")
WHITELIST_FILE = "t_invest/data/scanner/whitelist.json"

KLG_TZ = timezone(timedelta(hours=2))

RELIABLE_ISSUERS = ["ОФЗ", "Сбер", "Газпром", "Лукойл", "Роснефть", "РЖД", "МТС", "Магнит"]

def q2f(q):
    if q is None: return 0.0
    return q.units + q.nano / 1e9

def format_money(val):
    return f"{val:.2f}".rstrip('0').rstrip('.')

def send_telegram_photo(photo_buf, caption):
    if not TG_TOKEN or not TG_CHAT_ID:
        log.error("Нет TG токена или ID канала")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    payload = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    files = {"photo": ("chart.png", photo_buf, "image/png")}
    try:
        response = requests.post(url, data=payload, files=files, timeout=15)
        return response.json().get("ok", False)
    except Exception as e:
        log.error(f"TG Send Error: {e}")
        return False

def create_chart(stocks_data, bonds_data):
    plt.style.use('dark_background')
    # Увеличили размер фигуры, чтобы шрифты помещались и были большими
    fig, ax = plt.subplots(figsize=(10, 6), facecolor='#1a1a1a')
    ax.set_facecolor('#1a1a1a')

    labels = []
    values = []
    colors = []

    for s in stocks_data:
        labels.append(s['ticker'])
        values.append(s['yield_pct'])
        colors.append('#00C853')

    for b in bonds_data:
        labels.append(b['display_name'])
        values.append(b['coupon_value'])
        colors.append('#29B6F6')

    if not labels:
        return None

    y_pos = range(len(labels))
    bars = ax.barh(y_pos, values, color=colors, height=0.6)
    ax.set_yticks(y_pos)
    
    # УВЕЛИЧИЛИ ШРИФТ НАЗВАНИЙ
    ax.set_yticklabels(labels, fontsize=14, fontweight='bold')
    ax.invert_yaxis()

    # УВЕЛИЧИЛИ ШРИФТ ЦИФР НА СТОЛБИКАХ
    for bar in bars:
        width = bar.get_width()
        ax.text(width, bar.get_y() + bar.get_height()/2, f' {width:.2f}', 
                va='center', ha='left', color='white', fontweight='bold', fontsize=14)

    # Динамический заголовок
    if stocks_data and bonds_data:
        title = "Выплаты: Акции (Доходность %) / Облигации (Купон ₽)"
    elif bonds_data:
        title = "Купоны (облигации): Размер выплаты в ₽"
    else:
        title = "Дивиденды (акции): Доходность в %"

    # УВЕЛИЧИЛИ ШРИФТ ЗАГОЛОВКА
    ax.set_title(title, color='#ffffff', pad=20, fontsize=16, fontweight='bold')
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    # УВЕЛИЧИЛИ ШРИФТ ОСИ X (цифры внизу)
    ax.tick_params(axis='x', colors='#aaaaaa', labelsize=12)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

def main():
    if not TOKEN:
        log.error("Нет T_INVEST_TOKEN")
        sys.exit(1)

    today = datetime.now(KLG_TZ).date()
    tomorrow = today + timedelta(days=1)

    stocks_events = []
    bonds_events = []

    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        # === 1. ДИВИДЕНДЫ ===
        if os.path.exists(WHITELIST_FILE):
            with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                wl_data = json.load(f)
                wl_stocks = wl_data.get("data", [])
                
            for s in wl_stocks:
                figi = s.get("figi")
                ticker = s.get("ticker")
                try:
                    divs = client.instruments.get_dividends(figi=figi)
                    for d in divs.dividends:
                        r_date = d.record_date.date()
                        if r_date in (today, tomorrow):
                            price_resp = client.market_data.get_last_prices(figi=[figi])
                            price = q2f(price_resp.last_prices[0].price) if price_resp.last_prices else 0
                            div_val = q2f(d.dividend_net)
                            
                            yield_pct = (div_val / price * 100) if price > 0 else 0
                            
                            stocks_events.append({
                                "ticker": ticker,
                                "price": price,
                                "div": div_val,
                                "yield_pct": yield_pct,
                                "date": "сегодня" if r_date == today else "завтра"
                            })
                except Exception:
                    pass

        stocks_events = sorted(stocks_events, key=lambda x: x['yield_pct'], reverse=True)[:5]

        # === 2. КУПОНЫ ===
        try:
            bonds_resp = client.instruments.bonds(instrument_status=1)
            for b in bonds_resp.instruments:
                if not any(issuer.lower() in b.name.lower() for issuer in RELIABLE_ISSUERS):
                    continue
                
                try:
                    from_dt = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
                    to_dt = datetime.combine(tomorrow, datetime.max.time()).replace(tzinfo=timezone.utc)
                    
                    coupons = client.instruments.get_bond_coupons(figi=b.figi, from_=from_dt, to=to_dt)
                    for c in coupons.events:
                        c_date = c.coupon_date.date()
                        if c_date in (today, tomorrow):
                            coupon_val = q2f(c.pay_one_bond)
                            
                            nkd_val = 0.0
                            try:
                                nkd_resp = client.instruments.get_accrued_interests(figi=b.figi, from_=from_dt, to=from_dt)
                                if nkd_resp.accrued_interests:
                                    nkd_val = q2f(nkd_resp.accrued_interests[0].value)
                            except: pass

                            raw_ticker = b.ticker if b.ticker else ""
                            if raw_ticker.startswith("RU") or not raw_ticker:
                                # Увеличили лимит обрезки имени до 25 символов, чтобы было понятнее
                                display_name = b.name[:25].strip()
                            else:
                                display_name = raw_ticker

                            bonds_events.append({
                                "ticker": raw_ticker,
                                "display_name": display_name,
                                "name": b.name,
                                "coupon_value": coupon_val,
                                "nkd": nkd_val,
                                "date": "сегодня" if c_date == today else "завтра"
                            })
                except Exception:
                    pass
        except Exception as e:
            log.error(f"Ошибка получения облигаций: {e}")

        bonds_events = sorted(bonds_events, key=lambda x: x['coupon_value'], reverse=True)[:5]

    if not stocks_events and not bonds_events:
        log.info("Нет выплат на сегодня/завтра. Пост не отправлен.")
        sys.exit(0)

    # === 3. ФОРМИРУЕМ ТЕКСТ ===
    date_str = today.strftime("%d.%m.%Y")
    text = f"📅 <b>Календарь выплат на {date_str}</b>\n\n"

    if stocks_events:
        text += "💸 <b>Дивиденды (акции):</b>\n"
        for s in stocks_events:
            if s['date'] == "сегодня":
                text += f"• <b>{s['ticker']}</b> — Цена: {format_money(s['price'])} ₽ | Дивиденд: {format_money(s['div'])} ₽ (Доходность: {s['yield_pct']:.1f}%)\n"
            else:
                text += f"• <b>{s['ticker']}</b> — <i>Завтра</i> отсечка. Дивиденд: {format_money(s['div'])} ₽\n"
        text += "\n"

    if bonds_events:
        text += "🏦 <b>Купоны (облигации):</b>\n"
        for b in bonds_events:
            if b['date'] == "сегодня":
                text += f"• <b>{b['display_name']}</b> — Купон: {format_money(b['coupon_value'])} ₽ | НКД: {format_money(b['nkd'])} ₽\n"
            else:
                text += f"• <b>{b['display_name']}</b> — <i>Завтра</i> купон: {format_money(b['coupon_value'])} ₽\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск. Налог 13% удерживается автоматически.</i>"

    # === 4. ГЕНЕРАЦИЯ ГРАФИКА ===
    chart_buf = create_chart(stocks_events, bonds_events)

    # === 5. ОТПРАВКА ===
    if chart_buf:
        success = send_telegram_photo(chart_buf, text)
        if success:
            log.info("Календарь выплат успешно отправлен в канал.")
        else:
            log.error("Не удалось отправить в Telegram.")
    else:
        log.error("Не удалось сгенерировать график (пустые данные).")

if __name__ == "__main__":
    main()