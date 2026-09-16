"""
Kisan Voice AI Assistant Router
Provides voice-first conversational agronomy support in Hindi, Marathi, and English.
Designed especially for rural farmers to ask farming questions by voice.
"""

import re
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.auth import get_optional_user
from backend.schemas import VoiceAssistantRequest, VoiceAssistantResponse, QuickPromptItem
from backend.ai_engine import AGRONOMY_KNOWLEDGE_BASE

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

# Multi-lingual crop keyword mappings
CROP_KEYWORDS: Dict[str, List[str]] = {
    "Tomato": ["tomato", "tamatar", "ಟೊಮೆಟೊ", "ತೊಮ್ಯಾಟೊ", "टमाटर", "टोमॅटो"],
    "Potato": ["potato", "aaloo", "aalu", "ಆಲೂಗಡ್ಡೆ", "ಆಲೂ", "आलू", "बटाटा", "बटाटे"],
    "Cotton": ["cotton", "kapas", "ಹತ್ತಿ", "कपास", "कापूस"],
    "Rice": ["rice", "paddy", "dhan", "ಅಕ್ಕಿ", "ಭತ್ತ", "धान", "चावल", "तांदूळ", "भात"],
    "Wheat": ["wheat", "gehu", "gehun", "ಗೋಧಿ", "गेहूं", "गहू"],
    "Chili": ["chili", "chilli", "mirch", "mirchi", "ಮೆಣಸಿನಕಾಯಿ", "ಮೆಣಸು", "ಖಾರ", "मिर्च", "मिरची"],
    "Maize": ["maize", "corn", "makka", "makai", "ಮೆಕ್ಕೆಜೋಳ", "ಜೋಳ", "ಮಕ್ಕ", "मक्का", "मका"],
    "Onion": ["onion", "pyaz", "pyaaz", "kanda", "ಈರುಳ್ಳಿ", "ಉಳ್ಳಾಗಡ್ಡಿ", "प्याज", "कांदा"]
}

# Symptom / Problem keyword mappings
PROBLEM_KEYWORDS: Dict[str, List[str]] = {
    "Early Blight": ["early blight", "target", "concentric", "rings", "ಅರ್ಲಿ ಬ್ಲೈಟ್", "ಮುಂಗಾರು ಅಂಗಮಾರಿ", "ಕಂದು ಕಲೆ", "अर्ली ब्लाइट", "अगेती झुलसा", "गोल धब्बे", "करपा"],
    "Late Blight": ["late blight", "water-soaked", "fuzzy", "ಲೇಟ್ ಬ್ಲೈಟ್", "ಹಿಂಗಾರು ಅಂಗಮಾರಿ", "ಬೂಜು ರೋಗ", "लेट ब्लाइट", "पछेती झुलसा", "सफेद फफूंद", "काळी पडणे"],
    "Leaf Curl": ["leaf curl", "curl", "tylcv", "ಎಲೆ ಮುದುರು ರೋಗ", "ಮುದುರು", "पत्ती मरोड़", "पत्ते मुड़ना", "चुरडा मुरडा", "बोकड्या"],
    "Fruit Borer": ["borer", "caterpillar", "worm", "hole", "ಕಾಯಿ ಕೊರೆಯುವ ಹುಳು", "ಹುಳು", "ತೂತು", "फल छेदक", "इल्ली", "सुंडी", "अळी", "बोंडअळी"],
    "Aphids / Whitefly": ["aphid", "aphids", "whitefly", "sticky", "ಜಿಗಿಹುಳು", "ಬಿಳಿ ನೊಣ", "ರಸಹೀರುವ ಕೀಟ", "ನುಸಿ", "माहू", "सफेद मक्खी", "मावा", "तुडतुडे", "रसशोषक"],
    "Rice Blast": ["blast", "spindle", "diamond", "ಬೆಂಕಿ ರೋಗ", "ಬ್ಲಾಸ್ಟ್", "ಕುತ್ತಿಗೆ ಬೆಂಕಿ ರೋಗ", "ब्लास्ट", "झोंका", "पत्ती ब्लास्ट"],
    "Rust": ["rust", "pustules", "yellow rust", "ತುಕ್ಕು ರೋಗ", "ರಸ್ಟ್", "रस्ट", "गेरुआ", "तांबेरा", "हळद्या"],
    "Purple Blotch": ["purple blotch", "purple", "ನೇರಳೆ ಕಲೆ ರೋಗ", "ಪರ್ಪಲ್ ಬ್ಲಾಚ್", "पर्पल ब्लॉच", "बैंगनी धब्बे", "जांभळा करपा"],
    "Fall Armyworm": ["armyworm", "whorl", "ಲದ್ದಿ ಹುಳು", "ಸೈನಿಕ ಹುಳು", "ಆರ್ಮಿವರ್ಮ್", "फॉल आर्मीवॉर्म", "सैनिक कीट", "लष्करी अळी"]
}

