"""Spelling slips a visitor notices: well-known misspellings, a few wrong set
phrases, and one word spelled two different ways on the same page.

Deliberately conservative. Every word in MISSPELLINGS is wrong in English with
no second meaning, and the checks only run on pages that are in English - a
word that is a typo in English is often correct in another language.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

from .models import Finding

# wrong -> right. Only words that are never correct English (no British/American
# pairs such as cancelled/canceled, no rare real words such as "calender").
MISSPELLINGS: Dict[str, str] = {
    "accomodate": "accommodate", "accomodation": "accommodation", "acommodate": "accommodate",
    "acheive": "achieve", "acheived": "achieved", "achived": "achieved",
    "acknowlege": "acknowledge", "acount": "account", "acounts": "accounts",
    "accross": "across", "acess": "access", "acces": "access", "accesible": "accessible",
    "adress": "address", "adresses": "addresses", "adressed": "addressed",
    "affilate": "affiliate", "affliate": "affiliate", "afiliate": "affiliate",
    "affilates": "affiliates", "affliates": "affiliates",
    "aggrement": "agreement", "aggreement": "agreement", "agreemnt": "agreement",
    "agressive": "aggressive", "allready": "already", "alot": "a lot",
    "aplication": "application", "applicaton": "application", "apparant": "apparent",
    "aparent": "apparent", "appearence": "appearance", "arguement": "argument",
    "assesment": "assessment", "availible": "available", "avaliable": "available",
    "availabe": "available", "basicly": "basically", "becuase": "because",
    "begining": "beginning", "beggining": "beginning", "beleive": "believe",
    "belive": "believe", "benifit": "benefit", "benifits": "benefits",
    "buisness": "business", "bussiness": "business", "busines": "business",
    "calandar": "calendar", "carefull": "careful", "catagory": "category",
    "catagories": "categories", "cemetary": "cemetery", "changable": "changeable",
    "cheif": "chief", "collegue": "colleague", "collegues": "colleagues",
    "comming": "coming", "commision": "commission", "commisions": "commissions",
    "comission": "commission", "comissions": "commissions", "commited": "committed",
    "commitee": "committee", "comittee": "committee", "comparision": "comparison",
    "competetive": "competitive", "competitve": "competitive", "completly": "completely",
    "conection": "connection", "concious": "conscious", "conditons": "conditions",
    "condtions": "conditions", "consistant": "consistent", "contraversy": "controversy",
    "convinient": "convenient", "curiousity": "curiosity", "custumer": "customer",
    "dashbord": "dashboard", "definately": "definitely", "definatly": "definitely",
    "definitly": "definitely", "delivary": "delivery", "descripton": "description",
    "desicion": "decision", "diffrent": "different", "diferent": "different",
    "dificult": "difficult", "dilema": "dilemma", "dissapear": "disappear",
    "dissapoint": "disappoint", "dissapointed": "disappointed", "earnigns": "earnings",
    "efficent": "efficient", "embarass": "embarrass", "embarassing": "embarrassing",
    "enterpreneur": "entrepreneur", "entrepeneur": "entrepreneur",
    "enviroment": "environment", "enviromental": "environmental",
    "equiptment": "equipment", "exellent": "excellent", "excelent": "excellent",
    "existance": "existence", "experiance": "experience", "experiances": "experiences",
    "exprience": "experience", "familar": "familiar", "feild": "field",
    "finaly": "finally", "fortunatly": "fortunately", "foward": "forward",
    "fowarded": "forwarded", "fourty": "forty", "freind": "friend", "freinds": "friends",
    "fullfill": "fulfill", "garantee": "guarantee", "gaurantee": "guarantee",
    "guarentee": "guarantee", "gaurd": "guard", "goverment": "government",
    "grammer": "grammar", "happend": "happened", "harrass": "harass",
    "hierachy": "hierarchy", "imediate": "immediate", "immediatly": "immediately",
    "imediately": "immediately", "incidently": "incidentally", "independant": "independent",
    "intrested": "interested", "interupt": "interrupt", "knowlege": "knowledge",
    "langauge": "language", "languge": "language", "lenght": "length",
    "liason": "liaison", "libary": "library", "liesure": "leisure", "lisence": "license",
    "maintainance": "maintenance", "maintenence": "maintenance", "managment": "management",
    "mangement": "management", "mesage": "message", "messsage": "message",
    "millenium": "millennium", "minumum": "minimum", "mispell": "misspell",
    "neccessary": "necessary", "necessery": "necessary", "neccesary": "necessary",
    "noticable": "noticeable", "notifcation": "notification", "notificaton": "notification",
    "ocasion": "occasion", "occassion": "occasion", "occassionally": "occasionally",
    "occured": "occurred", "occuring": "occurring", "occurence": "occurrence",
    "occurance": "occurrence", "oppurtunity": "opportunity", "oportunity": "opportunity",
    "oppertunity": "opportunity", "orignal": "original", "parliment": "parliament",
    "pasword": "password", "paswords": "passwords", "passowrd": "password",
    "paymant": "payment", "paymnet": "payment", "peice": "piece",
    "perfomance": "performance", "performace": "performance", "permanant": "permanent",
    "persistant": "persistent", "personel": "personnel", "posession": "possession",
    "possesion": "possession", "posible": "possible", "potentialy": "potentially",
    "prefered": "preferred", "prefrence": "preference", "privelege": "privilege",
    "priveleges": "privileges", "priviledge": "privilege", "probaly": "probably",
    "proccess": "process", "procces": "process", "proffesional": "professional",
    "profesional": "professional", "professionnal": "professional", "promiss": "promise",
    "pronounciation": "pronunciation", "publically": "publicly",
    "questionaire": "questionnaire", "realy": "really", "reccomend": "recommend",
    "recomend": "recommend", "recommand": "recommend", "recepient": "recipient",
    "recipent": "recipient", "reciept": "receipt", "recieve": "receive",
    "recieved": "received", "recieves": "receives", "recieving": "receiving",
    "recived": "received", "refered": "referred", "referal": "referral",
    "referals": "referrals", "registartion": "registration", "registraion": "registration",
    "registeration": "registration", "regestration": "registration", "relevent": "relevant",
    "relize": "realize", "religous": "religious", "remeber": "remember",
    "repitition": "repetition", "reponse": "response", "resposne": "response",
    "responsability": "responsibility", "resturant": "restaurant", "rythm": "rhythm",
    "safty": "safety", "secuirty": "security", "securty": "security", "sence": "sense",
    "seperate": "separate", "seperately": "separately", "servise": "service",
    "sevice": "service", "shedule": "schedule", "sieze": "seize", "similiar": "similar",
    "simmilar": "similar", "sincerly": "sincerely", "speach": "speech",
    "statisitcs": "statistics", "statistcs": "statistics", "strenght": "strength",
    "subcribe": "subscribe", "subscibe": "subscribe", "submited": "submitted",
    "sumbit": "submit", "succeded": "succeeded", "sucess": "success", "succes": "success",
    "succesful": "successful", "successfull": "successful", "sucessful": "successful",
    "succesfully": "successfully", "sucessfully": "successfully",
    "suggesstion": "suggestion", "suport": "support", "supress": "suppress",
    "suprise": "surprise", "tecnology": "technology", "tempory": "temporary",
    "temporarly": "temporarily", "thier": "their", "throught": "through",
    "togheter": "together", "tommorow": "tomorrow", "tommorrow": "tomorrow",
    "tomorow": "tomorrow", "tounge": "tongue", "tranfer": "transfer", "trasfer": "transfer",
    "transaciton": "transaction", "transation": "transaction", "transfered": "transferred",
    "truely": "truly", "twelth": "twelfth", "unfortunatly": "unfortunately",
    "unfortunetly": "unfortunately", "untill": "until", "upto": "up to",
    "usefull": "useful", "vaccum": "vacuum", "verfication": "verification",
    "verifcation": "verification", "wheather": "whether", "whitch": "which",
    "wich": "which", "wierd": "weird", "witdraw": "withdraw", "widthdraw": "withdraw",
    "withdrawl": "withdrawal", "withdrawel": "withdrawal", "writting": "writing",
    "writen": "written", "yeild": "yield", "youre": "you're", "teh": "the",
    "taht": "that", "thsi": "this", "yuor": "your",
}

# Pairs where both spellings are correct English (British and American).
VALID_PAIRS = {frozenset(p) for p in (
    ("fulfill", "fulfil"), ("enroll", "enrol"), ("enrollment", "enrolment"),
    ("install", "instal"), ("installment", "instalment"), ("skillful", "skilful"),
    ("willful", "wilful"), ("distill", "distil"), ("instill", "instil"), ("appall", "appal"),
    ("dullness", "dulness"), ("fullness", "fulness"), ("deserts", "desserts"),
    ("desert", "dessert"), ("woollen", "woolen"), ("jewellery", "jewelery"),
)}

# A doubled letter right before one of these endings is ordinary English
# (planned/planed, filling/filing), so those pairs are left alone.
_SUFFIXES = ("ing", "ings", "ed", "er", "ers", "est", "en", "y", "ie", "ies", "ish", "able")

_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
_FORGET = re.compile(r"forget\s+(your\s+)?password\s*\??", re.I)
_BODY_PHRASES = [
    (re.compile(r"\b(could|should|would|must)\s+of\b(?!\s+course)", re.I),
     lambda m: f"{m.group(1)} have"),
    (re.compile(r"\byour\s+welcome(?=\s*[.!]|\s*$)", re.I | re.M), lambda m: "you're welcome"),
]
_ENGLISH = {"the", "and", "to", "of", "a", "in", "is", "you", "your", "for", "with", "on",
            "our", "we", "are", "this", "that", "it", "be", "as", "or", "by", "from", "at"}


def _looks_english(lang: str, words: List[str]) -> bool:
    lang = (lang or "").strip().lower()
    if lang and not lang.startswith("en"):
        return False
    if lang.startswith("en"):
        return True
    if len(words) < 30:
        return False
    hits = sum(1 for w in words if w.lower() in _ENGLISH)
    return hits / len(words) > 0.05


def _same_case(right: str, shown: str) -> str:
    if shown.isupper() and len(shown) > 1:
        return right.upper()
    if shown[:1].isupper():
        return right[:1].upper() + right[1:]
    return right


def _context(text: str, word: str) -> str:
    m = re.search(r"(?<![^\W\d_])" + re.escape(word) + r"(?![^\W\d_])", text, re.I)
    if not m:
        return ""
    a, b = max(0, m.start() - 50), min(len(text), m.end() + 50)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def _where(word: str, ui_words: set) -> str:
    return " It is in a menu, button, link or heading, so every visitor sees it." \
        if word.lower() in ui_words else ""


def check(url: str, body_text: str, ui_strings: Optional[List[str]] = None,
          lang: str = "", limit: int = 12) -> List[Finding]:
    text = body_text or ""
    ui = [s for s in (ui_strings or []) if isinstance(s, str) and s.strip()]
    words = _WORD.findall(text + "\n" + "\n".join(ui))
    if not _looks_english(lang, words):
        return []
    counts = Counter(w.lower() for w in words)
    shown: Dict[str, str] = {}
    for w in words:
        shown.setdefault(w.lower(), w)
    ui_words = {w.lower() for s in ui for w in _WORD.findall(s)}
    out: List[Finding] = []

    # 1. well-known misspellings
    for low in sorted(counts, key=lambda k: (k not in ui_words, k)):
        right = MISSPELLINGS.get(low)
        if not right:
            continue
        wrong = shown[low]
        fix = _same_case(right, wrong)
        out.append(Finding(
            severity="low", category="Content",
            title=f"Spelling mistake: '{wrong}' should be '{fix}'",
            detail=f"'{wrong}' is a common misspelling of '{fix}'." + _where(low, ui_words),
            url=url,
            evidence={"word": wrong, "suggestion": fix, "times_on_page": counts[low],
                      "context": _context(text, wrong) or wrong},
            how_to_fix=f"Change '{wrong}' to '{fix}' in the page text."))

    # 2. set phrases
    for s in ui:
        s2 = " ".join(s.split())
        if _FORGET.fullmatch(s2):
            fix = re.sub(r"(?i)forget", lambda m: "Forgot" if m.group(0)[0].isupper() else "forgot", s2)
            out.append(Finding(
                severity="low", category="Content",
                title=f"Wrong phrase: '{s2}' should be '{fix}'",
                detail="The link for a lost password reads 'Forget', which tells the visitor to "
                       "forget it. The usual wording is 'Forgot password?'.",
                url=url, evidence={"text": s2, "suggestion": fix},
                how_to_fix=f"Change the text to '{fix}'."))
            break
    for rx, make in _BODY_PHRASES:
        m = rx.search(text)
        if m:
            fix = make(m)
            out.append(Finding(
                severity="low", category="Content",
                title=f"Wrong phrase: '{m.group(0)}' should be '{fix}'",
                detail=f"'{m.group(0)}' is a common slip for '{fix}'.",
                url=url, evidence={"context": _context(text, m.group(0)) or m.group(0)},
                how_to_fix=f"Change it to '{fix}'."))

    # 3. one word spelled two ways on the same page (COMMISION next to COMMISSION)
    seen_pairs = set()
    for low in list(counts):
        if not (low.isascii() and low.isalpha() and len(low) >= 7):
            continue
        for i in range(len(low) - 1):
            if low[i] != low[i + 1]:
                continue
            if low[i + 2:] in _SUFFIXES:
                continue
            single = low[:i + 1] + low[i + 2:]
            if len(single) < 6 or single not in counts:
                continue
            pair = frozenset((low, single))
            if pair in seen_pairs or pair in VALID_PAIRS:
                continue
            if low in MISSPELLINGS or single in MISSPELLINGS:
                continue          # already reported above with the right spelling
            seen_pairs.add(pair)
            rare, common = (single, low) if counts[single] <= counts[low] else (low, single)
            out.append(Finding(
                severity="low", category="Content",
                title=f"Same word spelled two ways: '{shown[rare]}' and '{shown[common]}'",
                detail=f"The page writes '{shown[rare]}' {counts[rare]}× and '{shown[common]}' "
                       f"{counts[common]}×. One of them is a typo - most likely the rarer "
                       f"'{shown[rare]}'." + _where(rare, ui_words),
                url=url,
                evidence={"spellings": {shown[rare]: counts[rare], shown[common]: counts[common]},
                          "context": _context(text, shown[rare]) or shown[rare]},
                how_to_fix="Pick the correct spelling and use it everywhere."))
    return out[:limit]
