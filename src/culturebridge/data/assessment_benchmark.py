"""AI-authored review cases from inspected official-source snapshots, not expert/student labels."""

CASES = [
    {
        "id": "roof-material",
        "source": "edinburgh-great-hall",
        "concept": "재료",
        "question": "원문에서 어떤 부분에 나무가 쓰였다고 하나요?",
        "quote_pattern": r"wooden roof",
        "answers": [
            (
                "지붕에 나무가 쓰였다고 해요. 원문이 지붕의 재료를 설명하기 때문이에요.",
                "tentative_support",
            ),
            (
                "지붕이 나무이므로 건물 전체의 모든 부분도 나무로 지었어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "approximate-year",
        "source": "st-margarets-chapel",
        "concept": "시대",
        "question": "1130년은 정확히 확정된 연도인가요? 원문의 표현으로 설명해 주세요.",
        "quote_pattern": r"around 1130",
        "answers": [
            (
                "around라는 말이 있어서 약 1130년이라는 뜻이지 정확한 연도로 단정할 수 없어요.",
                "tentative_support",
            ),
            (
                "1130년이라는 숫자가 있으니 정확히 그해에 지었다고 확정할 수 있어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "present-pagoda",
        "source": "toji-pagoda",
        "concept": "시대",
        "question": "1644년은 어떤 탑에 관한 연도인가요?",
        "quote_pattern": r"현재의 탑.*1644",
        "answers": [
            (
                "현재의 탑이 지어진 해예요. 사찰이 처음 세워진 해라는 뜻은 아니에요.",
                "tentative_support",
            ),
            (
                "현재 탑이 1644년에 지어졌으니 사찰의 역사도 반드시 그때 처음 시작됐어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "gold-surface",
        "source": "kinkakuji-pavilion",
        "concept": "재료",
        "question": "금박에 관한 설명으로 건물 전체의 재료까지 알 수 있나요?",
        "quote_pattern": r"금박으로 덮인",
        "answers": [
            (
                "금박으로 덮였다는 표면 설명이에요. 이것만으로 건물 전체가 금이라는 뜻은 아니에요.",
                "tentative_support",
            ),
            (
                "금박으로 덮였으므로 건물의 속과 기둥까지 전부 금으로 만들었어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "room-not-whole",
        "source": "humayun-tomb",
        "concept": "구조",
        "question": "팔각형이라는 표현은 무엇을 설명하나요?",
        "quote_pattern": r"octagonal chamber",
        "answers": [
            (
                "chamber라는 방의 모양을 설명해요. 전체 건물의 평면이라고 확대하면 안 돼요.",
                "tentative_support",
            ),
            (
                "방이 팔각형이므로 건물 전체와 주변 정원도 모두 팔각형이에요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "start-not-completion",
        "source": "mont-saint-michel-abbey",
        "concept": "시대",
        "question": "1023년은 공사 시작과 완공 중 어떤 사건에 관한 설명인가요?",
        "quote_pattern": r"began according to tradition in 1023",
        "answers": [
            (
                "전승에 따르면 공사를 시작한 시기예요. "
                "began이라고 하니 완공 연도라고 할 수 없어요.",
                "tentative_support",
            ),
            ("1023년에 공사를 모두 마쳤다는 확정적인 설명이에요.", "possible_misconception"),
        ],
    },
    {
        "id": "rebuild-from",
        "source": "agra-fort",
        "concept": "시대",
        "question": "from 1565라는 말로 무엇을 알 수 있나요?",
        "quote_pattern": r"rebuilt.*from 1565",
        "answers": [
            (
                "1565년부터 다시 지었다는 뜻이에요. 이 문장만으로 완공한 해까지 확정할 수 없어요.",
                "tentative_support",
            ),
            (
                "1565년부터라는 말은 1565년에 재건을 모두 끝냈다는 뜻이에요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "multi-stage",
        "source": "stonehenge",
        "concept": "시대",
        "question": "이 유산 전체가 한 해에 완성됐다고 할 수 있나요?",
        "quote_pattern": r"several stages",
        "answers": [
            (
                "여러 단계에 걸쳐 지었다고 하므로 각 시기가 가리키는 공사를 나누어 봐야 해요.",
                "tentative_support",
            ),
            (
                "기원전 2500년이라는 숫자 하나가 있으니 모든 부분을 그해에 한꺼번에 완성했어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "carving-material",
        "source": "ninomaru-palace",
        "concept": "재료",
        "question": "나무에 관한 이 설명은 궁전의 어느 부분을 가리키나요?",
        "quote_pattern": r"carvings.*cypress wood",
        "answers": [
            (
                "방 사이의 조각 장식을 설명해요. 그 부분의 재료를 궁전 전체로 넓혀 말하면 안 돼요.",
                "tentative_support",
            ),
            (
                "조각이 나무이니 궁전의 모든 벽과 지붕도 이 나무 하나로 만들었다는 뜻이에요.",
                "possible_misconception",
            ),
            ("아직 잘 모르겠어요.", "none"),
            ("그런데 다른 인물의 역사를 검색하고 싶어요.", "none"),
        ],
    },
]

# The inspected KHS Dabotap snapshot (2026-10-25) supports these exact concepts.
# Provider-qualified IDs prevent treating a national API record as an overseas source.
CASES += [
    {
        "id": "khs-estimated-year",
        "source_id": "khs:11:0000200000000:37",
        "concept": "시대",
        "question": "다보탑의 751년은 확정된 연도인가요? 원문의 표현으로 설명해 주세요.",
        "quote_pattern": r"751.*추측된다",
        "answers": [
            (
                "추측된다고 하므로 약 751년에 세운 것으로 보지만 확정된 연도라고 할 수는 없어요.",
                "tentative_support",
            ),
            (
                "751년이라고 쓰였으니 확실히 그해 세웠다고 단정할 수 있어요.",
                "possible_misconception",
            ),
        ],
    },
    {
        "id": "khs-pagoda-structure",
        "source_id": "khs:11:0000200000000:37",
        "concept": "구조",
        "question": "다보탑의 기단과 탑신은 각각 어떤 모양으로 설명되어 있나요?",
        "quote_pattern": r"십.*기단.*8각형.*탑신",
        "answers": [
            (
                "기단은 십자 모양이고 탑신은 8각형이에요. 원문이 두 부분을 따로 설명해요.",
                "tentative_support",
            ),
            ("기단과 탑신은 구분 없이 모두 원형이라고 설명되어 있어요.", "possible_misconception"),
            ("아직 잘 모르겠어요.", "none"),
            ("이제 세종대왕의 업적을 찾아 주세요.", "none"),
        ],
    },
    {
        "id": "khs-stone-material",
        "source_id": "khs:11:0000200000000:37",
        "concept": "재료",
        "question": "석탑이라는 표현으로 어떤 재료를 알 수 있나요?",
        "quote_pattern": r"다보탑.*석탑",
        "answers": [
            ("돌로 만든 탑이라는 뜻이에요. 석탑이라는 원문 표현이 근거예요.", "tentative_support"),
            ("석탑이라는 말은 나무로 만든 탑이라는 뜻이에요.", "possible_misconception"),
        ],
    },
    {
        "id": "khs-religious-context",
        "source_id": "khs:11:0000200000000:37",
        "concept": "종교적 배경",
        "question": "두 탑의 배치는 어떤 경전의 이야기를 나타내려고 한 것인가요?",
        "quote_pattern": r"법화경.*탑으로 구현",
        "answers": [
            (
                "법화경의 이야기를 탑으로 나타내려고 했어요. "
                "다보불이 석가여래의 설법을 증명한다는 내용이에요.",
                "tentative_support",
            ),
            (
                "원문은 불교 경전과는 관련 없는 군사 훈련을 표현한 것이라고 해요.",
                "possible_misconception",
            ),
        ],
    },
]