# Common Quick Voice Prompts (Kannada, English, Hindi)
QUICK_VOICE_PROMPTS: List[QuickPromptItem] = [
    # Kannada Prompts
    QuickPromptItem(
        category="Tomato Blight",
        crop="Tomato",
        prompt="ಟೊಮೆಟೊ ಎಲೆಗಳ ಮೇಲೆ ಕಂದು ಕಲೆಗಳು ಕಾಣುತ್ತಿವೆ, ಏನು ಮಾಡಬೇಕು?",
        language="Kannada"
    ),
    QuickPromptItem(
        category="Cotton Pest",
        crop="Cotton",
        prompt="ಹತ್ತಿ ಬೆಳೆಯಲ್ಲಿ ಬಿಳಿ ನೊಣ ಮತ್ತು ರಸಹೀರುವ ಕೀಟಗಳ ನಿಯಂತ್ರಣ ಹೇಗೆ?",
        language="Kannada"
    ),
    QuickPromptItem(
        category="Chili Curl",
        crop="Chili",
        prompt="ಮೆಣಸಿನಕಾಯಿ ಎಲೆ ಮುದುರು ರೋಗಕ್ಕೆ ಸಾವಯವ ಪರಿಹಾರವೇನು?",
        language="Kannada"
    ),
    QuickPromptItem(
        category="Rice Blast",
        crop="Rice",
        prompt="ಭತ್ತದ ಬೆಂಕಿ ರೋಗ ತಡೆಯಲು ಯಾವ ಔಷಧ ಸಿಂಪಡಿಸಬೇಕು?",
        language="Kannada"
    ),
    # English Prompts
    QuickPromptItem(
        category="Tomato Blight",
        crop="Tomato",
        prompt="My tomato leaves have dark brown circular spots, what should I spray?",
        language="English"
    ),
    QuickPromptItem(
        category="Organic Pest Control",
        crop="General",
        prompt="How to prepare and use neem oil spray for leaf aphids?",
        language="English"
    ),
    QuickPromptItem(
        category="Cotton Pest",
        crop="Cotton",
        prompt="How to control whitefly and sucking pests in cotton organically?",
        language="English"
    ),
    # Hindi Prompts
    QuickPromptItem(
        category="Tomato Disease",
        crop="Tomato",
        prompt="टमाटर के पत्तों पर भूरे गोल धब्बे दिख रहे हैं, क्या उपाय करें?",
        language="Hindi"
    ),
    QuickPromptItem(
        category="Cotton Pest",
        crop="Cotton",
        prompt="कपास में रस चूसने वाले कीट और माहू का जैविक छिड़काव क्या है?",
        language="Hindi"
    ),
    QuickPromptItem(
        category="Rain / Fungus",
        crop="General",
        prompt="बारिश के बाद फसलों में फफूंद रोकने के लिए क्या करें?",
        language="Hindi"
    )
]


def detect_crop_from_text(text: str, fallback_crop: Optional[str] = None) -> str:
    """Finds which crop the farmer is asking about."""
    text_lower = text.lower()
    for crop_name, aliases in CROP_KEYWORDS.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                return crop_name
    return fallback_crop or "Tomato"


def match_problem(crop: str, text: str) -> Optional[Dict[str, Any]]:
    """Matches text against knowledge base diseases for the specified crop."""
    text_lower = text.lower()
    crop_diseases = AGRONOMY_KNOWLEDGE_BASE.get(crop, [])

    # Check for exact problem keywords
    for prob_name, kws in PROBLEM_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            for d in crop_diseases:
                if prob_name.lower() in d["problem_name"].lower() or any(k in text_lower for k in d["keywords"]):
                    return d

    # Search knowledge base keywords directly
    for d in crop_diseases:
        score = sum(1 for kw in d["keywords"] if kw.lower() in text_lower)
        if score >= 1:
            return d

    # Return first profile if available
    return crop_diseases[0] if crop_diseases else None


CROP_NAMES_KANNADA: Dict[str, str] = {
    "Tomato": "ಟೊಮೆಟೊ (Tomato)",
    "Potato": "ಆಲೂಗಡ್ಡೆ (Potato)",
    "Cotton": "ಹತ್ತಿ (Cotton)",
    "Rice": "ಭತ್ತ (Rice/Paddy)",
    "Wheat": "ಗೋಧಿ (Wheat)",
    "Chili": "ಮೆಣಸಿನಕಾಯಿ (Chili)",
    "Maize": "ಮೆಕ್ಕೆಜೋಳ (Maize)",
    "Onion": "ಈರುಳ್ಳಿ (Onion)"
}


