"""
CaseWeave AI — Comprehensive Indian Criminal Legal Corpus Populator.
Generates structured statutory definitions and landmark judicial precedents across:
1. Bharatiya Nyaya Sanhita (BNS), 2023
2. Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023
3. Bharatiya Sakshya Adhiniyam (BSA), 2023
4. Special & Local Laws (NDPS, POCSO, Juvenile Justice, SC/ST, IT Act, Arms Act)
5. Landmark Supreme Court Criminal Jurisprudence Precedents
"""
import json
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "legal_corpus"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)

CORPUS_DATA = [
    # ------------------------------------------------- BNS 2023 -------------------------------------------------
    {
        "id": "BNS-2023-S303",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "303",
        "title": "BNS Section 303 — Theft",
        "topic": "Theft, dishonest removal of movable property",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment up to 3 years, or fine, or both (community service for first offence < Rs 5,000)",
        "triable_by": "Any Magistrate",
        "ingredients": [
            "Dishonest intention to take movable property",
            "Property taken out of possession of another person",
            "Taken without consent of possessor",
            "Moving of property in order to effect such taking"
        ],
        "text": "Whoever, intending to take dishonestly any movable property out of the possession of any person without that person's consent, moves that property in order to such taking, is said to commit theft. Under Section 303(2), where the value of stolen property is less than five thousand rupees, and the person is convicted for the first time, community service may be awarded."
    },
    {
        "id": "BNS-2023-S305",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "305",
        "title": "BNS Section 305 — Theft in a Dwelling House or Building",
        "topic": "Theft in building, storehouse, tent or vessel",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment up to 7 years and fine",
        "triable_by": "Any Magistrate",
        "ingredients": [
            "Commission of theft as defined in Section 303",
            "Theft committed in any building, tent, vessel, or storehouse used for human dwelling or custody of property"
        ],
        "text": "Whoever commits theft in any building, tent or vessel, which building, tent or vessel is used as a human dwelling, or used for the custody of property, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine. This section directly applies to commercial shop, pharmacy, and warehouse burglaries where property is removed from within enclosed premises."
    },
    {
        "id": "BNS-2023-S304",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "304",
        "title": "BNS Section 304 — Snatching",
        "topic": "Snatching of property, sudden quick seizure",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment up to 3 years and fine",
        "triable_by": "Any Magistrate",
        "ingredients": [
            "Theft committed by suddenly or quickly grabbing or seizing property",
            "Property carried away from person or custody of another"
        ],
        "text": "Theft is snatching if, in order to commit theft, the offender suddenly or quickly or forcibly seizes, secures, grabs or takes away from any person or from his possession any movable property. This new provision in BNS codifies mobile and chain snatching as a distinct aggravated offence."
    },
    {
        "id": "BNS-2023-S331",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "331",
        "title": "BNS Section 331 — Lurking House-Trespass or House-Breaking by Night",
        "topic": "House-breaking by night, forced shutter entry, night intrusion",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment up to 14 years and fine (aggravated if prepared for hurt/assault)",
        "triable_by": "Court of Session / Magistrate First Class",
        "ingredients": [
            "House-trespass or house-breaking effected after sunset and before sunrise",
            "Entry effected through passage made by offender, breaking lock, or entering through unaccustomed opening",
            "Preparation made for causing hurt, assault, or wrongful restraint"
        ],
        "text": "Whoever commits lurking house-trespass by night, or house-breaking by night, having made preparation for causing hurt to any person, or for assaulting any person, or for wrongfully restraining any person, or for putting any person in fear of hurt or of assault or of wrongful restraint, shall be punished with imprisonment for a term which may extend to fourteen years, and shall also be liable to fine. Applicable to forced shutter breaches with crowbars or cutting equipment during night hours."
    },
    {
        "id": "BNS-2023-S111",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "111",
        "title": "BNS Section 111 — Organised Crime",
        "topic": "Organised crime syndicate, continuing unlawful activity, gang burglary",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Death or life imprisonment with minimum fine of Rs 10 Lakhs (if death results); otherwise 5 years to life imprisonment",
        "triable_by": "Special Court / Court of Session",
        "ingredients": [
            "Continuing unlawful activity by members of an organized crime syndicate",
            "Use of violence, threat, intimidation, or coercion to obtain direct or indirect material benefit",
            "Charge-sheet filed for cognizable offence within preceding 10 years and court has taken cognizance"
        ],
        "text": "Any continuing unlawful activity including kidnapping, robbery, dacoity, vehicle theft, extortion, land grabbing, contract killing, economic offence, cybercrimes, or illegal trafficking committed by a person either singly or jointly as a member of an organised crime syndicate. Critical for prosecuting repeat serial burglary rings across police station divisions."
    },
    {
        "id": "BNS-2023-S112",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "112",
        "title": "BNS Section 112 — Petty Organised Crime",
        "topic": "Theft, snatching, cheating by gang or organized syndicate",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment from 1 to 7 years and fine",
        "triable_by": "Magistrate of First Class",
        "ingredients": [
            "Offence committed by member of a group or gang",
            "Includes theft, snatching, cheating, ticket unauthorized sale, betting, or automated teller fraud"
        ],
        "text": "Whoever, being a member of a group or gang, either singly or jointly, commits any act of theft, snatching, cheating, unauthorized sale of tickets, unauthorized betting or gambling, or automated teller machine fraud, shall be punished with imprisonment for a term which shall not be less than one year but which may extend to seven years, and fine."
    },
    {
        "id": "BNS-2023-S310",
        "act": "Bharatiya Nyaya Sanhita, 2023",
        "section": "310",
        "title": "BNS Section 310 — Dacoity",
        "topic": "Robbery committed by 5 or more persons conjointly",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Imprisonment for life, or rigorous imprisonment up to 10 years and fine",
        "triable_by": "Court of Session",
        "ingredients": [
            "Five or more persons conjointly commit or attempt to commit robbery",
            "Whole number of persons committing or aiding robbery is five or more"
        ],
        "text": "When five or more persons conjointly commit or attempt to commit a robbery, or where the whole number of persons conjointly committing or attempting to commit a robbery, and persons present and aiding such commission or attempt, amount to five or more, every person so committing, attempting or aiding, is said to commit dacoity."
    },

    # ------------------------------------------------- BNSS 2023 -------------------------------------------------
    {
        "id": "BNSS-2023-S35",
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "section": "35",
        "title": "BNSS Section 35 — Arrest by Police Officer Without Warrant",
        "topic": "Arrest guidelines, notice of appearance, mandatory checklist",
        "type": "statute",
        "cognizable": True,
        "bailable": None,
        "punishment": "Procedural mandate",
        "triable_by": "High Court / Magistrate",
        "ingredients": [
            "Offence punishable with imprisonment up to 7 years requires written satisfaction of necessity to arrest",
            "Mandatory issuance of Notice of Appearance under Section 35(3) where arrest is not deemed necessary",
            "Mandatory medical examination of arrestee under Section 53",
            "Designated Police Officer in every district and station under Section 37"
        ],
        "text": "Governs police power of arrest without warrant. For offences punishable with imprisonment for a term which may be less than seven years or which may extend to seven years, police must not arrest unless satisfied that arrest is necessary to prevent further offence, ensure proper investigation, or prevent tampering of evidence. Under Section 35(3), where arrest is not made, police must issue a notice directing the person to appear before the investigating officer."
    },
    {
        "id": "BNSS-2023-S105",
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "section": "105",
        "title": "BNSS Section 105 — Recording of Search and Seizure Through Audio-Video Means",
        "topic": "Mandatory videography, search and seizure electronic record, mahazar",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Evidentiary procedural mandate",
        "triable_by": "All Criminal Courts",
        "ingredients": [
            "Process of conducting search of a place or seizure of any property must be recorded through audio-video electronic means",
            "Preparation of search list (mahazar) signed by witnesses",
            "Forwarding of electronic recording to Magistrate without delay"
        ],
        "text": "The process of conducting search of a place or taking possession of any property, article or thing under this Chapter or under Section 185, including preparation of the list of things seized and the signature of witnesses, shall be recorded through any audio-video electronic means preferably mobile phone and the police officer shall forward the recording to the District Magistrate, Sub-divisional Magistrate or Judicial Magistrate of first class without delay."
    },
    {
        "id": "BNSS-2023-S173",
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "section": "173",
        "title": "BNSS Section 173 — Information in Cognizable Cases (FIR)",
        "topic": "Registration of FIR, e-FIR, zero FIR, preliminary enquiry",
        "type": "statute",
        "cognizable": True,
        "bailable": None,
        "punishment": "Procedural mandate",
        "triable_by": "Police Station Jurisdiction",
        "ingredients": [
            "Every information relating to commission of cognizable offence must be recorded",
            "Permits information given electronically (e-FIR) taken on record and signed within 3 days",
            "Preliminary enquiry permissible within 14 days for offences punishable between 3 to 7 years with prior approval of DSP"
        ],
        "text": "Every information relating to the commission of a cognizable offence, if given orally to an officer in charge of a police station, shall be reduced to writing. Information may be given by electronic communication (e-FIR), which shall be taken on record on being signed within three days by the informant. Preliminary enquiry may be conducted within fourteen days in offences punishable with 3 to 7 years imprisonment."
    },
    {
        "id": "BNSS-2023-S180",
        "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "section": "180",
        "title": "BNSS Section 180 — Examination of Witnesses by Police",
        "topic": "Recording witness statements, audio-video witness examination",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Procedural mandate",
        "triable_by": "Investigating Officer",
        "ingredients": [
            "Examination of person acquainted with facts and circumstances",
            "Statement may be recorded by audio-video electronic means",
            "Statement shall not be signed by witness (under Section 181)"
        ],
        "text": "Any police officer making an investigation may examine orally any person supposed to be acquainted with the facts and circumstances of the case. The police officer may reduce into writing any statement made to him in the course of an examination, and statement of a witness may also be recorded by audio-video electronic means."
    },

    # ------------------------------------------------- BSA 2023 -------------------------------------------------
    {
        "id": "BSA-2023-S63",
        "act": "Bharatiya Sakshya Adhiniyam, 2023",
        "section": "63",
        "title": "BSA Section 63 — Admissibility of Electronic Records",
        "topic": "Electronic record admissibility, Section 63 certificate, digital integrity",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Evidentiary statutory condition",
        "triable_by": "All Courts",
        "ingredients": [
            "Identification of electronic record and describing manner of its production",
            "Particulars of device involved in production of electronic record",
            "Device was operating properly or periods of out-of-operation did not affect accuracy",
            "Certificate signed by person in official custody / management of device"
        ],
        "text": "Any information contained in an electronic record which is printed on a paper, stored, recorded or copied in optical or magnetic media produced by a computer shall be deemed to be also a document, if the conditions mentioned in this section are satisfied in relation to the information and computer in question and shall be admissible in any proceedings, without further proof or production of the original, as evidence of any contents of the original or of any fact stated therein. Requires a mandatory Certificate in Schedule Form-A/B signed by a responsible official."
    },
    {
        "id": "BSA-2023-S23",
        "act": "Bharatiya Sakshya Adhiniyam, 2023",
        "section": "23",
        "title": "BSA Section 23 — How Much of Information from Accused May be Proved",
        "topic": "Recovery of weapon/evidence pursuant to disclosure, Section 27 IEA successor",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Evidentiary rule",
        "triable_by": "All Criminal Courts",
        "ingredients": [
            "Information received from person accused of any offence in custody of police officer",
            "Discovery of a fact distinctly deposed to in consequence of information received",
            "Only that portion of information which relates distinctly to the fact discovered is admissible"
        ],
        "text": "Provided that when any fact is deposed to as discovered in consequence of information received from a person accused of any offence, in the custody of a police officer, so much of such information, whether it amounts to a confession or not, as relates distinctly thereby to the fact thereby discovered, may be proved. Governs admissibility of recovered crowbars, stolen cash, or drugs recovered based on accused disclosure statements."
    },

    # ------------------------------------------------- SPECIAL & LOCAL LAWS -------------------------------------------------
    {
        "id": "NDPS-1985-S21",
        "act": "Narcotic Drugs and Psychotropic Substances Act, 1985",
        "section": "21",
        "title": "NDPS Act Section 21 — Punishment for Contravention in Relation to Manufactured Drugs",
        "topic": "Manufactured narcotics, psychotropics, intermediate quantity, commercial quantity",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Small quantity: Up to 1 year RI; Intermediate: Up to 10 years RI and Rs 1 Lakh fine; Commercial: 10 to 20 years RI and Rs 1 to 2 Lakhs fine",
        "triable_by": "Special NDPS Court",
        "ingredients": [
            "Manufacture, possess, sell, purchase, transport, import inter-State or export inter-State any manufactured drug",
            "Absence of lawful license or authority under the Act or Drugs and Cosmetics Act",
            "Weight verification to classify Small, Intermediate, or Commercial quantity"
        ],
        "text": "Whoever, in contravention of any provision of this Act or any rule or order made or condition of licence granted thereunder, manufactures, possesses, sells, purchases, transports, imports inter-State, exports inter-State or uses any manufactured drug or any preparation containing any manufactured drug shall be punishable with rigorous imprisonment and fine graded strictly according to quantity."
    },
    {
        "id": "NDPS-1985-S50",
        "act": "Narcotic Drugs and Psychotropic Substances Act, 1985",
        "section": "50",
        "title": "NDPS Act Section 50 — Conditions Under Which Search of Persons Shall be Conducted",
        "topic": "Mandatory search procedure, right to be searched before Gazetted Officer or Magistrate",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Mandatory procedural safeguard (non-compliance vitiates recovery)",
        "triable_by": "Special NDPS Court",
        "ingredients": [
            "Informing suspect of statutory right to be searched in presence of Gazetted Officer or Magistrate",
            "Search of female must be conducted strictly by female officer",
            "Recording grounds of belief in writing if search conducted without taking to Magistrate"
        ],
        "text": "When any officer duly employed under section 42 is about to search any person under the provisions of section 41, section 42 or section 43, he shall, if such person so requires, take such person without unnecessary delay to the nearest Gazetted Officer of any of the departments mentioned in section 42 or to the nearest Magistrate. Strict mandatory compliance established by Supreme Court Constitution Bench in Vijaysinh Chandubha Jadeja."
    },
    {
        "id": "JJ-2015-S10",
        "act": "Juvenile Justice (Care and Protection of Children) Act, 2015",
        "section": "10",
        "title": "Juvenile Justice Act Section 10 — Apprehension of Child in Conflict with Law",
        "topic": "Child accused, age below 18, special juvenile police unit, no police lockup",
        "type": "statute",
        "cognizable": None,
        "bailable": None,
        "punishment": "Statutory safeguard for minors",
        "triable_by": "Juvenile Justice Board (JJB)",
        "ingredients": [
            "Child alleged to be in conflict with law placed under charge of Special Juvenile Police Unit (SJPU) or child welfare police officer",
            "Child shall NOT be placed in police lockup or lodged in jail",
            "Production before Juvenile Justice Board within 24 hours of apprehension",
            "Mandatory identity confidentiality under Section 74"
        ],
        "text": "As soon as a child alleged to be in conflict with law is apprehended by the police, he shall be placed under the charge of the special juvenile police unit or the designated child welfare police officer, who shall produce the child before the Juvenile Justice Board without any loss of time and in no case beyond twenty-four hours of apprehension. In no case shall a child alleged to be in conflict with law be placed in a police lockup or lodged in a jail."
    },
    {
        "id": "POCSO-2012-S19",
        "act": "Protection of Children from Sexual Offences (POCSO) Act, 2012",
        "section": "19",
        "title": "POCSO Act Section 19 — Mandatory Reporting of Offences",
        "topic": "Child sexual assault, statutory reporting duty, victim age under 18",
        "type": "statute",
        "cognizable": True,
        "bailable": False,
        "punishment": "Failure to report punishable with imprisonment up to 6 months or fine",
        "triable_by": "Special POCSO Court",
        "ingredients": [
            "Any person who has apprehension or knowledge that an offence under this Act has been committed must provide information",
            "Police officer must record information in child-friendly environment",
            "Child not to be detained in police station during night"
        ],
        "text": "Any person who has apprehension that an offence under this Act is likely to be committed or has knowledge that such an offence has been committed, he shall provide such information to the Special Juvenile Police Unit or the local police. Failure to report by responsible persons is a punishable offence under Section 21."
    },

    # ------------------------------------------------- LANDMARK PRECEDENTS -------------------------------------------------
    {
        "id": "SC-PREC-ARJUN-PANDITRAO",
        "act": "Supreme Court of India Precedent",
        "section": "Civil Appeal Nos. 2082-2083 of 2020",
        "title": "Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal (2020) 7 SCC 1",
        "topic": "Mandatory nature of electronic certificate, secondary digital evidence, Section 65B/63",
        "type": "precedent",
        "cognizable": None,
        "bailable": None,
        "punishment": "Judicial Precedent / Law of the Land (Article 141)",
        "triable_by": "All Courts",
        "ingredients": [
            "Certificate under Section 65B(4) / BSA Section 63 is a condition precedent to admissibility of electronic records",
            "Oral evidence cannot substitute the required statutory certificate",
            "Distinction between original device owner (primary) vs printed/copied records (secondary)",
            "Court may summon required certificate under CrPC Sec 91 / BNSS Sec 94 if authority refuses"
        ],
        "text": "A 3-Judge Bench of the Supreme Court conclusively held that the certificate required under Section 65B(4) of the Evidence Act (now Section 63 of Bharatiya Sakshya Adhiniyam, 2023) is a mandatory condition precedent for the admissibility of electronic evidence in the form of secondary evidence (CCTV hard drives, CD-ROMs, printed call detail records). In the absence of a contemporaneous certificate signed by the person in lawful charge of the computer device, secondary electronic evidence is legally inadmissible."
    },
    {
        "id": "SC-PREC-SELVI",
        "act": "Supreme Court of India Precedent",
        "section": "Criminal Appeal No. 1267 of 2004",
        "title": "Smt. Selvi & Ors. v. State of Karnataka (2010) 7 SCC 263",
        "topic": "Inadmissibility of involuntary lie-detector, polygraph, brain mapping, Article 20(3)",
        "type": "precedent",
        "cognizable": None,
        "bailable": None,
        "punishment": "Judicial Precedent / Constitutional Protection",
        "triable_by": "All Courts",
        "ingredients": [
            "Involuntary administration of narco-analysis, polygraph test, or brain mapping violates Article 20(3) (right against self-incrimination)",
            "Violates personal liberty and privacy under Article 21",
            "Any information or confession obtained through such involuntary tests is completely inadmissible as evidence in court",
            "Subsequent discoveries under Section 27 IEA / Section 23 BSA admissible only if voluntary"
        ],
        "text": "The Supreme Court ruled that no individual can be subjected to lie-detector, polygraph, or narco-analysis tests against their consent, as doing so violates the fundamental right against self-incrimination guaranteed under Article 20(3) of the Constitution of India and personal liberty under Article 21. Any inculpatory statement or 'scientific truth' derived from non-consensual tests is inadmissible in evidence."
    },
    {
        "id": "SC-PREC-ARNESH-KUMAR",
        "act": "Supreme Court of India Precedent",
        "section": "Criminal Appeal No. 1277 of 2014",
        "title": "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273",
        "topic": "Arrest safeguards for offences punishable with imprisonment less than 7 years",
        "type": "precedent",
        "cognizable": None,
        "bailable": None,
        "punishment": "Mandatory Judicial Directive to Police and Magistrates",
        "triable_by": "All Police Stations and Magistrates",
        "ingredients": [
            "Police shall not automatically arrest accused when offence is punishable with imprisonment up to 7 years",
            "Investigating officer must fill mandatory checklist under Section 41 CrPC / Section 35 BNSS",
            "Magistrate shall not authorize detention mechanically without recording reasons",
            "Notice of appearance must be served within two weeks of case institution"
        ],
        "text": "The Supreme Court issued mandatory guidelines directing that police officers shall not automatically arrest when a case is registered under an offence punishable with imprisonment for a term which may be less than seven years or which may extend to seven years. Police officers must be satisfied that arrest is necessary under specified statutory criteria, record reasons in writing, and submit the checklist before the Magistrate."
    }
]


def main():
    import re
    # Sentences that describe how a section applies to a particular kind of case are commentary, not statute text: they
    # are kept in practice_note, and every entry is labelled as a summary that must be verified against the official text.
    triggers = ("Applicable to", "Critical for", "This section directly applies", "This new provision in BNS", "Governs admissibility of recovered")
    count = 0
    for item in CORPUS_DATA:
        item = dict(item)
        sents = re.split(r"(?<=[.])\s+", item.get("text", ""))
        notes = [x for x in sents if x.startswith(triggers)]
        if notes:
            item["text"] = " ".join(x for x in sents if x not in notes)
            item["practice_note"] = " ".join(notes)
        item.setdefault("verification_status", "paraphrase_unverified")
        item.setdefault("text_kind", "summary_not_official_text")
        file_path = CORPUS_DIR / f"{item['id'].lower()}.json"
        file_path.write_text(json.dumps(item, indent=2, ensure_ascii=False), encoding="utf-8")
        count += 1
    print(f"Successfully generated {count} comprehensive legal corpus documents in {CORPUS_DIR}")


if __name__ == "__main__":
    main()
