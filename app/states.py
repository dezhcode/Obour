"""حالت های FSM ربات."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Buy(StatesGroup):
    # اسم سرویس، قبل از تایید پرداخت پرسیده می شود.
    # خرید پلن و ساخت دلخواه دو حالت جدا دارند، وگرنه هندلر پیام هر دو
    # روی یک state می نشست و اولی (خرید پلن) پیام دیگری را هم می گرفت.
    waiting_service_name = State()
    waiting_custom_name = State()
    waiting_discount = State()


class AiShop(StatesGroup):
    # ایمیلی که اشتراک (slot) روی آن فعال می شود
    waiting_email = State()


class Track(StatesGroup):
    waiting_code = State()


class Support(StatesGroup):
    waiting_message = State()


class Wallet(StatesGroup):
    waiting_amount = State()
    waiting_receipt = State()
    crypto_amount = State()
    stars_amount = State()


class Service(StatesGroup):
    waiting_name = State()


class Admin(StatesGroup):
    waiting_user_query = State()
    waiting_balance_delta = State()
    waiting_broadcast = State()
    waiting_setting = State()
    waiting_emoji = State()
    waiting_rules = State()
    waiting_cat_field = State()
    waiting_cat_new = State()
    waiting_plan_field = State()
    waiting_plan_new = State()
    waiting_discount_new = State()
    waiting_effect_capture = State()  # پیام با افکت دلخواه از ادمین
    waiting_broadcast_btn_label = State()
    waiting_broadcast_btn_url = State()
    waiting_reject_reason = State()  # دلیل دستی رد شارژ
    waiting_poll_question = State()
    waiting_poll_options = State()
    waiting_channel_post = State()
    waiting_winback = State()
    waiting_ai_field = State()
