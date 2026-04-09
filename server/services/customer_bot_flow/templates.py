"""
Verbatim customer-bot copy served by the API layer.

These strings are injected by the customer bot flow engine only. The LLM must not
invent or paraphrase welcome lines, onboarding menus, verification prompts, or
other scripted steps — see langchain_bot/prompts.py.
"""

from typing import Any, Dict

# Template id → language code → exact message ({placeholders} only where noted).
BOT_FLOW_TEMPLATES: Dict[str, Dict[str, str]] = {
    "welcome_back": {
        "english": (
            "Welcome back! Would you like to continue where we left off or start fresh?\n\n"
            "1️⃣ Continue\n"
            "2️⃣ Start fresh"
        ),
        "arabic": (
            "مرحبًا بعودتك! هل تريد المتابعة من حيث توقفت أم البدء من جديد؟\n\n"
            "1️⃣ متابعة\n"
            "2️⃣ البدء من جديد"
        ),
        "roman_urdu": (
            "Welcome back! Aap wahan se continue karna chahte hain jahan chhore the, ya naye siray se?\n\n"
            "1️⃣ Continue\n"
            "2️⃣ Start fresh"
        ),
    },
    "resume_continued": {
        "english": "Great — we'll pick up where you left off. 👍",
        "arabic": "تمام — سنكمل من حيث توقفنا. 👍",
        "roman_urdu": "Theek hai — jahan se chhore the wahan se continue karte hain. 👍",
    },
    "agent_relay_ack": {
        "english": (
            "✅ We received your message and shared it with our team.\n"
            "An agent will reply here as soon as they can.\n\n"
            "To leave this chat and talk to the bot again, send /reset"
        ),
        "arabic": (
            "✅ استلمنا رسالتك وتم إيصالها للفريق.\n"
            "سيرد عليك أحد الموظفين هنا في أقرب وقت.\n\n"
            "للعودة إلى البوت، أرسل /reset"
        ),
        "roman_urdu": (
            "✅ Aap ki message mil gayi aur team ko bhej di gayi.\n"
            "Agent jald yahin jawab dein ge.\n\n"
            "Bot se dubara baat karne ke liye /reset bhejein"
        ),
    },
    "entry": {
        "english": (
            "👋 Hi! Welcome to Arabia Dropshipping 🚀\n\n"
            "Are you:\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Reply with 1 or 2 😊\n"
            "Tip: type /reset anytime to restart this menu."
        ),
        "arabic": (
            "👋 السلام عليكم! مرحبًا بك في Arabia Dropshipping 🚀\n\n"
            "هل أنت:\n\n"
            "1️⃣ عميل جديد\n"
            "2️⃣ عميل حالي\n\n"
            "يرجى الرد بـ 1 أو 2 😊\n"
            "لإعادة القائمة اكتب /reset"
        ),
        "roman_urdu": (
            "👋 Salam! Welcome to Arabia Dropshipping 🚀\n\n"
            "Aap new customer hain ya existing customer?\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Reply mein 1 ya 2 likh dein 😊\n"
            "Menu dubara ke liye /reset likhein"
        ),
    },
    "new_welcome": {
        "english": (
            "Great! 🎉\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Browse products 🛍️\n"
            "2️⃣ Get information ℹ️\n"
            "3️⃣ Talk to support 👨‍💼\n\n"
            "Or type your question anytime 💬"
        ),
        "arabic": (
            "رائع! 🎉\n\n"
            "كيف يمكننا مساعدتك اليوم؟\n\n"
            "1️⃣ تصفح المنتجات 🛍️\n"
            "2️⃣ الحصول على معلومات ℹ️\n"
            "3️⃣ التحدث مع الدعم 👨‍💼\n\n"
            "أو اكتب سؤالك في أي وقت 💬"
        ),
        "roman_urdu": (
            "Zabardast! 🎉\n\n"
            "Aap ko kis cheez mein madad chahiye?\n\n"
            "1️⃣ Products dekhna 🛍️\n"
            "2️⃣ Maloomat lena ℹ️\n"
            "3️⃣ Support se baat karna 👨‍💼\n\n"
            "Ya apna sawal likh dein 💬"
        ),
    },
    "new_menu_after_greeting": {
        "english": (
            "Hello! 👋\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Browse products 🛍️\n"
            "2️⃣ Get information ℹ️\n"
            "3️⃣ Talk to support 👨‍💼\n\n"
            "Or type your question anytime 💬"
        ),
        "arabic": (
            "وعليكم السلام ورحمة الله 🌙\n\n"
            "كيف يمكننا مساعدتك اليوم؟\n\n"
            "1️⃣ تصفح المنتجات 🛍️\n"
            "2️⃣ الحصول على معلومات ℹ️\n"
            "3️⃣ التحدث مع الدعم 👨‍💼\n\n"
            "أو اكتب سؤالك في أي وقت 💬"
        ),
        "roman_urdu": (
            "Walaykum assalam! 🌙\n\n"
            "Aap ko kis cheez mein madad chahiye?\n\n"
            "1️⃣ Products dekhna 🛍️\n"
            "2️⃣ Maloomat lena ℹ️\n"
            "3️⃣ Support se baat karna 👨‍💼\n\n"
            "Ya apna sawal likh dein 💬"
        ),
    },
    "new_customer_order_use_existing_flow": {
        "english": (
            "📦 Order status is only available in the Existing customer flow (verify → Track order).\n\n"
            "Please reply with 2 (Existing customer), complete verification, then choose Track order and send your Order ID."
        ),
        "arabic": (
            "📦 حالة الطلب متاحة فقط في مسار عميل حالي (تحقق ← تتبع الطلب).\n\n"
            "يرجى الرد بـ 2 (عميل حالي)، ثم أكمل التحقق واختر تتبع الطلب وأرسل رقم الطلب."
        ),
        "roman_urdu": (
            "📦 Order status sirf Existing customer flow mein milta hai (verify → Order track).\n\n"
            "Please 2 (Existing customer) reply karein, verify complete karein, phir Order track choose karke Order ID bhejein."
        ),
    },
    "verify": {
        "english": "Please enter your verification code 🔐",
        "arabic": "يرجى إدخال رمز التحقق 🔐",
        "roman_urdu": "Apna verification code enter karein 🔐",
    },
    "verified_menu": {
        "english": (
            "✅ Verified successfully!\n\n"
            "How can we assist you?\n\n"
            "1️⃣ Track your order 📦\n"
            "2️⃣ Order details 📄\n"
            "3️⃣ Talk to support 👨‍💼\n\n"
            "Or type your question 💬"
        ),
        "arabic": (
            "✅ تم التحقق بنجاح!\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ تتبع الطلب 📦\n"
            "2️⃣ تفاصيل الطلب 📄\n"
            "3️⃣ التحدث مع الدعم 👨‍💼"
        ),
        "roman_urdu": (
            "✅ Verification successful!\n\n"
            "Aap kya karna chahte hain?\n\n"
            "1️⃣ Order track karein 📦\n"
            "2️⃣ Order details dekhein 📄\n"
            "3️⃣ Support se baat karein 👨‍💼"
        ),
    },
    "ask_order": {
        "english": "📦 Please enter your Order ID:",
        "arabic": "📦 يرجى إدخال رقم الطلب:",
        "roman_urdu": "Apna Order ID bhejein 📦",
    },
    "order_found": {
        "english": (
            "✅ Order found!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}"
        ),
        "arabic": (
            "✅ تم العثور على الطلب!\n\n"
            "📦 رقم الطلب: {order_id}\n"
            "📍 الحالة: {status}\n"
            "🚚 التوصيل: {delivery}"
        ),
        "roman_urdu": (
            "✅ Order mil gaya!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}"
        ),
    },
    "order_not_found": {
        "english": "Order nahi mila. Dobara check karein ya support likhein.",
        "arabic": "لم يتم العثور على الطلب. يرجى التحقق مرة أخرى أو اكتب support.",
        "roman_urdu": "Order nahi mila. Dobara check karein ya support likhein.",
    },
    "order_lookup_error": {
        "english": (
            "I'm having trouble reaching order data right now. Please try again in a moment, "
            "or type **agent** / **support** if you need help."
        ),
        "arabic": (
            "نواجه صعوبة في الوصول إلى بيانات الطلب حاليًا. يرجى المحاولة بعد قليل، "
            "أو اكتب **agent** / **support** للمساعدة."
        ),
        "roman_urdu": (
            "Abhi order data access mein masla aa raha hai. Thori dair baad dobara try karein, "
            "ya **agent** / **support** likhein."
        ),
    },
    "connecting": {
        "english": (
            "Sure! Connecting you to a human agent 👨‍💼\n"
            "Please wait a moment…"
        ),
        "arabic": (
            "حسنًا! سيتم توصيلك بأحد الموظفين 👨‍💼\n"
            "يرجى الانتظار قليلاً…"
        ),
        "roman_urdu": (
            "Theek hai! Aap ko agent se connect kiya ja raha hai 👨‍💼\n"
            "Thora intezar karein…"
        ),
    },
    "handoff_retry": {
        "english": (
            "Still looking for an available agent 👨‍💼\n"
            "Please wait — we'll connect you as soon as someone is free."
        ),
        "arabic": (
            "ما زلنا نبحث عن موظف متاح 👨‍💼\n"
            "يرجى الانتظار — سنوصلك فور توفر أحد."
        ),
        "roman_urdu": (
            "Abhi bhi available agent dhoondh rahe hain 👨‍💼\n"
            "Thora intezar karein — jaisay hi koi free ho ga connect kar dein ge."
        ),
    },
    "handoff_unavailable": {
        "english": (
            "⚠️ No agents are online right now.\n"
            "Please try again in a few minutes, or leave your message here and we'll reply when we're back."
        ),
        "arabic": (
            "⚠️ لا يوجد موظفون متصلون حاليًا.\n"
            "يرجى المحاولة بعد قليل، أو اترك رسالتك هنا وسنرد عند العودة."
        ),
        "roman_urdu": (
            "⚠️ Abhi koi agent online nahi hai.\n"
            "Kuch dair baad dobara try karein, ya yahin message chhor dein — wapas aate hi jawab dein ge."
        ),
    },
    "experience": {
        "english": (
            "How much experience do you have in dropshipping?\n\n"
            "1️⃣ Less than 1 year\n"
            "2️⃣ 1–2 years\n"
            "3️⃣ 3+ years"
        ),
        "arabic": (
            "ما مقدار خبرتك في الدروبشيبينغ؟\n\n"
            "1️⃣ أقل من سنة\n"
            "2️⃣ من 1 إلى سنتين\n"
            "3️⃣ أكثر من 3 سنوات"
        ),
        "roman_urdu": (
            "Aap ka dropshipping experience kitna hai?\n\n"
            "1️⃣ 1 saal se kam\n"
            "2️⃣ 1–2 saal\n"
            "3️⃣ 3+ saal"
        ),
    },
    "kb_wrap": {
        "english": (
            "💡 Here's what you need to know:\n\n{body}\n\n"
            "Need more help? Type support 👨‍💼\n"
            "To see the main choices again, type main menu."
        ),
        "arabic": (
            "💡 إليك المعلومات:\n\n{body}\n\n"
            "لمزيد من المساعدة اكتب support 👨‍💼\n"
            "لعرض الخيارات من جديد اكتب: القائمة الرئيسية"
        ),
        "roman_urdu": (
            "💡 Yeh information aap ke liye:\n\n{body}\n\n"
            "Mazeed madad ke liye support likhein 👨‍💼\n"
            "Menu dubara dekhne ke liye likhein: main menu"
        ),
    },
    "products_hint": {
        "english": "Browse products section is available. You can also type your question 💬",
        "arabic": "يمكنك تصفح قسم المنتجات. ويمكنك أيضاً كتابة سؤالك 💬",
        "roman_urdu": "Aap products browse kar sakte hain. Ya apna sawal likh dein 💬",
    },
    "fallback": {
        "english": (
            "I didn’t understand that 🤔\n"
            "Please choose an option or type your question 💬"
        ),
        "arabic": (
            "لم أفهم ذلك 🤔\n"
            "يرجى اختيار خيار أو كتابة سؤالك 💬"
        ),
        "roman_urdu": (
            "Mujhay samajh nahi aaya 🤔\n"
            "Please option select karein ya sawal likhein 💬"
        ),
    },
}


def resolve_bot_template(lang: str, template_id: str) -> str:
    """Resolve fixed bot copy for a language (used when the messaging layer augments replies)."""
    table = BOT_FLOW_TEMPLATES.get(template_id) or {}
    if not table:
        return ""
    return table.get(lang) or table.get("english") or next(iter(table.values()))


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
