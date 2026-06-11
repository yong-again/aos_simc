"""Grand Alliance / faction registry.

Wahapedia URL slugs and per-faction theme colors used by both the
scraper (URL construction) and the API (faction select menu / unit
rendering colors on the frontend canvas).
"""

import re

GRAND_ALLIANCES = {
    "Order": {
        "color": "#1f6fb2",
        "description": (
            "Armies dedicated to civilization, divine justice, and "
            "protecting the Mortal Realms."
        ),
        "description_ko": "문명과 신성한 정의, 필멸의 영역 수호에 헌신하는 군대입니다.",
    },
    "Chaos": {
        "color": "#8c1a1a",
        "description": (
            "Worshippers, daemons, and monsters devoted to the four "
            "Ruinous Powers or absolute anarchy."
        ),
        "description_ko": "네 파멸의 신 혹은 완전한 무정부 상태에 헌신하는 숭배자, 악마, 괴물들입니다.",
    },
    "Death": {
        "color": "#4e7a63",
        "description": (
            "Undead legions bound to the will of the Great Necromancer, "
            "Nagash."
        ),
        "description_ko": "위대한 강령술사 나가쉬의 의지에 묶인 언데드 군단입니다.",
    },
    "Destruction": {
        "color": "#b06a1f",
        "description": (
            "Rampaging hordes that live for battle, driven by instinct, "
            "savagery and the Waaagh!"
        ),
        "description_ko": "본능과 야만성, 와아아!에 이끌려 전투를 위해 살아가는 광란의 무리입니다.",
    },
}

