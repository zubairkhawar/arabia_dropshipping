"""
Verbatim customer-bot copy served by the API layer.

These strings are injected by the customer bot flow engine only. The LLM must not
invent or paraphrase welcome lines, onboarding menus, verification prompts, or
other scripted steps — see langchain_bot/prompts.py.
"""

from typing import Any, Dict

# Template id → language code → exact message ({placeholders} only where noted).
BOT_FLOW_TEMPLATES: Dict[str, Dict[str, str]] = {
    "entry": {
        "roman_urdu": (
            "👋 Salam! Welcome to *Arabia Dropshipping* 🚀\n\n"
            "Aap new customer hain ya existing customer?\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Reply mein 1 ya 2 likh dein 😊"
        ),
        "english": (
            "👋 Hi! Welcome to *Arabia Dropshipping* 🚀\n\n"
            "Are you a:\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Please reply with 1 or 2 😊"
        ),
        "arabic": (
            "👋 مرحباً! أهلاً بك في *Arabia Dropshipping* 🚀\n\n"
            "هل أنت:\n\n"
            "1️⃣ عميل جديد\n"
            "2️⃣ عميل حالي\n\n"
            "يرجى الرد بـ 1 أو 2 😊"
        ),
    },
    "new_welcome": {
        "roman_urdu": (
            "✨ Great! Welcome onboard.\n\n"
            "Hum aapki kaise madad kar sakte hain?\n\n"
            "1️⃣ Dropshipping ke baray mein maloomat\n"
            "2️⃣ Products dekhna\n"
            "3️⃣ Support se baat karna\n\n"
            "Aap apna sawal bhi likh sakte hain 💬"
        ),
        "english": (
            "✨ Great! Welcome onboard.\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Learn about dropshipping\n"
            "2️⃣ View products\n"
            "3️⃣ Talk to support\n\n"
            "You can also type your question 💬"
        ),
        "arabic": (
            "✨ رائع! أهلاً بك معنا.\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ التعرف على الدروبشيبينغ\n"
            "2️⃣ عرض المنتجات\n"
            "3️⃣ التحدث مع الدعم\n\n"
            "يمكنك أيضاً كتابة سؤالك 💬"
        ),
    },
    # After a greeting (Salam / hi / hello) on new-customer menu — server-only, no LLM / no kb_wrap.
    "new_menu_after_greeting": {
        "roman_urdu": (
            "Walaykum assalam! 🌙\n\n"
            "Hum aapki kaise madad kar sakte hain?\n\n"
            "1️⃣ Dropshipping ke baray mein maloomat\n"
            "2️⃣ Products dekhna\n"
            "3️⃣ Support se baat karna\n\n"
            "Aap apna sawal bhi likh sakte hain 💬"
        ),
        "english": (
            "Hello! 👋\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Learn about dropshipping\n"
            "2️⃣ View products\n"
            "3️⃣ Talk to support\n\n"
            "You can also type your question 💬"
        ),
        "arabic": (
            "وعليكم السلام ورحمة الله 🌙\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ التعرف على الدروبشيبينغ\n"
            "2️⃣ عرض المنتجات\n"
            "3️⃣ التحدث مع الدعم\n\n"
            "يمكنك أيضاً كتابة سؤالك 💬"
        ),
    },
    "verify": {
        "roman_urdu": (
            "🔐 Apna account verify karne ke liye code enter karein:\n\n"
            "(verification system will be added later — abhi ke liye apna code yahan likh dein.)"
        ),
        "english": (
            "🔐 Please verify your account.\n\n"
            "Enter the verification code sent to you:\n"
            "(Full verification will be enabled soon — for now, send any code to continue.)"
        ),
        "arabic": (
            "🔐 يرجى التحقق من حسابك.\n\n"
            "أدخل رمز التحقق المرسل إليك:\n"
            "(سيتم تفعيل التحقق الكامل لاحقاً — يمكنك إرسال أي رمز للمتابعة الآن.)"
        ),
    },
    "verified_menu": {
        "roman_urdu": (
            "✅ Verified successfully!\n\n"
            "Aap kya karna chahte hain?\n\n"
            "1️⃣ Order track karein 📦\n"
            "2️⃣ Account support\n"
            "3️⃣ Agent se baat karein 👨‍💼"
        ),
        "english": (
            "✅ Verified successfully!\n\n"
            "How can we assist you?\n\n"
            "1️⃣ Track your order 📦\n"
            "2️⃣ Account support\n"
            "3️⃣ Talk to agent 👨‍💼"
        ),
        "arabic": (
            "✅ تم التحقق بنجاح!\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ تتبع الطلب 📦\n"
            "2️⃣ دعم الحساب\n"
            "3️⃣ التحدث مع موظف 👨‍💼"
        ),
    },
    "ask_order": {
        "roman_urdu": "📦 Apna Order ID likhein:\nExample: 123456",
        "english": "📦 Please enter your Order ID:\nExample: 123456",
        "arabic": "📦 يرجى إدخال رقم الطلب:\nمثال: 123456",
    },
    "order_found": {
        "roman_urdu": (
            "✅ Order mil gaya!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}\n\n"
            "Shukriya 💙"
        ),
        "english": (
            "✅ Order found!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}\n\n"
            "Thank you 💙"
        ),
        "arabic": (
            "✅ تم العثور على الطلب!\n\n"
            "📦 رقم الطلب: {order_id}\n"
            "📍 الحالة: {status}\n"
            "🚚 التوصيل: {delivery}\n\n"
            "شكراً 💙"
        ),
    },
    "order_not_found": {
        "roman_urdu": (
            "❌ Order nahi mila.\n\n"
            "Dobara check karein ya *support* likhein."
        ),
        "english": (
            "❌ Order not found.\n\n"
            "Please double-check or type *support*."
        ),
        "arabic": (
            "❌ لم يتم العثور على الطلب.\n\n"
            "يرجى التحقق مرة أخرى أو اكتب *support*."
        ),
    },
    "connecting": {
        "roman_urdu": (
            "👨‍💼 Aap ko agent se connect kiya ja raha hai...\n\n"
            "Thori dair intezar karein."
        ),
        "english": (
            "👨‍💼 Connecting you to a support agent...\n\n"
            "Please wait a moment."
        ),
        "arabic": (
            "👨‍💼 جاري توصيلك بموظف الدعم...\n\n"
            "يرجى الانتظار لحظة."
        ),
    },
    "experience": {
        "roman_urdu": (
            "📊 Aap ka dropshipping experience kitna hai?\n\n"
            "1️⃣ Less than 1 year\n"
            "2️⃣ 1–2 years\n"
            "3️⃣ 3+ years"
        ),
        "english": (
            "📊 How much experience do you have in dropshipping?\n\n"
            "1️⃣ Less than 1 year\n"
            "2️⃣ 1–2 years\n"
            "3️⃣ 3+ years"
        ),
        "arabic": (
            "📊 ما مقدار خبرتك في الدروبشيبينغ؟\n\n"
            "1️⃣ أقل من سنة\n"
            "2️⃣ من 1 إلى سنتين\n"
            "3️⃣ أكثر من 3 سنوات"
        ),
    },
    "kb_wrap": {
        "roman_urdu": "💡 Yeh information aap ke liye:\n\n{body}\n\nMazeed madad ke liye *support* likhein 👨‍💼",
        "english": "💡 Here's what you need to know:\n\n{body}\n\nNeed more help? Type *support* 👨‍💼",
        "arabic": "💡 إليك المعلومات:\n\n{body}\n\nلمزيد من المساعدة اكتب *support* 👨‍💼",
    },
    "products_hint": {
        "roman_urdu": (
            "🛍️ Products ke liye hamari website / catalog dekhein (admin se link add karwa sakte hain).\n\n"
            "Aur sawal ho to likhein ya *support* likhein 👨‍💼"
        ),
        "english": (
            "🛍️ Please browse our website / catalog for products (your admin can add a direct link).\n\n"
            "Ask another question or type *support* 👨‍💼"
        ),
        "arabic": (
            "🛍️ يمكنك تصفح موقعنا / الكتالوج للمنتجات (يمكن للمسؤول إضافة رابط).\n\n"
            "اكتب سؤالاً آخر أو *support* 👨‍💼"
        ),
    },
    "account_support": {
        "roman_urdu": (
            "💬 Account support ke liye aap ko specialist se connect kiya ja raha hai...\n\n"
            "Thori dair intezar karein."
        ),
        "english": (
            "💬 Connecting you with account support...\n\n"
            "Please wait a moment."
        ),
        "arabic": (
            "💬 جاري توصيلك بدعم الحساب...\n\n"
            "يرجى الانتظار لحظة."
        ),
    },
    "fallback": {
        "roman_urdu": (
            "🤖 Samajh nahi aaya.\n\n"
            "Please 1 ya 2 select karein ya apna sawal likhein 😊"
        ),
        "english": (
            "🤖 Sorry, I didn't understand that.\n\n"
            "Please choose an option or type your question."
        ),
        "arabic": (
            "🤖 لم أفهم ذلك.\n\n"
            "يرجى اختيار خيار أو كتابة سؤالك."
        ),
    },
}


def public_templates_payload() -> Dict[str, Any]:
    """JSON-serializable object for GET /ai/customer-bot-templates."""
    return {
        "source": "server_templates",
        "description": (
            "Fixed copy for the structured customer bot. Not generated by the LLM. "
            "Channels should send these strings as returned by the messaging/chat API."
        ),
        "languages": ["roman_urdu", "english", "arabic"],
        "templates": BOT_FLOW_TEMPLATES,
    }
