"""
Verbatim customer-bot copy served by the API layer.

These strings are injected by the customer bot flow engine only. The LLM must not
invent or paraphrase welcome lines, onboarding menus, verification prompts, or
other scripted steps — see langchain_bot/prompts.py.
"""

from typing import Any, Dict, Optional

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
    "hello_ack": {
        "english": "Hello! How can I help today?",
        "arabic": "مرحبًا! كيف يمكنني مساعدتك اليوم؟",
        "roman_urdu": "Hello! Aaj kya madad karoon?",
    },
    "greeting": {
        "english": (
            "Hello. I'm Arabia Dropbot, your assistant for Arabia Dropshipping. "
            "Are you a new customer or existing customer?"
        ),
        "arabic": (
            "مرحبًا. أنا Arabia Dropbot، مساعدك لـ Arabia Dropshipping. "
            "هل أنت عميل جديد أم عميل حالي؟"
        ),
        "roman_urdu": (
            "Hello. Main Arabia Dropbot hoon, Arabia Dropshipping ka assistant. "
            "Kya aap new customer hain ya existing customer?"
        ),
    },
    "new_customer_welcome": {
        "english": "Great! How can I help you? Feel free to ask anything.",
        "arabic": "رائع! كيف يمكنني مساعدتك؟ لا تتردد في طرح أي سؤال.",
        "roman_urdu": "Zabardast! Main kaise madad kar sakta hoon? Koi bhi sawal pooch sakte hain.",
    },
    "existing_customer_welcome": {
        "english": "Great! How can I help you? Feel free to ask anything.",
        "arabic": "رائع! كيف يمكنني مساعدتك؟ لا تتردد في طرح أي سؤال.",
        "roman_urdu": "Zabardast! Main kaise madad kar sakta hoon? Koi bhi sawal pooch sakte hain.",
    },
    "entry": {
        "english": (
            "Hello. I'm Arabia Dropbot, your assistant for Arabia Dropshipping. How can I help?"
        ),
        "arabic": (
            "مرحبًا، أنا Arabia Dropbot، مساعدك في Arabia Dropshipping. كيف يمكنني مساعدتك؟"
        ),
        "roman_urdu": (
            "Hello, main Arabia Dropbot hoon — Arabia Dropshipping ka assistant. Kaise madad karoon?"
        ),
    },
    "new_welcome": {
        "english": (
            "Great! 😊\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Browse products 🛍️\n"
            "2️⃣ Get information ℹ️\n"
            "3️⃣ Talk to support\n\n"
            "Or type your question anytime"
        ),
        "arabic": (
            "رائع! 😊\n\n"
            "كيف يمكننا مساعدتك اليوم؟\n\n"
            "1️⃣ تصفح المنتجات 🛍️\n"
            "2️⃣ الحصول على معلومات ℹ️\n"
            "3️⃣ التحدث مع الدعم\n\n"
            "أو اكتب سؤالك في أي وقت"
        ),
        "roman_urdu": (
            "Great! 😊\n\n"
            "Aap ko kis cheez mein madad chahiye?\n\n"
            "1️⃣ Products dekhna 🛍️\n"
            "2️⃣ Maloomat lena ℹ️\n"
            "3️⃣ Support se baat karna\n\n"
            "Ya apna sawal likh dein"
        ),
    },
    "new_menu_after_greeting": {
        "english": (
            "Hello! 😊\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Browse products 🛍️\n"
            "2️⃣ Get information ℹ️\n"
            "3️⃣ Talk to support\n\n"
            "Or type your question anytime"
        ),
        "arabic": (
            "وعليكم السلام ورحمة الله 🌙\n\n"
            "كيف يمكننا مساعدتك اليوم؟\n\n"
            "1️⃣ تصفح المنتجات 🛍️\n"
            "2️⃣ الحصول على معلومات ℹ️\n"
            "3️⃣ التحدث مع الدعم\n\n"
            "أو اكتب سؤالك في أي وقت"
        ),
        "roman_urdu": (
            "Walaykum assalam! 🌙\n\n"
            "Aap ko kis cheez mein madad chahiye?\n\n"
            "1️⃣ Products dekhna 🛍️\n"
            "2️⃣ Maloomat lena ℹ️\n"
            "3️⃣ Support se baat karna\n\n"
            "Ya apna sawal likh dein"
        ),
    },
    "order_verify_intro": {
        "english": (
            "I can help you check your order status.\n\n"
            "To do this, I need to verify your account first.\n\n"
            "Please reply with your email address associated with your account."
        ),
        "arabic": (
            "يمكنني مساعدتك في التحقق من حالة طلبك.\n\n"
            "لذلك أحتاج أولاً إلى التحقق من حسابك.\n\n"
            "يرجى إرسال عنوان البريد الإلكتروني المرتبط بحسابك."
        ),
        "roman_urdu": (
            "Main aap ki order status check karne mein madad kar sakta hoon.\n\n"
            "Is ke liye pehle aap ka account verify karna zaroori hai.\n\n"
            "Apne account se jura hua email address bhejein."
        ),
    },
    "verification_expired_reverify": {
        "english": (
            "Your previous verification has expired for security.\n\n"
            "Please verify again. Send your email address."
        ),
        "arabic": (
            "انتهت صلاحية التحقق السابق لأسباب أمنية.\n\n"
            "يرجى التحقق مرة أخرى. أرسل عنوان بريدك الإلكتروني."
        ),
        "roman_urdu": (
            "Security ki wajah se aap ka pehla verification expire ho chuka hai.\n\n"
            "Dobara verify karein. Apna email address bhejein."
        ),
    },
    "account_verify_intro": {
        "english": (
            "I can help with account details (orders, invoices, etc.).\n\n"
            "To do this, I need to verify your account first.\n\n"
            "Please reply with your email address associated with your account."
        ),
        "arabic": (
            "يمكنني المساعدة في تفاصيل الحساب (الطلبات، الفواتير، وغيرها).\n\n"
            "لذلك أحتاج أولاً إلى التحقق من حسابك.\n\n"
            "يرجى إرسال عنوان البريد الإلكتروني المرتبط بحسابك."
        ),
        "roman_urdu": (
            "Main account se mutaliq cheezon (orders, invoices, waghera) mein madad kar sakta hoon.\n\n"
            "Is ke liye pehle aap ka account verify karna zaroori hai.\n\n"
            "Apne account se jura hua email address bhejein."
        ),
    },
    "ask_email": {
        "english": "Please reply with your email address associated with your account.",
        "arabic": "يرجى إرسال عنوان البريد الإلكتروني المرتبط بحسابك.",
        "roman_urdu": "Apne account se jura hua email address bhejein.",
    },
    "email_invalid": {
        "english": "Please enter a valid email address (example: name@email.com).",
        "arabic": "يرجى إدخال بريد إلكتروني صحيح (مثال: name@email.com).",
        "roman_urdu": "Please valid email likhein (misal: name@email.com).",
    },
    "code_sent": {
        "english": (
            "I've sent a 6-digit verification code to {email}.\n\n"
            "Please enter the code here.\n\n"
            "The code expires in 5 minutes.\n\n"
            "Type \"resend\" to get a new code."
        ),
        "arabic": (
            "أرسلتُ رمز تحقق مكوّن من 6 أرقام إلى {email}.\n\n"
            "يرجى إدخال الرمز هنا.\n\n"
            "تنتهي صلاحية الرمز خلال 5 دقائق.\n\n"
            "اكتب \"resend\" لإرسال رمز جديد."
        ),
        "roman_urdu": (
            "Main ne {email} par 6 digit ka verification code bhej diya hai.\n\n"
            "Yahan code enter karein.\n\n"
            "Code 5 minute mein expire ho jata hai.\n\n"
            "Naya code ke liye \"resend\" likhein."
        ),
    },
    "verify": {
        "english": (
            "I've sent a 6-digit verification code to {email}.\n\n"
            "Please enter the code here.\n\n"
            "The code expires in 5 minutes.\n\n"
            "Type \"resend\" to get a new code."
        ),
        "arabic": (
            "أرسلتُ رمز تحقق مكوّن من 6 أرقام إلى {email}.\n\n"
            "يرجى إدخال الرمز هنا.\n\n"
            "تنتهي صلاحية الرمز خلال 5 دقائق.\n\n"
            "اكتب \"resend\" لإرسال رمز جديد."
        ),
        "roman_urdu": (
            "Main ne {email} par 6 digit ka verification code bhej diya hai.\n\n"
            "Yahan code enter karein.\n\n"
            "Code 5 minute mein expire ho jata hai.\n\n"
            "Naya code ke liye \"resend\" likhein."
        ),
    },
    "verify_send_error": {
        "english": "We couldn't send a verification code right now. Please recheck your email and try again.",
        "arabic": "تعذر إرسال رمز التحقق الآن. يرجى التحقق من البريد الإلكتروني والمحاولة مرة أخرى.",
        "roman_urdu": "Abhi verification code send nahi ho saka. Email dobara check karke phir try karein.",
    },
    "verify_invalid_code": {
        "english": "The verification code is incorrect or expired. Please try again.",
        "arabic": "رمز التحقق غير صحيح أو منتهي الصلاحية. حاول مرة أخرى.",
        "roman_urdu": "Verification code ghalat hai ya expire ho gaya. Dobara try karein.",
    },
    "ask_mobile": {
        "english": "Please provide your mobile number 📱",
        "arabic": "يرجى إدخال رقم الجوال 📱",
        "roman_urdu": "Apna mobile number bhejein 📱",
    },
    "customer_not_found_after_verify": {
        "english": "We could not find a customer with this email and mobile. Please check and send your mobile number again.",
        "arabic": "لم نعثر على عميل بهذا البريد والجوال. يرجى التحقق وإرسال رقم الجوال مرة أخرى.",
        "roman_urdu": "Is email aur mobile par customer nahi mila. Mobile dobara check karke bhejein.",
    },
    "verification_success": {
        "english": "✅ Verified!",
        "arabic": "✅ تم التحقق!",
        "roman_urdu": "✅ Verified!",
    },
    "verified_followup": {
        "english": "Need anything else?",
        "arabic": "هل تحتاج إلى أي شيء آخر؟",
        "roman_urdu": "Aur kuch madad chahiye?",
    },
    "verified_menu": {
        "english": "✅ Verified! How can I help you next?",
        "arabic": "✅ تم التحقق! كيف يمكنني مساعدتك الآن؟",
        "roman_urdu": "✅ Verified! Ab kya madad karoon?",
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
    "connecting_agent_named": {
        "english": (
            "\n\nYou are now connected with {agent_name}. "
            "They will reply to you here."
        ),
        "arabic": (
            "\n\nتم توصيلك الآن مع {agent_name}. "
            "سيقوم بالرد عليك هنا."
        ),
        "roman_urdu": (
            "\n\nAap ab {agent_name} se connect ho gaye hain. "
            "Woh yahin reply karein ge."
        ),
    },
    "connecting": {
        "english": (
            "I understand. Let me connect you with a human agent.\n"
            "Please wait while I find an available agent."
        ),
        "arabic": (
            "أفهم ذلك. دعني أوصلك بأحد الوكلاء البشريين.\n"
            "يرجى الانتظار بينما أبحث عن وكيل متاح."
        ),
        "roman_urdu": (
            "Main samajh gaya. Mujhe aap ko human agent se connect karna hai.\n"
            "Meharbani karke thora intezar karein. Main abhi available agent dhoondh raha hoon."
        ),
    },
    "handoff_retry": {
        "english": (
            "Still looking for available support\n"
            "Please wait — we'll connect you as soon as someone is free."
        ),
        "arabic": (
            "ما زلنا نبحث عن دعم متاح\n"
            "يرجى الانتظار — سنوصلك فور توفر أحد."
        ),
        "roman_urdu": (
            "Abhi bhi available support dhoondh rahe hain\n"
            "Thora intezar karein — jaisay hi koi free ho ga connect kar dein ge."
        ),
    },
    "handoff_unavailable": {
        "english": (
            "⚠️ No agents are online right now.\n"
            "{schedule}"
            "Please try again in a few minutes, or leave your message here and we'll reply when we're back."
        ),
        "arabic": (
            "⚠️ لا يوجد موظفون متصلون حاليًا.\n"
            "{schedule}"
            "يرجى المحاولة بعد قليل، أو اترك رسالتك هنا وسنرد عند العودة."
        ),
        "roman_urdu": (
            "⚠️ Abhi koi agent online nahi hai.\n"
            "{schedule}"
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
            "{body}\n\n"
            "If you need more information or assistance, feel free to ask.\n"
            "You can also visit our website at https://www.arabiadropship.com\n"
            "Or type \"support\" to speak with a human agent."
        ),
        "arabic": (
            "{body}\n\n"
            "إذا كنت بحاجة إلى مزيد من المعلومات أو المساعدة، لا تتردد في السؤال.\n"
            "يمكنك أيضاً زيارة موقعنا: https://www.arabiadropship.com\n"
            "أو اكتب \"support\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "{body}\n\n"
            "Agar aapko mazeed information ya madad chahiye, befikr hokar poochein.\n"
            "Aap hamari website bhi visit kar sakte hain: https://www.arabiadropship.com\n"
            "Ya \"support\" likhein human agent se baat karne ke liye."
        ),
    },
    "unknown_info": {
        "english": 'I don\'t have that information. Type "agent" to speak with a human.',
        "arabic": "لا تتوفر لدي هذه المعلومة. اكتب \"agent\" للتحدث مع موظف.",
        "roman_urdu": "Mere paas yeh information nahi hai. Insaan se baat ke liye \"agent\" likhein.",
    },
    "products_hint": {
        "english": "Browse products section is available. You can also type your question.",
        "arabic": "يمكنك تصفح قسم المنتجات. ويمكنك أيضاً كتابة سؤالك.",
        "roman_urdu": "Aap products browse kar sakte hain. Ya apna sawal likh dein.",
    },
    "fallback": {
        "english": (
            "I didn’t catch that 🤔\n"
            "Ask your question in one message, or type \"agent\" for a human."
        ),
        "arabic": (
            "لم أفهم ذلك 🤔\n"
            "اكتب سؤالك في رسالة واحدة، أو اكتب \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Samajh nahi aaya 🤔\n"
            "Apna sawal ek message mein likhein, ya insaan ke liye \"agent\" likhein."
        ),
    },
}


