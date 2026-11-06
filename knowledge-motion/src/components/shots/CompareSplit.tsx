import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CompareSplitParams } from "../../types/schema";

export const CompareSplit: React.FC<{ params: CompareSplitParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 顶部入场动效
  const titleEntrance = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100 },
  });

  // 左卡片第 6 帧入场
  const leftCardEntrance = spring({
    frame: Math.max(0, frame - 6),
    fps,
    config: { damping: 14, stiffness: 90 },
  });

  // 右卡片第 14 帧入场
  const rightCardEntrance = spring({
    frame: Math.max(0, frame - 14),
    fps,
    config: { damping: 14, stiffness: 90 },
  });

  // 底部结论第 24 帧淡入
  const noteOpacity = interpolate(frame, [24, 38], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "0 60px",
      }}
    >
      {/* 顶部标题区域 */}
      <div
        style={{
          textAlign: "center",
          marginBottom: 40,
          opacity: titleEntrance,
          transform: `translateY(${interpolate(titleEntrance, [0, 1], [30, 0])}px)`,
        }}
      >
        {params.badge && (
          <div
            style={{
              color: "#22c55e",
              fontFamily: "monospace",
              fontSize: 24,
              letterSpacing: 3,
              marginBottom: 12,
              fontWeight: 700,
            }}
          >
            {params.badge}
          </div>
        )}
        <div
          style={{
            color: "#ffffff",
            fontSize: 52,
            fontWeight: 800,
            letterSpacing: -1,
          }}
        >
          {params.title}
        </div>
      </div>

      {/* 上下两相对比卡片 */}
      <div
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 30,
          position: "relative",
        }}
      >
        {/* 对比项 A：普通/传统 */}
        <div
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.75)",
            border: "1px solid rgba(148, 163, 184, 0.2)",
            borderRadius: 20,
            padding: "32px 36px",
            transform: `translateY(${interpolate(leftCardEntrance, [0, 1], [40, 0])}px) scale(${interpolate(leftCardEntrance, [0, 1], [0.95, 1])})`,
            opacity: leftCardEntrance,
          }}
        >
          <div
            style={{
              color: "#94a3b8",
              fontSize: 22,
              fontWeight: 600,
              marginBottom: 8,
              letterSpacing: 1,
            }}
          >
            传统认知 / 广谱
          </div>
          <div
            style={{
              color: "#cbd5e1",
              fontSize: 40,
              fontWeight: 700,
              marginBottom: 12,
            }}
          >
            {params.leftLabel}
          </div>
          <div
            style={{
              color: "#64748b",
              fontSize: 28,
              lineHeight: 1.45,
            }}
          >
            {params.leftDesc}
          </div>
        </div>

        {/* 中间发光 VS 标 */}
        <div
          style={{
            alignSelf: "center",
            backgroundColor: "#22c55e",
            color: "#050d0a",
            fontWeight: 900,
            fontSize: 22,
            padding: "4px 20px",
            borderRadius: 999,
            boxShadow: "0 0 20px rgba(34, 197, 94, 0.6)",
            margin: "-15px 0",
            zIndex: 10,
          }}
        >
          VS
        </div>

        {/* 对比项 B：褐藻寡糖/核心优势 */}
        <div
          style={{
            backgroundColor: "rgba(6, 78, 59, 0.35)",
            border: "2px solid rgba(34, 197, 94, 0.6)",
            boxShadow: "0 0 40px rgba(34, 197, 94, 0.15)",
            borderRadius: 20,
            padding: "32px 36px",
            transform: `translateY(${interpolate(rightCardEntrance, [0, 1], [40, 0])}px) scale(${interpolate(rightCardEntrance, [0, 1], [0.95, 1])})`,
            opacity: rightCardEntrance,
          }}
        >
          <div
            style={{
              color: "#4ade80",
              fontSize: 22,
              fontWeight: 700,
              marginBottom: 8,
              letterSpacing: 1,
            }}
          >
            专项定向 / 高活性
          </div>
          <div
            style={{
              color: "#ffffff",
              fontSize: 42,
              fontWeight: 800,
              marginBottom: 12,
              textShadow: "0 0 20px rgba(34, 197, 94, 0.4)",
            }}
          >
            {params.rightLabel}
          </div>
          <div
            style={{
              color: "#86efac",
              fontSize: 28,
              lineHeight: 1.45,
            }}
          >
            {params.rightDesc}
          </div>
        </div>
      </div>

      {/* 底部关键提示 */}
      {params.comparisonNote && (
        <div
          style={{
            marginTop: 36,
            textAlign: "center",
            color: "#94a3b8",
            fontSize: 26,
            maxWidth: 860,
            lineHeight: 1.5,
            opacity: noteOpacity,
          }}
        >
          💡 {params.comparisonNote}
        </div>
      )}
    </AbsoluteFill>
  );
};
