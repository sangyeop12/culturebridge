"""Metadata-only, free-of-charge requests. Draft creation never sends mail or grants rights."""

from urllib.parse import urlsplit

from culturebridge.data.material_review import SCOPE_NOTES
from culturebridge.data.source_audit import PROVIDER_FINDINGS


def permission_requests(school, course, applicant, reply_email=""):
    from culturebridge.services.individual_source_service import INDIVIDUALS

    if not all(value.strip() for value in (school, course, applicant)):
        raise ValueError("학교·수업·신청자 정보를 확인하세요.")
    groups = {}
    for identity in SCOPE_NOTES:
        row = INDIVIDUALS[identity]
        host = (urlsplit(row["url"]).hostname or "").removeprefix("www.")
        finding = next(
            (
                value
                for domain, value in PROVIDER_FINDINGS.items()
                if host == domain or host.endswith("." + domain)
            ),
            None,
        )
        policy_url = finding[1] if finding else row["url"]
        # A shared rights policy can cover multiple institutional sites, e.g. CMN.
        group = groups.setdefault(
            policy_url,
            {
                "organizations": [],
                "policy_url": policy_url,
                "sources": [],
                "status": "draft_not_sent",
                "free_only": True,
                "recipient_verified": False,
                "reply_email": reply_email,
            },
        )
        if row["organization"] not in group["organizations"]:
            group["organizations"].append(row["organization"])
        group["sources"].append({"id": identity, "title": row["name"], "url": row["url"]})
    for group in groups.values():
        source_list = "\n".join("- " + r["title"] + ": " + r["url"] for r in group["sources"])
        group["subject"] = "CultureBridge: request for free non-commercial classroom permission"
        group["body"] = (
            "Dear rights and permissions team,\n\n"
            f"My name is {applicant}. I am working on CultureBridge for {course} at {school}. "
            "It is a non-commercial student project for heritage comparison and learning.\n\n"
            "Please confirm whether the following uses of the specific textual materials below "
            "can be authorised free of charge, or identify an existing free licence "
            "that covers them. "
            "Please answer each use separately:\n"
            "1. Store the selected text on our project server and display it to project members "
            "and the instructor for classroom development and demonstrations.\n"
            "2. Produce clearly labelled Korean translations, simplified learning explanations, "
            "comparisons and quiz questions, keeping the original "
            "and our interpretation distinct.\n"
            "3. Transmit selected excerpts to Google's Gemini API for translation or analysis. "
            "Please specify any conditions on this third-party processing. We are not seeking "
            "permission to train an AI model on your materials.\n"
            "4. Include permitted excerpts or derived learning explanations, source attribution "
            "and quiz results in classroom HTML, Markdown, JSON or printed learning reports.\n\n"
            "Materials requested:\n" + source_list + "\n\n"
            "This request does not include photographs, logos, maps or other separately credited "
            "third-party works. We will not present our project as endorsed by your institution. "
            "The request is limited to a non-commercial course project, not a general public "
            "or commercial release. We are not requesting bulk redistribution of your originals "
            "or publication of original texts in a public code repository.\n\n"
            "We cannot accept any licence, processing, handling or other fee. If any requested "
            "use requires payment, please treat that use as not accepted and let us know. "
            "Please do not begin any chargeable work. Partial permission and free alternative "
            "official sources would also be helpful.\n\n"
            "Please specify attribution, permitted audience, duration, modification and "
            "redistribution conditions, and whether you control the rights to all requested text. "
            "No response will be treated as no permission, not as consent. If another department "
            "handles this request, please direct us to it.\n\n"
            f"Thank you,\n{applicant}\n{school}\n{course}\n"
            + ("Reply address: " + reply_email + "\n" if reply_email else "")
        )
    return list(groups.values())
