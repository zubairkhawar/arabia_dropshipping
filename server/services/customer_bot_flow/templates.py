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
    "email_verified_success": {
        "english": "✅ Email verified successfully! Now please provide your mobile number.",
        "roman_urdu": "✅ Email verify ho gaya! Ab apna mobile number dein.",
        "arabic": "✅ تم التحقق من البريد الإلكتروني بنجاح! الرجاء تقديم رقم هاتفك المحمول.",
    },
    "ask_mobile": {
        "english": "Please provide your mobile number 📱",
        "arabic": "يرجى إدخال رقم الجوال 📱",
        "roman_urdu": "Apna mobile number bhejein 📱",
    },
    "mobile_unsupported_country": {
        "english": (
            "We only support phone numbers from Pakistan, UAE, and Saudi Arabia.\n\n"
            "🇵🇰 Pakistan: 03XXXXXXXXX or +923XXXXXXXXX\n"
            "🇦🇪 UAE: 971XXXXXXXXX\n"
            "🇸🇦 Saudi Arabia: 966XXXXXXXXX\n\n"
            "Please send a valid mobile number."
        ),
        "arabic": (
            "نحن ندعم أرقام الهاتف من باكستان والإمارات والسعودية فقط.\n\n"
            "🇵🇰 باكستان: 03XXXXXXXXX أو +923XXXXXXXXX\n"
            "🇦🇪 الإمارات: 971XXXXXXXXX\n"
            "🇸🇦 السعودية: 966XXXXXXXXX\n\n"
            "يرجى إرسال رقم جوال صحيح."
        ),
        "roman_urdu": (
            "Hum sirf Pakistan, UAE aur Saudi Arabia ke numbers support karte hain.\n\n"
            "🇵🇰 Pakistan: 03XXXXXXXXX ya +923XXXXXXXXX\n"
            "🇦🇪 UAE: 971XXXXXXXXX\n"
            "🇸🇦 Saudi Arabia: 966XXXXXXXXX\n\n"
            "Please sahih mobile number bhejein."
        ),
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
    "kb_wrap_agency": {
        "english": (
            "{body}\n\n"
            "For more details, visit our Agency Partnership Program:\n"
            "https://www.agency.arabiadropship.com/\n\n"
            "If you need more information or assistance, feel free to ask.\n"
            "You can also visit our website at https://www.arabiadropship.com\n"
            "Or type \"support\" to speak with a human agent."
        ),
        "arabic": (
            "{body}\n\n"
            "لمزيد من التفاصيل، قم بزيارة برنامج شراكة الوكالة:\n"
            "https://www.agency.arabiadropship.com/\n\n"
            "إذا كنت بحاجة إلى مزيد من المعلومات أو المساعدة، لا تتردد في السؤال.\n"
            "يمكنك أيضاً زيارة موقعنا: https://www.arabiadropship.com\n"
            "أو اكتب \"support\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "{body}\n\n"
            "Mazeed details ke liye hamara Agency Partnership Program dekhein:\n"
            "https://www.agency.arabiadropship.com/\n\n"
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
    "trending_ask_country": {
        "english": (
            "Which country's trending products would you like to see?\n\n"
            "1️⃣ 🇸🇦 KSA (Saudi Arabia)\n"
            "2️⃣ 🇦🇪 UAE\n"
            "3️⃣ 🇵🇰 Pakistan\n\n"
            "Reply with the number (1–3) or the country name."
        ),
        "arabic": (
            "ما هي دولة المنتجات الرائجة التي تريد رؤيتها؟\n\n"
            "1️⃣ 🇸🇦 السعودية (KSA)\n"
            "2️⃣ 🇦🇪 الإمارات (UAE)\n"
            "3️⃣ 🇵🇰 باكستان (Pakistan)\n\n"
            "أرسل الرقم (1–3) أو اسم الدولة."
        ),
        "roman_urdu": (
            "Aap kis country ke trending products dekhna chahte hain?\n\n"
            "1️⃣ 🇸🇦 KSA (Saudi Arabia)\n"
            "2️⃣ 🇦🇪 UAE\n"
            "3️⃣ 🇵🇰 Pakistan\n\n"
            "1–3 mein se number ya country name likhein."
        ),
    },
    "trending_country_retry": {
        "english": "Please choose one: 1 = KSA 🇸🇦, 2 = UAE 🇦🇪, 3 = Pakistan 🇵🇰 (or type KSA / UAE / PK).",
        "arabic": "يرجى اختيار: 1 = السعودية 🇸🇦، 2 = الإمارات 🇦🇪، 3 = باكستان 🇵🇰 (أو اكتب KSA / UAE / PK).",
        "roman_urdu": "Please choose: 1 = KSA 🇸🇦, 2 = UAE 🇦🇪, 3 = Pakistan 🇵🇰 (ya KSA / UAE / PK likhein).",
    },
    "trending_after_images_footer": {
        "english": (
            "These are the current trending products in {country}! 🔥\n\n"
            "Want details on a specific product? Type the product name (or its number from the list).\n\n"
            "Or type your question anytime."
        ),
        "arabic": (
            "هذه المنتجات الرائجة الحالية في {country}! 🔥\n\n"
            "تريد تفاصيل عن منتج معيّن؟ اكتب اسم المنتج (أو رقمه من القائمة).\n\n"
            "أو اكتب سؤالك في أي وقت."
        ),
        "roman_urdu": (
            "Yeh {country} ke current trending products hain! 🔥\n\n"
            "Kisi product ki detail chahiye? Product ka naam likhein (ya list ka number).\n\n"
            "Ya kabhi bhi apna sawal likhein."
        ),
    },
    "trending_product_not_matched": {
        "english": (
            "I couldn’t match that to one of the trending products I just showed. "
            "Try the exact product name, a number from the list (1–8), or type \"agent\" for a human."
        ),
        "arabic": (
            "لم أستطع ربط ذلك بأحد المنتجات الرائجة التي عرضتها للتو. "
            "جرّب اسم المنتج بدقة، أو رقماً من القائمة (1–8)، أو اكتب \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Isay abhi dikhaye gaye trending products se match nahi kar saka. "
            "Exact naam try karein, list ka number (1–8), ya \"agent\" likhein human ke liye."
        ),
    },
    "trending_header": {
        "english": "🔥 Trending picks for {country}:",
        "arabic": "🔥 منتجات رائجة في {country}:",
        "roman_urdu": "🔥 {country} ke trending picks:",
    },
    "trending_header_category": {
        "english": "🔥 Trending {category} picks for {country}:",
        "arabic": "🔥 منتجات {category} الرائجة في {country}:",
        "roman_urdu": "🔥 {country} ke trending {category} picks:",
    },
    "trending_no_products": {
        "english": "No trending products are listed for {country} yet.",
        "arabic": "لا توجد منتجات رائجة مسجّلة لـ {country} حتى الآن.",
        "roman_urdu": "Abhi {country} ke liye koi trending product list nahi hai.",
    },
    "trending_no_products_category": {
        "english": "No trending {category} products are listed for {country} yet. Try another category/country or ask me anything else.",
        "arabic": "لا توجد منتجات {category} رائجة مسجّلة لـ {country} حالياً. جرّب فئة/دولة أخرى أو اسألني أي شيء آخر.",
        "roman_urdu": "Abhi {country} mein {category} category ke trending products list nahi hain. Doosri category/country try karein ya koi aur sawal pooch lein.",
    },
    "sourcing_collect_details": {
        "english": (
            "Thank you for your interest in sourcing a product! 📦\n\n"
            "Please share the following details so our support team can assist you:\n\n"
            "📷 Product picture (if available)\n"
            "📝 Product name\n"
            "🔢 Required quantity\n\n"
            "Once you share these details, I will connect you with a support agent "
            "who will help you with pricing and availability."
        ),
        "arabic": (
            "شكرًا لاهتمامك بتوريد منتج! 📦\n\n"
            "يرجى مشاركة التفاصيل التالية حتى يتمكن فريق الدعم من مساعدتك:\n\n"
            "📷 صورة المنتج (إن وجدت)\n"
            "📝 اسم المنتج\n"
            "🔢 الكمية المطلوبة\n\n"
            "بمجرد مشاركة هذه التفاصيل، سأوصلك بأحد موظفي الدعم "
            "للمساعدة في الأسعار والتوفر."
        ),
        "roman_urdu": (
            "Product sourcing mein interest ke liye shukriya! 📦\n\n"
            "Hamari support team ki madad ke liye yeh details share karein:\n\n"
            "📷 Product ki picture (agar available ho)\n"
            "📝 Product ka naam\n"
            "🔢 Kitni quantity chahiye\n\n"
            "Yeh details milne ke baad main aapko support agent se connect kar doonga "
            "jo pricing aur availability mein madad karega."
        ),
    },
    "sourcing_with_product": {
        "english": (
            "Thank you for your interest in sourcing {product}! 📦\n\n"
            "Please also share:\n\n"
            "📷 Product picture (if available)\n"
            "🔢 Required quantity\n\n"
            "Once you share these details, I will connect you with a support agent "
            "who will help you with pricing and availability."
        ),
        "arabic": (
            "شكرًا لاهتمامك بتوريد {product}! 📦\n\n"
            "يرجى أيضاً مشاركة:\n\n"
            "📷 صورة المنتج (إن وجدت)\n"
            "🔢 الكمية المطلوبة\n\n"
            "بمجرد مشاركة هذه التفاصيل، سأوصلك بأحد موظفي الدعم "
            "للمساعدة في الأسعار والتوفر."
        ),
        "roman_urdu": (
            "{product} sourcing mein interest ke liye shukriya! 📦\n\n"
            "Yeh bhi share karein:\n\n"
            "📷 Product ki picture (agar available ho)\n"
            "🔢 Kitni quantity chahiye\n\n"
            "Yeh details milne ke baad main aapko support agent se connect kar doonga "
            "jo pricing aur availability mein madad karega."
        ),
    },
    "sourcing_handoff": {
        "english": (
            "Thank you for providing the details! 🙏\n\n"
            "I am now connecting you with a support agent who will assist you with "
            "pricing, availability, and your order. Please wait a moment."
        ),
        "arabic": (
            "شكرًا لتقديم التفاصيل! 🙏\n\n"
            "أقوم الآن بتوصيلك بموظف دعم سيساعدك في "
            "الأسعار والتوفر وطلبك. يرجى الانتظار لحظة."
        ),
        "roman_urdu": (
            "Details share karne ka shukriya! 🙏\n\n"
            "Main ab aapko support agent se connect kar raha hoon jo "
            "pricing, availability, aur aapke order mein madad karega. "
            "Thora intezar karein."
        ),
    },
    "sourcing_bulk_handoff": {
        "english": (
            "Thank you for your bulk order inquiry! 📦\n\n"
            "For your order, our support team will provide you with:\n\n"
            "• Wholesale pricing\n"
            "• Bulk shipping rates\n"
            "• Estimated delivery timeline\n\n"
            "I am connecting you with a support agent now. Please wait a moment."
        ),
        "arabic": (
            "شكرًا لاستفسارك عن الطلب بالجملة! 📦\n\n"
            "لطلبك، سيقدم لك فريق الدعم:\n\n"
            "• أسعار الجملة\n"
            "• أسعار الشحن بالجملة\n"
            "• الجدول الزمني المتوقع للتسليم\n\n"
            "أقوم بتوصيلك بموظف دعم الآن. يرجى الانتظار لحظة."
        ),
        "roman_urdu": (
            "Bulk order inquiry ke liye shukriya! 📦\n\n"
            "Aapke order ke liye hamari support team yeh provide karegi:\n\n"
            "• Wholesale pricing\n"
            "• Bulk shipping rates\n"
            "• Estimated delivery timeline\n\n"
            "Main ab aapko support agent se connect kar raha hoon. Thora intezar karein."
        ),
    },
    "fallback": {
        "english": (
            "Sorry, I could not fully understand that.\n"
            "Please ask your question again in one message, or type \"agent\" to speak with a human."
        ),
        "arabic": (
            "عذرا، لم أتمكن من فهم سؤالك بالكامل.\n"
            "يرجى كتابة سؤالك مرة أخرى في رسالة واحدة، أو اكتب \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Maaf kijiye, main aapki baat samajh nahi paya.\n"
            "Kya aap apna sawal dobara ek message mein pooch sakte hain? Ya \"agent\" likh kar human support se baat kar sakte hain."
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
