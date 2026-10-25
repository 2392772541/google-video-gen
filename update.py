import os

p = r'D:\AI-Projects\infinite-canvas\web\src\lib\prompt-compiler\visual-compiler.ts'
with open(p, 'r', encoding='utf-8') as f:
    content = f.read()

if 'CharacterProfile' not in content:
    content = 'import type { CharacterProfile } from "../../types/canvas";\n' + content

if 'characterConstraint?: string;' not in content:
    target = '    styleCategory: "anime" | "realistic" | "cg" | "general";'
    replacement = target + '\n    characterConstraint?: string;\n    characterProfile?: CharacterProfile;'
    content = content.replace(target, replacement, 1)

old_sig = 'export function compileVisualPrompt(rawPrompt: string): CompiledVisualPrompt {'
new_sig = 'export function compileVisualPrompt(rawPrompt: string, characterProfile?: CharacterProfile): CompiledVisualPrompt {'
if old_sig in content:
    content = content.replace(old_sig, new_sig, 1)

old_empty = '''            safeAlternativePrompt: "",
            safeCompiledFinalPrompt: "",
            styleCategory: "general",
        };'''
new_empty = '''            safeAlternativePrompt: "",
            safeCompiledFinalPrompt: "",
            styleCategory: "general",
            characterConstraint: undefined,
            characterProfile,
        };'''
if old_empty in content:
    content = content.replace(old_empty, new_empty, 1)

char_logic = '''
    // 角色视觉档案一致性约束构建
    let characterConstraint = "";
    if (characterProfile) {
        const charParts: string[] = [];
        if (characterProfile.name) charParts.push(`角色:${characterProfile.name}`);
        if (characterProfile.fixedTraits) charParts.push(`固定外貌特征:${characterProfile.fixedTraits}`);
        if (characterProfile.outfit) charParts.push(`服装与配饰:${characterProfile.outfit}`);
        if (characterProfile.style) charParts.push(`统一画风:${characterProfile.style}`);
        characterConstraint = charParts.join("，");
    }
'''

target_insert = '    // 5. 组装最终送模 prompt\n    const parts: string[] = [];'
replacement_insert = char_logic + '\n    // 5. 组装最终送模 prompt\n    const parts: string[] = [];\n    if (characterConstraint) parts.push(characterConstraint);'
if target_insert in content:
    content = content.replace(target_insert, replacement_insert, 1)

target_safe = '    const safeParts: string[] = [];'
replacement_safe = '    const safeParts: string[] = [];\n    if (characterConstraint) safeParts.push(characterConstraint);'
if target_safe in content:
    content = content.replace(target_safe, replacement_safe, 1)

target_ret = '        styleCategory,\n    };'
replacement_ret = '        styleCategory,\n        characterConstraint,\n        characterProfile,\n    };'
if target_ret in content:
    content = content.replace(target_ret, replacement_ret, 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated visual-compiler.ts successfully!')
