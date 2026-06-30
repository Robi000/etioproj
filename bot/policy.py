from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from accounts.models import TelegramUser
from bot.models import BotRegistrationSession
from bot.handler_modules.utils import TelegramUpdateContext


POLICY_VERSION = "2026-06-25"
POLICY_BLOCK_MINUTES = 2

POLICY_TEXT = """
👋 እንኳን ወደ መገናኛችን በደህና መጡ!

አገልግሎታችንን ከመጠቀምዎ በፊት እባክዎ የሚከተሉትን ህጎች ያንብቡ።

..... በመጀመሪያ አገልግሎታችን ለአገልግሎት ሰጪዎችም ለተገልጋይም ነፃ ነው። .....



🔞🔞🔞 18 አመት እና ከዚያ በላይ ብቻ 🔞🔞🔞
ይህ አገልግሎት መስጫ 18 አመት እና ከዚያ በላይ ላሉ ሰዎች ብቻ ነው። 18 አመት በታች ያሉ ሰዎች መመዝገብም ሆነ መጠቀም አይችሉም።

🔐🔐🔐 ሚስጥር አጠባበቅ 🔐🔐🔐
ኩባንያችን የእርሶን ሚስጥር ይጠብቃል። በዚህ አገልግሎት ውስጥ የሚከተሉት መረጃዎች ሲሰበሰቡ ለሰዎች የሚላኩትና ለሰዎች ማይላኩት እንደሚከተለው ይቀርባሉ። 

->> ለደንበኞች የሚላኩ፡
1) ፎቶ፡ የፎቶ መረጃ የምንወስድ ሲሆን ፊትዎ የተሸፈነ የአካላትዎ ፎቶ እንዲልኩ እንመክራለን። 
2) የቴሌግራም username: ደንበኛ በቀላሉ እንዲያገኝዎ የተመዘገቡበትን ቴሌግራም username እንልካለን።
3) ለዚህ ስራ የሚጠቀሙበት ስልክ ቁጥር ካልዎት፡ ይሄ አስገዳጅ አይደለም። ቁጥሩ አለኝ ካሉ ይላካል ከሌልዎት የቴሌግራም Username ብቻ ለደንበኛ ይላካል። 
4) የአግልግሎትዎ ሂሳብ፡ የአገልግሎት ዋጋዎትን ለደንበኛ ይላካል። ለራስዎ የአግልግሎት ዋጋ የሚያወጡት ራስዎ ኖት። 

ለደንበኛ የማይላኩ፡
1) የስልክ ቁጥር፡ የቴሌግራም አካውንቶ የወጣበት ስልክ ቁጥር የምንሰበስብ ሲሆን ኩባንያው እርሶን ብቻ እንዲያገኝ ይረዳል። ይሄ ለሌላ ሰው አይላክም ( እርሶ እንዲላክ በድጋሚ መላክ የሚችለው ስልክ ቁጥር ውስጥ በድጋሚ ካላስገቡት)
2) GPS መረጃ፡ ይሄ ለደንበኛ አይላክም። ይሄ እርሶ ባሉበት ከተማ ብቻ የሚገኝ ደንበኛ ብቻ እንዲያወራዎት ያገልግላል። የእርሶ ፕሮፋይል ከሚኖሩበት ከተማ ውጭ ሌላ ሰው እንዳይጠይቆት ያገለግላል።


📸📸📸 እውነተኛ ፎቶ ብቻ 📸📸📸
የሚሰጡን  ፎቶ የራስዎ መሆን አለበት።  የሚከተሉትንም ህጎች ማክበር አለበት። ፎቶ በሚለቁበት ጊዜ የፊት ክፍሎ እንዲሸፈን እንመክራለን...

❌ የሚለቁት ፎቶ ምንም አማላይ ቢሆንም ነገር ግን የጡት ጥቁር የሚታይበት ፣ የእምስ ክፍል የሚታይበት መሆን አይችልም። 
❌ ከኢንተርኔት የወረደ ፎቶ አይፈቀድም
❌ የሌላ ሰው ፎቶ አይፈቀድም

የሐሰት ፎቶ የሚጠቀም ተጠቃሚ በቋሚነት ሊታገድ ይችላል።



💰💰💰 ትክክለኛ መረጃ ያቅርቡ 💰💰💰
አገልግሎት ሰጪዎች አገልግሎት የሚሰጡበት ዋጋ በፃፉት ዋጋ የማገልገል ግዴታ አለብዎት።  የሚፅፉት የአገልግሎት ዋጋ ግን የሆቴል ፣ የወሊድ መቆጣጠሪያ ማካተት የለበትም። የትራንስፖርት ዋጋ ከደንበኛ ጋር በስምምነት ሲካሄድ ከ 1000 ብር በላይ መሆን የለበትም። 

ደንበኛም ለአገልግሎት ሰጪ ተገቢውን ክፍያ የመፈፀም እንደ ስምምነትዎ እስከ 30% ቀብድ የማስያዝ ግዴታ አለብዎ።  የቀብድ አከፋፈል በስምምነት ሲሆን  ያለ ቀብድ ከመስራት እስከመረጡት አገልግሎት ዋጋ 30% ድረስ በስምምነት በጨረስ ይችላሉ። ለትራንስፖርት ቀብድ አይታሰብም።



🎥🎥🎥 የማንነት ማረጋገጫ 🎥🎥🎥
በማንኛውም ጊዜ  አስፈላጊ ሆኖ ከተገኘ በTelegram Video Call ማንነትዎን ለማረጋገጥ እንደሚስማሙ ይቆጠራሉ። በምንደውልበት ጊዜም የእርሶን ገፅታ (በልብስ)  ልንጠይቅ እንችላለን። ከጠየቅን ቦሃላ ግን የማረጋገጫ ባጅ በአካውንቶ ላይ እናደርጋለን። 



⚠️⚠️⚠️ ቅሬታዎች ⚠️⚠️⚠️
በእርስዎ ላይ ብዙ ትክክለኛ ቅሬታዎች በተለይ ከክፍያ ጋር በተያያዘ  ከቀረቡ የአገልግሎት ሰጪም የአገልግሎት ተቀባይም Access ለጊዜው ወይም በቋሚነት ሊዘጋ ይችላል።



 📨📨 የግንኙነት ጥያቄ (Contact Request) ገደብ 📨📨
በየቀኑ የመጀመሪያዎቹ 2 ጥያቄዎች ወዲያውኑ ይላካሉ።
ከዚያ በኋላ:
• 3ኛ → 20 ደቂቃ ጥበቃ
• 4ኛ → 30 ደቂቃ ጥበቃ
• 5ኛ → 50 ደቂቃ ጥበቃ
• 6ኛ → 60 ደቂቃ ጥበቃ
🚫 በአንድ ቀን ከ6 በላይ እንዲሁም በሳምንት ከ7 በላይ አዲስ የግንኙነት ጥያቄ መላክ አይቻልም።

የሚከተሉት ግን ጥያቄ እንደማቅረብ አይቆጠሩም፦
✅ ፕሮፋይል ማየት
✅ Like ወይም Dislike ማድረግ


🤝🤝🤝 አገልግሎት ሰጪዎች ለደንበኞች ምላሽ መስጠት አለባቸው 🤝🤝🤝
ተደጋጋሚ ሁኔታ ላይ የደንበኞችን ጥያቄ መቀበል ካልፈለጉ ወይም ካልመለሱ ገደብ ወይም ቋሚ እገዳ ሊደረግብዎ ይችላል። አገልግሎት በማይሰጡበት ጊዜ ከእይታ መውጫውን ነክተው መውጣት አለብዎ። ከእይታ ሲወጡ ለማንም ደበንበኛ አይታዩም። 


🛡️🛡️🛡️ ደህንነትዎን ይጠብቁ 🛡️🛡️🛡️
እኛ የምናደርገው ሰዎችን ማገናኘት ብቻ ነው።
ከሁለቱ ወገኖች መካከል የስልክ ቁጥር፣ Telegram ወይም ሌላ የግንኙነት መረጃ ከተለዋወጠ በኋላ የሚፈጠር ማንኛውም አለመግባባት  የተጠቃሚዎች ኃላፊነት ነው። ኩባንያው ከዚያ በኋላ ለሚፈጠር ማንኛውም ጉዳይ ተጠያቂ አይሆንም።


📚📚📚 3 አጭር ጥያቄዎች  📚📚📚
ህጎቹን እንደተረዱ ለማረጋገጥ 3 አጭር ጥያቄዎች ይጠየቃሉ።
✅ ሶስቱንም በትክክል መመለስ ያስፈልጋል።
❌ ከተሳሳቱ 2 ደቂቃ የማንበቢያ ጊዜ ይሰጥዎታል እና ከዚያ በኋላ እንደገና መሞከር ይችላሉ።
✅ በመቀጠል እነዚህን ህጎች አንብበው እንደተረዱ እና ለመከተል እንደሚስማሙ ያረጋግጣሉ።



፟🛌🛌🛌 አሪፍ የሴክስ ጊዜ እንዲያሳልፉ እንመኝሎታለን። 🛌🛌🛌
"""



