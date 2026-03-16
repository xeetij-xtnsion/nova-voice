from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    openai_api_key: str

    # Database (shared with nova-agent — read-only access to kb_chunks)
    database_url: str

    # RAG Parameters
    top_k: int = 8
    kb_version: int = 1
    similarity_threshold: float = 0.45

    # OpenAI Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # OpenAI Realtime API
    openai_realtime_model: str = "gpt-4o-realtime-preview-2025-06-03"
    realtime_voice: str = "coral"

    # Clinic services (for known topic responses)
    clinic_services: list = [
        "Acupuncture",
        "Naturopathic Medicine",
        "Massage Therapy",
    ]


settings = Settings()

# Practitioner -> service mapping (same as nova-agent)
practitioner_services = {
    "Dr. Ali Nurani": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BSc (University of Calgary), ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, CAND, AAND",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
            "Prolotherapy",
            "Functional Testing",
        ],
        "areas_of_focus": "Autoimmune conditions (all types including lupus, rheumatoid arthritis, Hashimoto's, Crohn's, MS, and more), cancer co-management (diet, cancer-focused IV nutrition therapies, botanical/herbal treatments), gut health and digestive health, weight management, endocrine, immune support, pain management, nervous system concerns",
        "certifications": "IV nutrient therapy, injection therapies, ozone therapy, regenerative injection therapy",
    },
    "Dr. Marisa Hucal": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BSc Honours (University of Calgary), ND (Boucher Institute of Naturopathic Medicine)",
        "registrations": "CNDA, CAND",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
        ],
        "areas_of_focus": "Gut health and digestive health, fertility, weight management, hormonal health (men and women), stress and mental health",
        "certifications": "Acupuncture, IV therapy, chelation and advanced IV therapies, prescribing upgrade, Metabolic Balance Certified Coach",
    },
    "Dr. Alexa Torontow": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "BHK (University of British Columbia), ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, AAND",
        "services": ["Naturopathic Medicine"],
        "areas_of_focus": "Gut health and digestive health, fertility, women's hormonal health, pregnancy, postpartum care, perinatal support",
        "certifications": "Trained Birth Doula",
    },
    "Dr. Madison Thorne": {
        "title": "Naturopathic Doctor (ND)",
        "credentials": "Kinesiology degree, ND (Canadian College of Naturopathic Medicine)",
        "registrations": "CNDA, AAND, CAND, Oncology Association of Naturopathic Doctors",
        "services": [
            "Naturopathic Medicine",
            "IV Therapy",
            "Injections",
        ],
        "areas_of_focus": "Women's hormonal health, general naturopathic medicine",
        "certifications": "Acupuncture, IV therapy, intramuscular injection therapy",
    },
    "Lorena Bulcao": {
        "title": "Dr. Ac, TCMD, RMT",
        "credentials": "Massage Therapy (Mount Royal College), TCMD (Calgary College of Chinese Medicine and Acupuncture)",
        "services": [
            "Acupuncture",
            "Cupping",
            "Facial Rejuvenation",
            "Massage Therapy",
        ],
        "areas_of_focus": "Pain management, musculoskeletal issues, stress management, women's health, facial acupuncture",
        "certifications": "Reiki, reflexology, Thai massage, yoga instruction, Ayurvedic medicine training (India)",
    },
}
