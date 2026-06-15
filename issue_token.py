"""
issue_token.py — ръчно издаване на токен по payment intent ID.

Употреба:
    python issue_token.py pi_3TiTtlKYR1RWCnis1vntwXlu

Нужни env vars (или ги постави директно долу):
    STRIPE_SECRET_KEY   sk_live_...
    APEX_SECRET         същият като в Railway
"""

import sys
import os
import hmac
import hashlib
import base64
import time
import stripe

# ── Конфигурация ───────────────────────────────────────────────
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
APEX_SECRET       = os.getenv("APEX_SECRET", "change-this-in-railway-to-a-long-random-string")
PLANS             = {"core", "pro"}
TOKEN_DAYS        = 30
# ───────────────────────────────────────────────────────────────

def make_token(expiry_timestamp: int, plan: str = "core") -> str:
    if plan not in PLANS:
        plan = "core"
    payload   = f"{expiry_timestamp}.{plan}"
    signature = hmac.new(APEX_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")

def main():
    if len(sys.argv) < 2:
        print("Употреба: python issue_token.py <payment_intent_id>")
        sys.exit(1)

    pi_id = sys.argv[1].strip()

    if not STRIPE_SECRET_KEY:
        print("ГРЕШКА: STRIPE_SECRET_KEY не е зададен.")
        sys.exit(1)

    if APEX_SECRET == "change-this-in-railway-to-a-long-random-string":
        print("ПРЕДУПРЕЖДЕНИЕ: APEX_SECRET е дефолтният! Токенът няма да работи в production.")

    stripe.api_key = STRIPE_SECRET_KEY

    print(f"\nТърся checkout session по payment intent: {pi_id}")

    # Stripe не дава директна връзка PI→Session; търсим в списъка на sessions
    sessions = stripe.checkout.Session.list(payment_intent=pi_id, limit=5)

    if not sessions.data:
        print("ГРЕШКА: Не намерих checkout session за този payment intent.")
        print("Провери дали STRIPE_SECRET_KEY е live ключ и payment intent-ът е от live mode.")
        sys.exit(1)

    session = sessions.data[0]

    print(f"\nНамерена session:")
    print(f"  ID:             {session.id}")
    print(f"  Status:         {session.status}")
    print(f"  Payment status: {session.payment_status}")
    print(f"  Plan (metadata):{(session.metadata or {}).get('plan', '(не е зададен)')}")
    print(f"  Customer email: {session.customer_details.email if session.customer_details else '(няма)'}")

    if session.payment_status != "paid":
        print(f"\nВНИМАНИЕ: payment_status е '{session.payment_status}', не 'paid'.")
        print("Издавам токен само за реално платени сесии. Прекратявам.")
        sys.exit(1)

    plan = (session.metadata or {}).get("plan", "core")
    if plan not in PLANS:
        plan = "core"

    expiry = int(time.time()) + TOKEN_DAYS * 24 * 60 * 60
    token  = make_token(expiry, plan)

    expiry_human = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(expiry))

    print(f"\n✅ Токенът е издаден успешно!")
    print(f"  План:    {plan.upper()}")
    print(f"  Валиден: {TOKEN_DAYS} дни (до {expiry_human})")
    print(f"\n━━━ ТОКЕН (копирай целия ред) ━━━")
    print(token)
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\nИзпрати на потребителя:")
    print(f"  https://apexpulse.pro/app?token={token}")

if __name__ == "__main__":
    main()