def format_kannada_response(crop: str, problem: Dict[str, Any], query: str) -> Dict[str, Any]:
    crop_kn = CROP_NAMES_KANNADA.get(crop, f"{crop} ಬೆಳೆ")
    p_name = problem["problem_name"]
    organic = problem["organic_remedies"][0] if problem.get("organic_remedies") else "ಬೇವಿನ ಎಣ್ಣೆ 5 ಮಿ.ಲೀ. ಪ್ರತಿ ಲೀಟರ್ ನೀರಿಗೆ"
    chemical = problem["chemical_controls"][0] if problem.get("chemical_controls") else "ಮ್ಯಾಂಕೋಜೆಬ್ 75% WP @ 2.5 ಗ್ರಾಂ ಪ್ರತಿ ಲೀಟರ್ ನೀರಿಗೆ"
    action = problem["immediate_actions"][0] if problem.get("immediate_actions") else "ರೋಗಪೀಡಿತ ಎಲೆಗಳನ್ನು ತಕ್ಷಣ ಕತ್ತರಿಸಿ ತೋಟದಿಂದ ಹೊರಗೆ ಹಾಕಿ."

    reply = (
        f"ರೈತ ಮಿತ್ರರೇ, ನಿಮ್ಮ {crop_kn} ಬೆಳೆಯಲ್ಲಿ **{p_name}** ರೋಗದ ಲಕ್ಷಣಗಳು ಕಂಡುಬರುತ್ತಿವೆ.\n\n"
        f"🚨 **ತಕ್ಷಣದ ಕ್ರಮ:**\n- {action}\n- ಗಿಡಗಳ ಎಲೆಗಳ ಮೇಲೆ ನೀರು ಬೀಳದಂತೆ ಬುಡಕ್ಕೆ ಮಾತ್ರ ನೀರು ಹಾಯಿಸಿ.\n\n"
        f"🌱 **ಸಾವಯವ / ನೈಸರ್ಗಿಕ ಪರಿಹಾರ:**\n- {organic}\n- ಟ್ರೈಕೋಡರ್ಮಾ ವಿರಿಡೆ (Trichoderma) 5 ಗ್ರಾಂ ಅಥವಾ ಹುಳಿ ಮಜ್ಜಿಗೆಯ ದ್ರಾವಣ (1:10 ಪ್ರಮಾಣ) ಸಿಂಪಡಿಸುವುದು ಪ್ರಯೋಜನಕಾರಿ.\n\n"
        f"🧪 **ರಾಸಾಯನಿಕ ನಿಯಂತ್ರಣ (ಅಗತ್ಯವಿದ್ದಲ್ಲಿ):**\n- {chemical}\n\n"
        f"🛡️ **ಸುರಕ್ಷತಾ ಸಲಹೆ:** ಔಷಧ ಸಿಂಪರಣೆಯನ್ನು ಮುಂಜಾನೆ ಅಥವಾ ಸಂಜೆ ಶಾಂತ ವಾತಾವರಣದಲ್ಲಿ ಮಾಡಿ, ಮಾಸ್ಕ್ ಮತ್ತು ಕೈಗವಸು ಧರಿಸಿ."
    )

    audio_text = (
        f"ರೈತ ಮಿತ್ರರೇ, ನಿಮ್ಮ {crop_kn} ಬೆಳೆಯಲ್ಲಿ {p_name} ರೋಗದ ಲಕ್ಷಣಗಳು ಕಂಡುಬಂದಿವೆ. "
        f"ರೋಗಪೀಡಿತ ಎಲೆಗಳನ್ನು ತಕ್ಷಣ ಕತ್ತರಿಸಿ ನಾಶಮಾಡಿ. ಸಾವಯವ ನಿಯಂತ್ರಣಕ್ಕಾಗಿ {organic.split('(')[0]} ಸಿಂಪಡಿಸಿ, "
        f"ಅಥವಾ ತೀವ್ರ ರೋಗವಿದ್ದರೆ {chemical.split('(')[0]} ಬಳಸಿ."
    )

    follow_ups = [
        f"{crop} ಬೆಳೆಗೆ ಔಷಧ ಸಿಂಪಡಿಸುವ ಸರಿಯಾದ ಪ್ರಮಾಣ ಎಷ್ಟು?",
        "ಬೇವಿನ ಎಣ್ಣೆ ಕಷಾಯವನ್ನು ಮನೆಯಲ್ಲೇ ಹೇಗೆ ತಯಾರಿಸುವುದು?",
        "ಮುಂದಿನ ಸಿಂಪರಣೆಯನ್ನು ಎಷ್ಟು ದಿನಗಳ ನಂತರ ಮಾಡಬೇಕು?"
    ]

    return {
        "reply": reply,
        "audio_text": audio_text,
        "suggested_actions": [action, organic, chemical],
        "follow_ups": follow_ups
    }