@dataclass(frozen=True)
class PolicyQuestion:
    prompt: str
    expected_answer: str


POLICY_QUESTIONS = [
    PolicyQuestion(
        prompt="Can customers see provider contact information before approval?",
        expected_answer="no",
    ),
    PolicyQuestion(
        prompt="Must providers confirm they are available before the request goes to admin?",
        expected_answer="yes",
    ),
    PolicyQuestion(
        prompt="Is it okay to send fake or spam contact requests?",
        expected_answer="no",
    ),
]


def get_or_create_policy_user(context: TelegramUpdateContext) -> TelegramUser | None:
    if context.telegram_user_id is None:
        return None

    telegram_user, _ = TelegramUser.objects.get_or_create(
        telegram_id=context.telegram_user_id,
        defaults={
            "telegram_username": context.username,
            "first_name": context.first_name,
        },
    )

    changed_fields = []
    if context.username and telegram_user.telegram_username != context.username:
        telegram_user.telegram_username = context.username
        changed_fields.append("telegram_username")
    if context.first_name and telegram_user.first_name != context.first_name:
        telegram_user.first_name = context.first_name
        changed_fields.append("first_name")

    if changed_fields:
        changed_fields.append("updated_at")
        telegram_user.save(update_fields=changed_fields)

    return telegram_user