FACTIONS = {
    # Order
    "stormcast-eternals": {
        "name": "Stormcast Eternals",
        "alliance": "Order",
        "color": "#d4af37",
        "description": "Sigmar's chosen, heavily armored warriors descending from the heavens.",
        "description_ko": "시그마가 선택한, 하늘에서 강림하는 중무장 전사들.",
    },
    "cities-of-sigmar": {
        "name": "Cities of Sigmar",
        "alliance": "Order",
        "color": "#3b5e8c",
        "description": "Diverse mortal armies of humans, aelves, and duardin fighting together.",
        "description_ko": "인간, 엘프, 두아딘이 함께 싸우는 다채로운 필멸자 군대.",
    },
    "sylvaneth": {
        "name": "Sylvaneth",
        "alliance": "Order",
        "color": "#4a7c3f",
        "description": "Living tree-spirits and vengeful fae led by the goddess Alarielle.",
        "description_ko": "여신 알라리엘이 이끄는 살아있는 나무 정령과 복수심에 찬 요정들.",
    },
    "lumineth-realm-lords": {
        "name": "Lumineth Realm-lords",
        "alliance": "Order",
        "color": "#e8e3c8",
        "description": "Highly disciplined and magically potent aelven hosts.",
        "description_ko": "고도로 훈련되고 마법에 능통한 엘프 군세.",
    },
    "daughters-of-khaine": {
        "name": "Daughters of Khaine",
        "alliance": "Order",
        "color": "#a3232e",
        "description": "Fanatical, bloodthirsty aelf worshippers of the god of murder.",
        "description_ko": "살육의 신을 섬기는 광신적이고 피에 굶주린 엘프 숭배자들.",
    },
    "idoneth-deepkin": {
        "name": "Idoneth Deepkin",
        "alliance": "Order",
        "color": "#2b8a8f",
        "description": "Reclusive, deep-sea aelves who raid coastal settlements for souls.",
        "description_ko": "영혼을 약탈하러 해안 정착지를 습격하는 은둔적인 심해 엘프.",
    },
    "kharadron-overlords": {
        "name": "Kharadron Overlords",
        "alliance": "Order",
        "color": "#b9862f",
        "description": "Sky-faring, gold-obsessed duardin (dwarfs) in high-tech airships.",
        "description_ko": "첨단 비행선을 타고 하늘을 누비는, 황금에 집착하는 두아딘(드워프).",
    },
    "fyreslayers": {
        "name": "Fyreslayers",
        "alliance": "Order",
        "color": "#d9692f",
        "description": "Mercenary duardin who fight for ur-gold and bear blazing runes.",
        "description_ko": "우르골드를 위해 싸우며 불타는 룬을 새긴 용병 두아딘.",
    },
    "seraphon": {
        "name": "Seraphon",
        "alliance": "Order",
        "color": "#2e8b8b",
        "description": "Ancient, star-faring lizardmen and saurian warriors guided by enigmatic Slann Starmasters.",
        "description_ko": "수수께끼의 슬란 스타마스터가 인도하는, 별을 항해하는 고대 리자드맨과 사우루스 전사들.",
    },
    # Chaos
    "slaves-to-darkness": {
        "name": "Slaves to Darkness",
        "alliance": "Chaos",
        "color": "#4d4a5a",
        "description": "Mortal marauders and warriors dedicated to the undivided powers of Chaos.",
        "description_ko": "카오스 전체의 힘에 헌신하는 필멸자 약탈자와 전사들.",
    },
    "blades-of-khorne": {
        "name": "Blades of Khorne",
        "alliance": "Chaos",
        "color": "#b3001b",
        "description": "Brutal, blood-crazed mortal and daemon servants of the Blood God.",
        "description_ko": "피의 신을 섬기는 잔혹하고 피에 미친 필멸자와 악마들.",
    },
    "disciples-of-tzeentch": {
        "name": "Disciples of Tzeentch",
        "alliance": "Chaos",
        "color": "#3a6ea5",
        "description": "Magical, scheming, and mutating followers of the Changer of the Ways.",
        "description_ko": "변화의 신을 따르는 마법적이고 책략적이며 끊임없이 변이하는 추종자들.",
    },
    "maggotkin-of-nurgle": {
        "name": "Maggotkin of Nurgle",
        "alliance": "Chaos",
        "color": "#6b8e23",
        "description": "Disgusting but resilient plague-ridden warriors of the god of decay.",
        "description_ko": "부패의 신을 섬기는 역겹지만 끈질긴 역병 전사들.",
    },
    "hedonites-of-slaanesh": {
        "name": "Hedonites of Slaanesh",
        "alliance": "Chaos",
        "color": "#b57edc",
        "description": "Decadent and swift aesthetic-worshippers seeking the ultimate sensory excess.",
        "description_ko": "궁극의 감각적 쾌락을 좇는 퇴폐적이고 신속한 숭배자들.",
    },
    "skaven": {
        "name": "Skaven",
        "alliance": "Chaos",
        "color": "#7a5c3e",
        "description": "Massive, subterranean swarms of treacherous ratmen armed with warpstone technology.",
        "description_ko": "워프스톤 기술로 무장한 배신적인 쥐인간의 거대한 지하 무리.",
    },
    # Death
    "soulblight-gravelords": {
        "name": "Soulblight Gravelords",
        "alliance": "Death",
        "color": "#7b1e3b",
        "description": "Aristocratic vampires and their undead thralls.",
        "description_ko": "귀족적인 뱀파이어와 그들의 언데드 노예들.",
    },
    "flesh-eater-courts": {
        "name": "Flesh-eater Courts",
        "alliance": "Death",
        "color": "#9c8f6e",
        "description": "Maddened ghouls and monsters who believe they are noble, honorable knights.",
        "description_ko": "자신들을 고귀하고 명예로운 기사라 믿는 광기에 빠진 구울과 괴물들.",
    },
    "nighthaunt": {
        "name": "Nighthaunt",
        "alliance": "Death",
        "color": "#5fa8a0",
        "description": "Terror-inducing, spectral spirits of the dead trapped in eternal torment.",
        "description_ko": "영원한 고통에 갇힌 공포를 부르는 망령 무리.",
    },
    "ossiarch-bonereapers": {
        "name": "Ossiarch Bonereapers",
        "alliance": "Death",
        "color": "#d8d3c4",
        "description": "Construct-armies meticulously crafted from the bone-tithes collected by Nagash.",
        "description_ko": "나가쉬가 거둔 뼈 공물로 정교하게 빚어낸 구조체 군대.",
    },
    # Destruction
    "ironjawz": {
        "name": "Ironjawz",
        "alliance": "Destruction",
        "color": "#caa519",
        "description": "Hulking armored orruks who live for the biggest, loudest scraps.",
        "description_ko": "가장 크고 시끄러운 싸움을 위해 사는 거대한 중갑 오럭.",
    },
    "kruleboyz": {
        "name": "Kruleboyz",
        "alliance": "Destruction",
        "color": "#5e7a3a",
        "description": "Cunning, swamp-dwelling orruks who favour poison, traps and dirty tricks.",
        "description_ko": "독과 함정, 비열한 속임수를 선호하는 교활한 늪지 오럭.",
    },
    "gloomspite-gitz": {
        "name": "Gloomspite Gitz",
        "alliance": "Destruction",
        "color": "#8a4fbe",
        "description": "Moon-mad grots, squigs and troggoths swarming from caves beneath the realms.",
        "description_ko": "지하 동굴에서 쏟아져 나오는, 달에 미친 그롯·스큌·트로고스 무리.",
    },
    "ogor-mawtribes": {
        "name": "Ogor Mawtribes",
        "alliance": "Destruction",
        "color": "#a9a9a9",
        "description": "Nomadic ogor hordes that eat their way across the realms in the Mawpath's wake.",
        "description_ko": "모파스를 따라 영역을 먹어치우며 떠도는 유목 오거 무리.",
    },
}

NAME_TO_SLUG = {v["name"].lower(): k for k, v in FACTIONS.items()}


def faction_list():
    """Faction menu payload grouped for the UI, with theme colors."""
    out = []
    for slug, f in FACTIONS.items():
        out.append(
            {
                "slug": slug,
                "name": f["name"],
                "alliance": f["alliance"],
                "color": f["color"],
                "alliance_color": GRAND_ALLIANCES[f["alliance"]]["color"],
                "alliance_description": GRAND_ALLIANCES[f["alliance"]]["description"],
                "alliance_description_ko": GRAND_ALLIANCES[f["alliance"]]["description_ko"],
                "description": f["description"],
                "description_ko": f["description_ko"],
            }
        )
    return out


def _norm_name(name: str) -> str:
    """Lowercase and strip punctuation so 'Flesh-eater Courts',
    'flesh eater courts' and the slug all compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def resolve_faction_slug(name: str) -> str | None:
    """Map a free-form faction name (e.g. from a parsed roster) to a slug."""
    if not name:
        return None
    if name.strip().lower() in FACTIONS:
        return name.strip().lower()
    n = _norm_name(name)
    for slug, f in FACTIONS.items():
        fn = _norm_name(f["name"])
        if n == fn or n in fn or fn in n:
            return slug
    return None
