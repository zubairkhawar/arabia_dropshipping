"""
Verbatim customer-bot copy served by the API layer.

These strings are injected by the customer bot flow engine only. The LLM must not
invent or paraphrase welcome lines, onboarding menus, verification prompts, or
other scripted steps — see langchain_bot/prompts.py.
"""

from typing import Any, Dict, Optional

# Template id → language code → exact message ({placeholders} only where noted).
BOT_FLOW_TEMPLATES: Dict[str, Dict[str, str]] = {
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
    "thanks_ack": {
        "english": "You're welcome! Is there anything else I can help you with?",
        "arabic": "على الرحب والسعة! هل هناك أي شيء آخر يمكنني مساعدتك به؟",
        "roman_urdu": "Shukriya! Kya aur koi madad chahiye?",
    },
    "customer_type_menu_reminder": {
        "english": "To continue, reply **1** if you are a new customer or **2** if you are an existing customer.",
        "arabic": "للمتابعة، أجب بـ **1** إذا كنت عميلاً جديداً أو **2** إذا كنت عميلاً حالياً.",
        "roman_urdu": "Aage barhne ke liye **1** likhein agar new customer, **2** likhein agar existing customer.",
    },
    "customer_type_unclear": {
        "english": (
            "No problem! To help you better, please let me know:\n\n"
            "**1** — I'm a new customer\n"
            "**2** — I'm an existing customer\n\n"
            "Just reply with 1 or 2."
        ),
        "arabic": (
            "لا مشكلة! لمساعدتك بشكل أفضل، يرجى إخباري:\n\n"
            "**1** — أنا عميل جديد\n"
            "**2** — أنا عميل حالي\n\n"
            "فقط أرسل 1 أو 2."
        ),
        "roman_urdu": (
            "Koi masla nahi! Aapki behtar madad ke liye batayein:\n\n"
            "**1** — Main new customer hoon\n"
            "**2** — Main existing customer hoon\n\n"
            "Sirf 1 ya 2 likhein."
        ),
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
    "order_verify_intro": {
        "english": (
            "I understand you want to check your order details. Let me help you with that.\n\n"
            "To protect your privacy, orders are linked to specific accounts, and I couldn't "
            "find any under your current session.\n\n"
            "*Quick ways to resolve this:*\n\n"
            "1. *Share your order number* (for example #157955)\n"
            "2. *Send the email address* you used when ordering\n"
            "3. *Check your inbox* for the order confirmation email\n\n"
            "Once you provide your order number or email, I'll instantly show you:\n"
            "• Current status & tracking\n"
            "• Delivery estimate\n"
            "• Complete order summary\n\n"
            "Which would you prefer to share?"
        ),
        "arabic": (
            "أفهم أنك تريد الاطلاع على تفاصيل طلبك. سأساعدك في ذلك.\n\n"
            "للحفاظ على خصوصيتك، الطلبات مرتبطة بحسابات محددة، ولم أجد أي طلبات "
            "ضمن جلستك الحالية.\n\n"
            "*طرق سريعة للحل:*\n\n"
            "1. *أرسل رقم الطلب* (مثلاً #157955)\n"
            "2. *أرسل البريد الإلكتروني* الذي استخدمته عند الطلب\n"
            "3. *تحقق من بريدك الإلكتروني* بحثاً عن رسالة تأكيد الطلب\n\n"
            "فور إرسال رقم الطلب أو البريد الإلكتروني، سأعرض لك فوراً:\n"
            "• الحالة الحالية ومعلومات التتبع\n"
            "• الموعد التقديري للتسليم\n"
            "• ملخص الطلب الكامل\n\n"
            "أيهما تفضل أن ترسل؟"
        ),
        "roman_urdu": (
            "Main samajh gaya ke aap order details dekhna chahte hain — main madad karta hoon.\n\n"
            "Aap ki privacy ke liye orders sirf specific accounts se linked hote hain, aur mujhe "
            "aap ki current session mein koi order nahi mila.\n\n"
            "*Jaldi solve karne ke teen tareeqay:*\n\n"
            "1. *Order number bhejein* (misal #157955)\n"
            "2. *Woh email bhejein* jo order ke waqt use ki thi\n"
            "3. *Apna inbox check karein* — order confirmation email mil sakti hai\n\n"
            "Order number ya email milte hi main fauran ye dikhaoonga:\n"
            "• Current status aur tracking\n"
            "• Delivery ka takhmeeni waqt\n"
            "• Poora order summary\n\n"
            "Aap kaun sa bhejna chahenge?"
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
            "I understand you want to check your account details (orders, invoices, tracking). "
            "Let me help you with that.\n\n"
            "To protect your privacy, account data is tied to a verified email, and I couldn't "
            "find any under your current session.\n\n"
            "*Quick ways to resolve this:*\n\n"
            "1. *Send the email address* you used when signing up\n"
            "2. *Share an order number* (for example #157955) if you just want that order's details\n"
            "3. *Check your inbox* for our latest email — your account email will be the \"To\" address\n\n"
            "Once you share either, I'll instantly show you orders, invoices, or tracking.\n\n"
            "Which would you prefer to share?"
        ),
        "arabic": (
            "أفهم أنك تريد الاطلاع على تفاصيل حسابك (الطلبات والفواتير والتتبع). سأساعدك في ذلك.\n\n"
            "للحفاظ على خصوصيتك، بيانات الحساب مرتبطة ببريد إلكتروني مُحقَّق، ولم أجد أي بيانات "
            "ضمن جلستك الحالية.\n\n"
            "*طرق سريعة للحل:*\n\n"
            "1. *أرسل البريد الإلكتروني* الذي استخدمته عند التسجيل\n"
            "2. *أرسل رقم طلب* (مثلاً #157955) إذا كنت تريد تفاصيل طلب واحد فقط\n"
            "3. *تحقق من بريدك الإلكتروني* — آخر رسالة منّا ستكون على عنوان حسابك\n\n"
            "فور إرسال أحدها، سأعرض لك الطلبات أو الفواتير أو التتبع فوراً.\n\n"
            "أيهما تفضل أن ترسل؟"
        ),
        "roman_urdu": (
            "Main samajh gaya ke aap account details (orders, invoices, tracking) dekhna chahte "
            "hain — main madad karta hoon.\n\n"
            "Privacy ke liye account data sirf verified email se linked hota hai, aur mujhe aap ki "
            "current session mein koi record nahi mila.\n\n"
            "*Jaldi solve karne ke teen tareeqay:*\n\n"
            "1. *Sign-up ki email* bhejein\n"
            "2. *Order number bhejein* (misal #157955) agar sirf usi order ki details chahiye\n"
            "3. *Apna inbox check karein* — hamari latest email aap ki account email par aayi hogi\n\n"
            "Koi bhi bhejte hi main fauran orders, invoices ya tracking dikha doonga.\n\n"
            "Aap kaun sa bhejna chahenge?"
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
        "english": "We only support 🇵🇰 Pakistan, 🇦🇪 UAE, and 🇸🇦 Saudi Arabia numbers. Please send a valid mobile.",
        "arabic": "ندعم أرقام 🇵🇰 باكستان و🇦🇪 الإمارات و🇸🇦 السعودية فقط. يرجى إرسال رقم جوال صحيح.",
        "roman_urdu": "Sirf 🇵🇰 Pakistan, 🇦🇪 UAE aur 🇸🇦 Saudi Arabia ke numbers. Sahih mobile bhejein.",
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
    "order_not_found": {
        "english": (
            "I couldn't find that order on your account. "
            "Please double-check the order number and try again, "
            "or type **agent** / **support** if you need help."
        ),
        "arabic": (
            "لم يتم العثور على الطلب في حسابك. "
            "يرجى التحقق من رقم الطلب والمحاولة مرة أخرى، "
            "أو اكتب **agent** / **support** للمساعدة."
        ),
        "roman_urdu": (
            "Mujhe aapke account mein yeh order nahi mila. "
            "Order number check karke dobara try karein, "
            "ya **agent** / **support** likhein."
        ),
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
    "invoice_not_found": {
        "english": (
            "I couldn't find an invoice matching that request. "
            "Please double-check the order/invoice number, or type **agent** for help."
        ),
        "arabic": (
            "لم أتمكن من العثور على فاتورة مطابقة. "
            "يرجى التحقق من رقم الطلب/الفاتورة، أو اكتب **agent** للمساعدة."
        ),
        "roman_urdu": (
            "Koi matching invoice nahi mila. Order ya invoice number check karein, "
            "ya **agent** likhein madad ke liye."
        ),
    },
    "invoice_lookup_error": {
        "english": (
            "I'm having trouble reaching invoice data right now. Please try again in a moment, "
            "or type **agent** / **support** if you need help."
        ),
        "arabic": (
            "نواجه صعوبة في الوصول إلى بيانات الفاتورة حاليًا. يرجى المحاولة بعد قليل، "
            "أو اكتب **agent** / **support** للمساعدة."
        ),
        "roman_urdu": (
            "Abhi invoice data access mein masla aa raha hai. Thori dair baad dobara try karein, "
            "ya **agent** / **support** likhein."
        ),
    },
    "tracking_lookup_error": {
        "english": (
            "I couldn't pull tracking info for that number right now. Please double-check it, "
            "or type **agent** / **support** for help."
        ),
        "arabic": (
            "لم أتمكن من الحصول على معلومات التتبع لهذا الرقم الآن. يرجى التحقق منه، "
            "أو اكتب **agent** / **support** للمساعدة."
        ),
        "roman_urdu": (
            "Abhi is tracking number ki info nahi mil rahi. Number check karein, "
            "ya **agent** / **support** likhein."
        ),
    },
    "cannot_find_order_help": {
        "english": (
            "No worries — here's how to find it quickly:\n\n"
            "1. *Check your inbox and spam folder* for an email from Arabia Dropship with the "
            "subject \"Order confirmation\" — the order number is in the subject and body.\n"
            "2. *Check your WhatsApp history* for messages from us when the order was placed.\n"
            "3. *Search by email*: just reply with the email address you used when ordering and "
            "I'll look it up for you.\n\n"
            "If you still can't find it, type *agent* and a human will take over."
        ),
        "arabic": (
            "لا مشكلة — إليك طرقاً سريعة للعثور عليه:\n\n"
            "1. *تحقق من بريدك الإلكتروني وصندوق الرسائل غير المرغوب فيها* بحثاً عن رسالة من Arabia "
            "Dropship بعنوان \"تأكيد الطلب\" — رقم الطلب موجود في الموضوع والمحتوى.\n"
            "2. *تحقق من محادثات واتساب* من وقت إنشاء الطلب.\n"
            "3. *ابحث عبر البريد الإلكتروني*: أرسل البريد الإلكتروني الذي استخدمته عند الطلب وسأبحث لك.\n\n"
            "إذا لم تجد، اكتب *agent* وسيتولى أحد الموظفين المحادثة."
        ),
        "roman_urdu": (
            "Koi baat nahi — jaldi dhoondhne ke tareeqay:\n\n"
            "1. *Inbox aur spam folder check karein* — Arabia Dropship ki \"Order confirmation\" "
            "subject wali email mein order number mil jayega.\n"
            "2. *WhatsApp history check karein* — order place karte waqt bheji gayi messages.\n"
            "3. *Email se dhundhwaein*: aap wo email bhejein jo order ke waqt use ki thi, main dekh "
            "leta hoon.\n\n"
            "Agar phir bhi na miley to *agent* likhein, aap ko insaan connect kar doonga."
        ),
    },
    "orders_period_lookup_error": {
        "english": (
            "I couldn't fetch orders for that period right now. Please try again in a moment, "
            "or type **agent** / **support** for help."
        ),
        "arabic": (
            "لم أتمكن من جلب الطلبات لهذه الفترة الآن. يرجى المحاولة بعد قليل، "
            "أو اكتب **agent** / **support** للمساعدة."
        ),
        "roman_urdu": (
            "Abhi is period ke orders nahi aa rahe. Thori dair baad try karein, "
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
    "trending_intro_first": {
        "english": "Here are the trending products in {country}:",
        "arabic": "إليك المنتجات الرائجة في {country}:",
        "roman_urdu": "Yeh hain {country} ke trending products:",
    },
    "trending_intro_more": {
        "english": "Here are more trending products in {country}:",
        "arabic": "إليك المزيد من المنتجات الرائجة في {country}:",
        "roman_urdu": "Yeh hain aur trending products {country} ke liye:",
    },
    "trending_intro_first_category": {
        "english": "Here are the trending {category} products in {country}:",
        "arabic": "إليك منتجات {category} الرائجة في {country}:",
        "roman_urdu": "Yeh hain {country} ke trending {category} products:",
    },
    "trending_intro_more_category": {
        "english": "Here are more trending {category} products in {country}:",
        "arabic": "إليك المزيد من منتجات {category} الرائجة في {country}:",
        "roman_urdu": "Yeh hain aur {category} trending products {country} ke liye:",
    },
    "trending_footer_first_has_more": {
        "english": "Would you like to see more products? Just type \"show me more\".",
        "arabic": "هل تريد رؤية المزيد من المنتجات؟ فقط اكتب \"show me more\".",
        "roman_urdu": "Aur products dekhna chahen ge? Bas \"show me more\" likhein.",
    },
    "trending_footer_first_only": {
        "english": (
            "These are all the trending products in {country} right now.\n\n"
            "Would you like me to help you with something else? You can also type \"agent\" to speak with a human."
        ),
        "arabic": (
            "هذه كل المنتجات الرائجة في {country} حالياً.\n\n"
            "هل تريد مساعدة في شيء آخر؟ يمكنك أيضاً كتابة \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Abhi {country} ke liye yeh saare trending products hain.\n\n"
            "Aur kuch madad chahiye? \"agent\" likh kar human se baat kar sakte hain."
        ),
    },
    "trending_footer_more_has_more": {
        "english": (
            "Would you like to see more? Type \"show me more\" or ask about a specific product by number."
        ),
        "arabic": (
            "هل تريد المزيد؟ اكتب \"show me more\" أو اسأل عن منتج محدد برقمه."
        ),
        "roman_urdu": (
            "Aur dekhna hai? \"show me more\" likhein ya number se kisi product ke baare mein pooch lein."
        ),
    },
    "trending_footer_more_end": {
        "english": (
            "These are all the trending products in {country} right now.\n\n"
            "Would you like me to help you with something else? You can also type \"agent\" to speak with a human."
        ),
        "arabic": (
            "هذه كل المنتجات الرائجة في {country} حالياً.\n\n"
            "هل تريد مساعدة في شيء آخر؟ يمكنك أيضاً كتابة \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Abhi {country} ke liye yeh saare trending products hain.\n\n"
            "Aur kuch madad chahiye? \"agent\" likh kar human se baat kar sakte hain."
        ),
    },
    "trending_followup_suggestions": {
        "english": (
            "\n\nYou might also want to ask:\n"
            "• Show trending products in {other_a}\n"
            "• Show trending products in {other_b}\n"
            "• Tell me about a product by its list number\n\n"
            "Is there anything else I can help with?"
        ),
        "arabic": (
            "\n\nيمكنك أيضًا أن تسأل:\n"
            "• عرض المنتجات الرائجة في {other_a}\n"
            "• عرض المنتجات الرائجة في {other_b}\n"
            "• أخبرني عن منتج برقمه في القائمة\n\n"
            "هل هناك أي شيء آخر يمكنني المساعدة به؟"
        ),
        "roman_urdu": (
            "\n\nAap yeh bhi pooch sakte hain:\n"
            "• {other_a} mein trending products dikhao\n"
            "• {other_b} mein trending products dikhao\n"
            "• List number se kisi product ke baare mein batao\n\n"
            "Kya aur koi madad chahiye?"
        ),
    },
    "trending_no_more_pages": {
        "english": (
            "There are no more trending products to show for {country} right now. "
            "Ask me anything else, pick trending products again for another country, or type \"agent\" for a human."
        ),
        "arabic": (
            "لا توجد منتجات رائجة إضافية لعرضها لـ {country} حالياً. "
            "اسأل عن أي شيء آخر، أو اختر دولة أخرى للمنتجات الرائجة، أو اكتب \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Abhi {country} ke liye aur trending products load karne ko nahi bacha. "
            "Kuch aur pooch lein, dobara trending products try karein, ya \"agent\" likhein."
        ),
    },
    "trending_product_detail_ok": {
        "english": (
            "📦 {name}\n💰 {price_line}\n\n📝 {description}\n\n"
            "For stock, bulk pricing, or shipping help, type \"agent\" to reach a human."
        ),
        "arabic": (
            "📦 {name}\n💰 {price_line}\n\n📝 {description}\n\n"
            "لمخزون أو تسعير بالجملة أو الشحن، اكتب \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "📦 {name}\n💰 {price_line}\n\n📝 {description}\n\n"
            "Stock, bulk pricing, ya shipping ke liye \"agent\" likhein human se baat ke liye."
        ),
    },
    "trending_product_detail_missing": {
        "english": (
            "I don’t have a catalog description for {name} yet.\n\n"
            "For specs, stock, and pricing, type \"agent\" to reach a support agent — "
            "or ask another question."
        ),
        "arabic": (
            "لا يوجد وصف مسجّل في الكتالوج لـ {name} حتى الآن.\n\n"
            "للمواصفات أو المخزون أو الأسعار، اكتب \"agent\" للتحدث مع الدعم — أو اسأل سؤالاً آخر."
        ),
        "roman_urdu": (
            "Abhi catalog mein {name} ka koi description nahi hai.\n\n"
            "Specs, stock, pricing ke liye \"agent\" likhein support se — ya koi aur sawal pooch lein."
        ),
    },
    "trending_product_detail_handoff": {
        "english": (
            "I'd be happy to help you with more details about {product_name}.\n\n"
            "Let me connect you with a support agent who can provide complete information including "
            "availability, bulk pricing, and shipping options.\n\n"
            "Please wait a moment."
        ),
        "arabic": (
            "يسعدني مساعدتك في المزيد من التفاصيل عن {product_name}.\n\n"
            "دعني أوصلك بأحد موظفي الدعم ليقدم لك معلومات كاملة تشمل التوفر والأسعار بالجملة وخيارات الشحن.\n\n"
            "يرجى الانتظار لحظة."
        ),
        "roman_urdu": (
            "{product_name} ki mazeed details mein madad karne ko tayyar hoon.\n\n"
            "Main aap ko support agent se connect karta hoon — availability, bulk pricing, aur shipping "
            "options ka poora jawab mil jaye ga.\n\n"
            "Thora intezar karein."
        ),
    },
    "trending_product_not_matched": {
        "english": (
            "I couldn’t match that to one of the trending products in this list. "
            "Try a list number (e.g. 3 or \"product 3\"), type \"show me more\", or type \"agent\" for a human."
        ),
        "arabic": (
            "لم أستطع ربط ذلك بأحد المنتجات الرائجة في هذه القائمة. "
            "جرّب رقم المنتج (مثل 3 أو \"product 3\")، أو اكتب \"show me more\"، أو \"agent\" للتحدث مع موظف."
        ),
        "roman_urdu": (
            "Isay is trending list se match nahi kar saka. "
            "List number try karein (jaise 3 ya \"product 3\"), \"show me more\" likhein, ya \"agent\" human ke liye."
        ),
    },
    "trending_no_products": {
        "english": (
            "There aren't any trending products listed for {country} yet — our team is "
            "still adding them. In the meantime, try another market or ask me anything else."
        ),
        "arabic": (
            "لا توجد منتجات رائجة مسجّلة لـ {country} حتى الآن — فريقنا يعمل على إضافتها. "
            "في غضون ذلك، جرّب سوقاً آخر أو اسألني أي شيء آخر."
        ),
        "roman_urdu": (
            "Abhi {country} ke liye koi trending product list nahi hai — team add kar rahi "
            "hai. Aap doosra market try karein ya koi aur sawal pooch lein."
        ),
    },
    "trending_no_products_category": {
        "english": "No trending {category} products are listed for {country} yet. Try another category/country or ask me anything else.",
        "arabic": "لا توجد منتجات {category} رائجة مسجّلة لـ {country} حالياً. جرّب فئة/دولة أخرى أو اسألني أي شيء آخر.",
        "roman_urdu": "Abhi {country} mein {category} category ke trending products list nahi hain. Doosri category/country try karein ya koi aur sawal pooch lein.",
    },
    "non_trending_unavailable": {
        "english": (
            "I only showcase our *trending* picks here — the non-trending catalog "
            "isn't available through the bot. For the full catalog please sign in "
            "to your seller dashboard.\n\n"
            "Would you like to see the trending products instead, or is there "
            "anything else I can help with?"
        ),
        "arabic": (
            "أعرض هنا فقط المنتجات *الرائجة* — الكتالوج الكامل غير متوفر عبر البوت. "
            "للاطلاع على كل المنتجات يُرجى تسجيل الدخول إلى لوحة البائع.\n\n"
            "هل تود رؤية المنتجات الرائجة بدلاً من ذلك، أم يمكنني مساعدتك بشيء آخر؟"
        ),
        "roman_urdu": (
            "Main yahan sirf *trending* products dikhata hoon — baqi ke products "
            "bot par available nahi hain. Poora catalogue dekhne ke liye apne "
            "seller dashboard mein login karein.\n\n"
            "Kya aap trending products dekhna chahenge, ya kisi aur cheez mein madad chahiye?"
        ),
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
