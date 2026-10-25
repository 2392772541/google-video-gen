p = r"D:\AI-Projects\infinite-canvas\web\src\pages\canvas\project.tsx"
with open(p, "r", encoding="utf-8") as f:
    content = f.read()

# 检查 DEFAULT_CHARACTER_PROFILES
old_profiles = '''export const DEFAULT_CHARACTER_PROFILES: Record<string, CharacterProfile> = {
    "sailor_moon": {
        characterId: "sailor_moon",
        name: "水手月亮 (月野兔)",
        fixedTraits: "金色及膝超长双马尾，头顶标志性双丸子头（发髻），额头佩戴金色月牙符印额饰，蓝色大眼睛，清秀面容",
        outfit: "经典白色水手服上衣，水蓝色水手领与百褶短裙，胸前巨大红色缎带蝴蝶结与金色圆形变身胸针，红色高筒皮靴",
        style: "1990年代日本经典赛璐璐手绘动画风格，清晰锐利的赛璐璐描边，纯净柔和的手绘渐变光影，复古胶片颗粒感",
        referenceAssets: [
            {
                id: "ref_sailor_moon_01",
                url: "/media/sailor_moon_master_ref.png",
                label: "月野兔标准赛璐璐立像",
                isPrimary: true
            }
        ],
        updatedAt: 1729840000000
    }
};'''

new_profiles = '''export const DEFAULT_CHARACTER_PROFILES: Record<string, CharacterProfile> = {
    "sailor_moon": {
        characterId: "sailor_moon",
        name: "水手月亮 (月野兔)",
        fixedTraits: "金色及膝超长双马尾，头顶标志性双丸子头（发髻），额头佩戴金色月牙符印额饰，蓝色大眼睛，清秀面容",
        outfit: "经典白色水手服上衣，水蓝色水手领与百褶短裙，胸前巨大红色缎带蝴蝶结与金色圆形变身胸针，红色高筒皮靴",
        style: "1990年代日本经典赛璐璐手绘动画风格，清晰锐利的赛璐璐描边，纯净柔和的手绘渐变光影，复古胶片颗粒感",
        referenceAssets: [
            {
                id: "ref_sailor_moon_01",
                url: "/media/sailor_moon_master_ref.png",
                label: "月野兔标准赛璐璐立像",
                isPrimary: true
            }
        ],
        updatedAt: 1729840000000
    },
    "tuxedo_mask": {
        characterId: "tuxedo_mask",
        name: "夜礼服假面 (地场卫)",
        fixedTraits: "深黑色短发，冷峻下颌线条，面部佩戴白色半脸面具（眼罩假面），手持深红丝绒玫瑰花",
        outfit: "高贵修身纯黑燕尾服，高顶黑色丝绸礼帽，内衬奢华红色丝绒里衬的长披风，纯白衬衫与白领结，白手套",
        style: "1990年代日本经典赛璐璐手绘动画风格，清晰锐利的赛璐璐描边，纯净柔和的手绘渐变光影，复古胶片颗粒感",
        referenceAssets: [
            {
                id: "ref_tuxedo_mask_01",
                url: "/media/tuxedo_mask_master_ref.png",
                label: "夜礼服假面标准赛璐璐立像",
                isPrimary: true
            }
        ],
        updatedAt: 1729840000000
    }
};'''

if old_profiles in content:
    content = content.replace(old_profiles, new_profiles, 1)

old_resolve = '''    if (/月野兔|水手月亮|美少女战士|Sailor\\s*Moon|Usagi/i.test(promptText)) {
        return DEFAULT_CHARACTER_PROFILES["sailor_moon"];
    }
    return undefined;'''

new_resolve = '''    if (/夜礼服假面|地场卫|Tuxedo\\s*Mask|燕尾服绅士/i.test(promptText)) {
        return DEFAULT_CHARACTER_PROFILES["tuxedo_mask"];
    }
    if (/月野兔|水手月亮|美少女战士|Sailor\\s*Moon|Usagi/i.test(promptText)) {
        return DEFAULT_CHARACTER_PROFILES["sailor_moon"];
    }
    return undefined;'''

if old_resolve in content:
    content = content.replace(old_resolve, new_resolve, 1)

with open(p, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated project.tsx with dual character profiles successfully!")