def format_hindi_response(crop: str, problem: Dict[str, Any], query: str) -> Dict[str, Any]:
    p_name = problem["problem_name"]
    organic = problem["organic_remedies"][0] if problem.get("organic_remedies") else "नीम तेल 5ml प्रति लीटर पानी"
    chemical = problem["chemical_controls"][0] if problem.get("chemical_controls") else "मैनकोजेब 2.5 ग्राम प्रति लीटर पानी"
    action = problem["immediate_actions"][0] if problem.get("immediate_actions") else "संक्रमित पत्तियों को तुरंत काटकर नष्ट करें।"

    reply = (
        f"किसान भाई, आपकी {crop} की फसल में **{p_name}** के लक्षण दिख रहे हैं।\n\n"
        f"🚨 **तुरंत क्या करें:**\n- {action}\n- पानी सीधे जड़ों में दें, पत्तियों पर पानी का छिड़काव न करें।\n\n"
        f"🌱 **जैविक / प्राकृतिक उपाय:**\n- {organic}\n- 10 दिन में एक बार खट्टी छाछ (1:10 अनुपात) का छिड़काव भी लाभकारी है।\n\n"
        f"🧪 **रासायनिक दवा (आवश्यकता होने पर):**\n- {chemical}\n\n"
        f"🛡️ **सुरक्षा सलाह:** दवा का छिड़काव सुबह या शाम को शांत मौसम में करें और सुरक्षा मास्क पहनें।"
    )

    audio_text = (
        f"किसान भाई, आपकी {crop} फसल में {p_name} के लक्षण हैं। "
        f"संक्रमित पत्तियों को तुरंत हटा दें। जैविक नियंत्रण के लिए {organic.split('(')[0]} का छिड़काव करें, "
        f"या अधिक प्रकोप होने पर {chemical.split('(')[0]} छिड़कें।"
    )

    follow_ups = [
        f"{crop} में दवा का सही नाप क्या है?",
        "जैविक नीम तेल कैसे तैयार करें?",
        f"{crop} की खाद और सिंचाई का समय बताएं"
    ]

    return {
        "reply": reply,
        "audio_text": audio_text,
        "suggested_actions": [action, organic, chemical],
        "follow_ups": follow_ups
    }


def format_marathi_response(crop: str, problem: Dict[str, Any], query: str) -> Dict[str, Any]:
    p_name = problem["problem_name"]
    organic = problem["organic_remedies"][0] if problem.get("organic_remedies") else "कडुनिंब अर्क (नीम ऑइल) ५ मिली प्रति लिटर"
    chemical = problem["chemical_controls"][0] if problem.get("chemical_controls") else "मॅनकोझेब २.५ ग्रॅम प्रति लिटर पाणी"
    action = problem["immediate_actions"][0] if problem.get("immediate_actions") else "बाधित पाने ताबडतोब तोडून नष्ट करा."

    reply = (
        f"शेतकरी बंधू, आपल्या {crop} पिकावर **{p_name}** चे लक्षण दिसत आहे.\n\n"
        f"🚨 **तातडीची कृती:**\n- {action}\n- झाडांवर पाणी शिंपडणे टाळा, ठिबक किंवा मुळाशी पाणी द्या.\n\n"
        f"🌱 **सेंद्रिय / जैविक उपाय:**\n- {organic}\n- आंबट ताक (१:१० प्रमाणात पाण्यात) फवारल्यास बुरशी रोखण्यास मदत होते.\n\n"
        f"🧪 **रासायनिक फवारणी (गरज भासल्यास):**\n- {chemical}\n\n"
        f"🛡️ **काळजी:** फवारणी करताना तोंडाला मास्क लावा आणि सकाळी किंवा संध्याकाळी फवारा."
    )

    audio_text = (
        f"शेतकरी बंधू, आपल्या {crop} पिकावर {p_name} चा प्रादुर्भाव दिसत आहे. "
        f"रोगट पाने ताबडतोब काढून नष्ट करा आणि जैविक उपायासाठी {organic.split('(')[0]} फवारा."
    )

    follow_ups = [
        f"{crop} साठी औषधाचे अचूक प्रमाण काय?",
        "सेंद्रिय कीटकनाशक कसे बनवावे?",
        "पुढील फवारणी कधी करावी?"
    ]

    return {
        "reply": reply,
        "audio_text": audio_text,
        "suggested_actions": [action, organic, chemical],
        "follow_ups": follow_ups
    }


