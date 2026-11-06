import { z } from "zod";

// 单个镜头的基础类型定义
export const ShotBaseSchema = z.object({
  id: z.string(),
  durationInFrames: z.number().int().positive(),
});

// 1. 动感文字镜头参数
export const KeyTypographyParamsSchema = ShotBaseSchema.extend({
  type: z.literal("KeyTypography"),
  mainTitle: z.string(),
  highlightWord: z.string().optional(),
  subtitle: z.string().optional(),
  badge: z.string().optional(),
});

// 2. 像素与噪点扰动镜头参数（模拟对抗样本攻击）
export const NoiseDisruptorParamsSchema = ShotBaseSchema.extend({
  type: z.literal("NoiseDisruptor"),
  title: z.string(),
  labelBefore: z.string(), // 如 "熊猫 (98.2%)"
  labelAfter: z.string(),  // 如 "长臂猿 (99.7%)"
  noiseIntensity: z.number().min(0).max(1).default(0.4),
  description: z.string().optional(),
});

// 联合分镜类型
export const ShotSchema = z.discriminatedUnion("type", [
  KeyTypographyParamsSchema,
  NoiseDisruptorParamsSchema,
]);

// 整个视频项目的 DSL Schema
export const ProjectDSLSchema = z.object({
  projectTitle: z.string(),
  fps: z.number().default(30),
  width: z.number().default(1080),
  height: z.number().default(1920),
  theme: z.enum(["cyber_dark", "matrix_green", "crimson_hazard"]).default("cyber_dark"),
  shots: z.array(ShotSchema),
});

export type Shot = z.infer<typeof ShotSchema>;
export type ProjectDSL = z.infer<typeof ProjectDSLSchema>;
export type KeyTypographyParams = z.infer<typeof KeyTypographyParamsSchema>;
export type NoiseDisruptorParams = z.infer<typeof NoiseDisruptorParamsSchema>;
