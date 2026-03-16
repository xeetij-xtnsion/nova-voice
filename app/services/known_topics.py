"""Known topic data builders for voice AI tool responses."""

from typing import Dict
from app.config import settings, practitioner_services


def build_topic_data(topic_name: str) -> Dict:
    """Return structured clinic data for a given topic name."""
    if topic_name == "services":
        return {
            "detail": (
                "We offer the following services: "
                + ", ".join(settings.clinic_services)
                + "."
            ),
            "services": settings.clinic_services,
        }

    if topic_name == "hours":
        return {
            "detail": (
                "Our hours of operation: "
                "Monday 12 to 8 PM, "
                "Tuesday 10 AM to 8 PM, "
                "Wednesday and Thursday 10 AM to 6 PM, "
                "Friday 9 AM to 6 PM, "
                "Saturday 9 AM to 5 PM, "
                "Sunday closed."
            ),
        }

    if topic_name == "location":
        return {
            "detail": (
                "Nova Naturopathic Integrative Clinic is located at "
                "208-6707 Elbow Drive Southwest, Calgary, Alberta, T2V 0E4. "
                "We're on the 2nd floor of Mayfair Place, the commercial side. "
                "When you get off the elevator, turn left and it's the first set "
                "of glass doors across from the elevator. "
                "You can reach us at 587-391-5753 or email admin@novaclinic.ca."
            ),
        }

    if topic_name == "parking":
        return {
            "detail": (
                "Free parking is available at Mayfair Place for up to 2 hours "
                "in unreserved yellow stalls, either in the basement or surface lot. "
                "Just register your license plate at the kiosk when you arrive."
            ),
        }

    if topic_name == "practitioners":
        lines = []
        for name, info in practitioner_services.items():
            services = ", ".join(info["services"])
            focus = info.get("areas_of_focus", "")
            line = f"{name}, {info['title']}, offers {services}"
            if focus:
                line += f". Focus areas: {focus}"
            lines.append(line)
        return {
            "detail": "Our practitioners: " + ". ".join(lines),
        }

    if topic_name == "consultations":
        return {
            "detail": (
                "Initial consultations are part of our Naturopathic Medicine service. "
                "There are three options: "
                "First, an Initial Naturopathic Consultation, about 80 minutes for $295, "
                "which is a comprehensive assessment with one of our naturopathic doctors. "
                "Second, an Initial Injection or IV Consultation, about 80 minutes from $290, "
                "for patients interested in injection or IV nutrient therapy. "
                "Third, a Meet and Greet, which is free, 15 minutes by phone, "
                "a no-obligation introductory call to discuss your health concerns "
                "and see if we're a good fit."
            ),
        }

    if topic_name == "what_to_bring":
        return {
            "detail": (
                "For your appointment, please bring a valid government-issued photo ID, "
                "your insurance card or extended health benefits info if applicable, "
                "a list of any current medications or supplements, "
                "any relevant medical records or lab results, "
                "and comfortable clothing especially for massage, acupuncture, or osteopathic treatments. "
                "New patients should arrive 10 to 15 minutes early to complete intake forms."
            ),
        }

    if topic_name == "rescheduling":
        return {
            "detail": (
                "We have a 24-hour cancellation and rescheduling policy. "
                "Please let us know at least 24 hours before your scheduled appointment "
                "if you need to cancel or reschedule. Failure to do so may result in a fee. "
                "You can call us at 587-391-5753, email admin@novaclinic.ca, "
                "or manage your appointment through our online booking portal."
            ),
        }

    if topic_name == "testing":
        return {
            "detail": (
                "We offer two categories of testing. "
                "Standardized testing is similar to what your family doctor orders through "
                "Alberta Health Services, like blood work, thyroid panels, and cholesterol. "
                "Functional testing measures sub-clinical imbalances using blood, stool, "
                "saliva, or dried urine for deep health insights. "
                "Important: testing ordered by our naturopathic doctors is not subsidized "
                "by the government of Alberta and will be an out-of-pocket expense, "
                "but can be billed to extended health insurance. "
                "Both types require a naturopathic doctor consultation."
            ),
        }

    return {}
