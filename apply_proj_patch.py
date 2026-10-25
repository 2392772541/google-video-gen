p = r"D:\AI-Projects\infinite-canvas\web\src\pages\canvas\project.tsx"
with open(p, "r", encoding="utf-8") as f:
    content = f.read()

# 1. 导入 CharacterProfile
if "type CharacterProfile," not in content:
    target = "    type CanvasNodeMetadata,"
    replacement = "    type CanvasNodeMetadata,\n    type CharacterProfile,"
    content = content.replace(target, replacement, 1)

# 2. 插入角色档案定义与解析函数
helper_code = '''
export const DEFAULT_CHARACTER_PROFILES: Record<string, CharacterProfile> = {
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
};

export function resolveCharacterProfileForPrompt(promptText: string, metadata?: CanvasNodeMetadata, upstreamNode?: CanvasNodeData): CharacterProfile | undefined {
    if (metadata?.characterProfileSnapshot) return metadata.characterProfileSnapshot;
    const charId = metadata?.characterId || upstreamNode?.metadata?.characterId;
    if (charId && DEFAULT_CHARACTER_PROFILES[charId]) {
        return DEFAULT_CHARACTER_PROFILES[charId];
    }
    if (/月野兔|水手月亮|美少女战士|Sailor\\s*Moon|Usagi/i.test(promptText)) {
        return DEFAULT_CHARACTER_PROFILES["sailor_moon"];
    }
    return undefined;
}
'''

if "DEFAULT_CHARACTER_PROFILES" not in content:
    # 插入在 imports 之后，组件定义之前
    marker = "export default function ProjectCanvasPage"
    if marker in content:
        content = content.replace(marker, helper_code + "\n" + marker, 1)
    else:
        marker2 = "function InfiniteCanvasPage"
        content = content.replace(marker2, helper_code + "\n" + marker2, 1)

# 3. 在 2705 行附近使用 resolveCharacterProfileForPrompt
old_block = '''                        metadata: {
                            prompt: effectivePrompt,
                            compiledPrompt: compileVisualPrompt(effectivePrompt).compiledFinalPrompt,'''
new_block = '''                        metadata: {
                            prompt: effectivePrompt,
                            characterId: resolveCharacterProfileForPrompt(effectivePrompt, node.metadata, sourceNode)?.characterId,
                            characterProfileSnapshot: resolveCharacterProfileForPrompt(effectivePrompt, node.metadata, sourceNode),
                            compiledPrompt: compileVisualPrompt(effectivePrompt, resolveCharacterProfileForPrompt(effectivePrompt, node.metadata, sourceNode)).compiledFinalPrompt,'''
if old_block in content:
    content = content.replace(old_block, new_block, 1)

old_compile = "const visualCompiled = compileVisualPrompt(effectivePrompt);"
new_compile = "const charProfile = resolveCharacterProfileForPrompt(effectivePrompt, node.metadata, sourceNode);\n                                const visualCompiled = compileVisualPrompt(effectivePrompt, charProfile);"
if old_compile in content:
    content = content.replace(old_compile, new_compile, 1)

# 4. 在 3185 行附近单镜头重试
old_retry = "const visualCompiled = compileVisualPrompt(prompt);"
new_retry = "const charProfile = resolveCharacterProfileForPrompt(prompt, node.metadata);\n                const visualCompiled = compileVisualPrompt(prompt, charProfile);"
if old_retry in content:
    content = content.replace(old_retry, new_retry, 1)

with open(p, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated project.tsx with CharacterProfile integration successfully!")