def format_english_response(crop: str, problem: Dict[str, Any], query: str) -> Dict[str, Any]:
    p_name = problem["problem_name"]
    organic = problem["organic_remedies"][0] if problem.get("organic_remedies") else "Neem Oil spray at 5 ml/liter water"
    chemical = problem["chemical_controls"][0] if problem.get("chemical_controls") else "Mancozeb 75% WP @ 2.5 g/liter water"
    action = problem["immediate_actions"][0] if problem.get("immediate_actions") else "Prune and destroy infected foliage immediately."

    reply = (
        f"Hello Farmer, based on your symptoms, your {crop} is showing signs of **{p_name}** ({problem.get('scientific_name', '')}).\n\n"
        f"🚨 **Immediate Field Action:**\n- {action}\n- Avoid sprinkler irrigation; water directly at the base early in the morning.\n\n"
        f"🌱 **Organic & Biological Remedies:**\n- {organic}\n- Foliar spray of Trichoderma viride @ 5g/L or sour buttermilk solution (1:10 dilution).\n\n"
        f"🧪 **Standard Chemical Control:**\n- {chemical}\n\n"
        f"🛡️ **Safety & Prevention:** Spray during calm morning or late evening hours. Maintain at least 7 days pre-harvest interval."
    )

    audio_text = (
        f"Attention farmer: Your {crop} appears affected by {p_name}. "
        f"{action} For organic control, spray {organic.split('(')[0]}. "
        f"For severe infection, apply {chemical.split('(')[0]}."
    )

    follow_ups = [
        f"What is the exact dilution dosage for {crop}?",
        "How do I prepare organic neem spray?",
        "What weather conditions trigger this disease?"
    ]

    return {
        "reply": reply,
        "audio_text": audio_text,
        "suggested_actions": [action, organic, chemical],
        "follow_ups": follow_ups
    }


@router.post("/chat", response_model=VoiceAssistantResponse)
def voice_assistant_chat(
    req: VoiceAssistantRequest,
    user: Optional[User] = Depends(get_optional_user)
):
    """Processes farmer voice/text queries and generates accessible voice-ready agronomy advice."""
    raw_query = req.message.strip()
    if not raw_query:
        raw_query = "Crop health and protection guidance"

    user_crop = user.primary_crop if user and user.primary_crop else None
    crop = req.crop_context or detect_crop_from_text(raw_query, fallback_crop=user_crop)
    problem = match_problem(crop, raw_query)

    lang = (req.language or "English").lower().strip()

    # Explicit user language choice takes absolute priority
    if "kannada" in lang or lang == "kn":
        res_data = format_kannada_response(crop, problem, raw_query)
        selected_lang = "Kannada"
    elif "hindi" in lang or lang == "hi":
        res_data = format_hindi_response(crop, problem, raw_query)
        selected_lang = "Hindi"
    elif "marathi" in lang or lang == "mr":
        res_data = format_marathi_response(crop, problem, raw_query)
        selected_lang = "Marathi"
    elif "english" in lang or lang == "en":
        res_data = format_english_response(crop, problem, raw_query)
        selected_lang = "English"
    else:
        # Fallback to script detection if language was completely unassigned
        if any('\u0c80' <= c <= '\u0cff' for c in raw_query):
            res_data = format_kannada_response(crop, problem, raw_query)
            selected_lang = "Kannada"
        elif any('\u0900' <= c <= '\u097f' for c in raw_query):
            res_data = format_hindi_response(crop, problem, raw_query)
            selected_lang = "Hindi"
        else:
            res_data = format_english_response(crop, problem, raw_query)
            selected_lang = "English"

    return VoiceAssistantResponse(
        reply=res_data["reply"],
        audio_text=res_data["audio_text"],
        language=selected_lang,
        detected_crop=crop,
        detected_problem=problem.get("problem_name") if problem else None,
        suggested_actions=res_data["suggested_actions"],
        follow_ups=res_data["follow_ups"]
    )


@router.get("/quick-prompts", response_model=List[QuickPromptItem])
def get_quick_prompts():
    """Returns sample voice queries for farmers to tap or speak."""
    return QUICK_VOICE_PROMPTS