def user_has_policy_access(telegram_user_id: int | None) -> bool:
    if telegram_user_id is None:
        return False

    telegram_user = TelegramUser.objects.filter(
        telegram_id=telegram_user_id,
    ).first()
    return bool(
        telegram_user
        and telegram_user.has_accepted_policy(POLICY_VERSION)
    )


def start_policy_session(context: TelegramUpdateContext) -> BotRegistrationSession | None:
    if context.telegram_user_id is None or context.chat_id is None:
        return None

    session, _ = BotRegistrationSession.objects.update_or_create(
        telegram_user_id=context.telegram_user_id,
        defaults={
            "chat_id": context.chat_id,
            "state": BotRegistrationSession.State.POLICY,
            "data": {
                "policy_version": POLICY_VERSION,
                "policy_question_index": 0,
                "policy_answers": [],
            },
        },
    )
    return session


def get_policy_session(telegram_user_id: int) -> BotRegistrationSession | None:
    return BotRegistrationSession.objects.filter(
        telegram_user_id=telegram_user_id,
        state=BotRegistrationSession.State.POLICY,
    ).first()


def get_current_question(session: BotRegistrationSession) -> tuple[int, PolicyQuestion]:
    index = int(session.data.get("policy_question_index", 0))
    index = min(max(index, 0), len(POLICY_QUESTIONS) - 1)
    return index, POLICY_QUESTIONS[index]


def answer_policy_question(
    telegram_user: TelegramUser,
    session: BotRegistrationSession,
    question_index: int,
    answer: str,
) -> tuple[bool, bool, str]:
    expected_index, question = get_current_question(session)
    normalized_answer = answer.strip().lower()

    if question_index != expected_index:
        return False, False, "Please answer the current question shown in the chat."

    if normalized_answer != question.expected_answer:
        telegram_user.policy_failed_attempts += 1
        telegram_user.policy_blocked_until = timezone.now() + timedelta(
            minutes=POLICY_BLOCK_MINUTES
        )
        telegram_user.save(
            update_fields=[
                "policy_failed_attempts",
                "policy_blocked_until",
                "updated_at",
            ]
        )
        session.data = {
            "policy_version": POLICY_VERSION,
            "policy_question_index": 0,
            "policy_answers": [],
        }
        session.save(update_fields=["data", "updated_at"])
        return False, False, "That answer was not correct."

    answers = list(session.data.get("policy_answers", []))
    answers.append(
        {
            "question_index": question_index,
            "answer": normalized_answer,
        }
    )

    next_index = expected_index + 1
    if next_index >= len(POLICY_QUESTIONS):
        telegram_user.policy_accepted_at = timezone.now()
        telegram_user.policy_version = POLICY_VERSION
        telegram_user.policy_failed_attempts = 0
        telegram_user.policy_blocked_until = None
        telegram_user.save(
            update_fields=[
                "policy_accepted_at",
                "policy_version",
                "policy_failed_attempts",
                "policy_blocked_until",
                "updated_at",
            ]
        )
        session.state = BotRegistrationSession.State.COMPLETED
        session.data = {
            "policy_version": POLICY_VERSION,
            "policy_passed": True,
        }
        session.save(update_fields=["state", "data", "updated_at"])
        return True, True, "Policy verification passed."

    data = session.data
    data["policy_answers"] = answers
    data["policy_question_index"] = next_index
    session.data = data
    session.save(update_fields=["data", "updated_at"])
    return True, False, "Correct."


def policy_block_is_active(telegram_user: TelegramUser) -> bool:
    return bool(
        telegram_user.policy_blocked_until
        and telegram_user.policy_blocked_until > timezone.now()
    )
