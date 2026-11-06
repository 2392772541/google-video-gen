import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CompareSplitParams } from "../../types/schema";

export const CompareSplit: React.FC<{ params: CompareSplitParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100 },
  });

  // 左/上卡片入场（第 10 帧）
  const leftSpring = spring({
    frame: frame - 10,
    fps,
    config: { damping: 15, stiffness: 110 },
  });

  // 右/下卡片入场（第 22 帧）
  const rightSpring = spring({
    frame: frame - 22,
    fps,
    config: { damping: 15, stiffness: 110 },
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "0 60px",
      }}
    >
      {/* 顶部徽标 */}
      {params.badge && (
        <div
          style={{
            opacity: titleSpring,
            backgroundColor: "rgba(56, 189, 248, 0.15)",
            color: "#38bdf8",
            border: "1px solid rgba(56, 189, 248, 0.4)",
            padding: "8px 24px",
            borderRadius: 999,
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: 2,
            marginBottom: 25,
            fontFamily: "monospace",
          }}
        >
          {params.badge}
        </div>
      )}

      {/* 标题 */}
      <div
        style={{
          opacity: titleSpring,
          color: "#ffffff",
          fontSize: 54,
          fontWeight: 800,
          textAlign: "center",
          marginBottom: 50,
          maxWidth: 900,
        }}
      >
        {params.title}
      </div>

      {/* 对比双卡片（竖屏上下堆叠展示） */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width: "100%",
          maxWidth: 780,
          gap: 30,
        }}
      >
        {/* 卡片 1：传统对比项 */}
        <div
          style={{
            opacity: frame >= 10 ? leftSpring : 0,
            transform: `translateX(${frame >= 10 ? (1 - leftSpring) * -40 : -40}px)`,
            backgroundColor: "rgba(30, 41, 59, 0.7)",
            border: "1px solid rgba(148, 163, 184, 0.25)",
            borderRadius: 20,
            padding: "30px 36px",
          }}
        >
          <div
            style={{
              color: "#94a3b8",
              fontSize: 26,
              fontWeight: 700,
              marginBottom: 10,
              letterSpacing: 1,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span style={{ color: "#ef4444", fontSize: 24 }}>✕</span>
            {params.leftLabel}
          </div>
          <div style={{ color: "#cbd5e1", fontSize: 32, lineHeight: 1.45 }}>
            {params.leftDesc}
          </div>
        </div>

        {/* 卡片 2：核心优势项 */}
        <div
          style={{
            opacity: frame >= 22 ? rightSpring : 0,
            transform: `translateX(${frame >= 22 ? (1 - rightSpring) * 40 : 40}px)`,
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            border: "2px solid rgba(56, 189, 248, 0.6)",
            borderRadius: 20,
            padding: "32px 36px",
            boxShadow: "0 0 35px rgba(56, 189, 248, 0.2)",
          }}
        >
          <div
            style={{
              color: "#38bdf8",
              fontSize: 28,
              fontWeight: 700,
              marginBottom: 12,
              letterSpacing: 1,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span style={{ color: "#22c55e", fontSize: 26 }}>✓</span>
            {params.rightLabel}
          </div>
          <div style={{ color: "#f8fafc", fontSize: 34, fontWeight: 600, lineHeight: 1.45 }}>
            {params.rightDesc}
          </div>
        </div>
      </div>

      {/* 底部备注总结 */}
      {params.comparisonNote && (
        <div
          style={{
            marginTop: 50,
            opacity: interpolate(frame, [40, 55], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            color: "#38bdf8",
            fontSize: 28,
            textAlign: "center",
            maxWidth: 820,
            fontWeight: 500,
          }}
        >
          {params.comparisonNote}
        </div>
      )}
    </AbsoluteFill>
  );
};