def resolve_bot_template(lang: str, template_id: str) -> str:
    """Resolve fixed bot copy for a language (used when the messaging layer augments replies)."""
    table = BOT_FLOW_TEMPLATES.get(template_id) or {}
    if not table:
        return ""
    return table.get(lang) or table.get("english") or next(iter(table.values()))


def append_handoff_agent_line(lang: str, reply_text: str, agent_name: str) -> str:
    """Append one line naming the assigned human agent after the generic 'connecting' copy."""
    n = (agent_name or "").strip()
    if not n:
        return reply_text or ""
    tpl = resolve_bot_template(lang, "connecting_agent_named")
    if not tpl:
        return reply_text or ""
    try:
        suffix = tpl.format(agent_name=n)
    except Exception:
        suffix = f"\n\nYou're connected with {n}."
    return f"{(reply_text or '').strip()}{suffix}"


def lookup_agent_display_name(db: Any, agent_id: int) -> Optional[str]:
    """Display name for WhatsApp handoff follow-up (User.full_name, else Agent id)."""
    from models import Agent, User

    ag = db.query(Agent).filter(Agent.id == agent_id).first()
    if not ag:
        return None
    u = db.query(User).filter(User.id == ag.user_id).first()
    if u and (u.full_name or "").strip():
        return (u.full_name or "").strip()
    return f"Agent #{agent_id}"


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
